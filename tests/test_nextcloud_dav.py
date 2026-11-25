"""Tests du client WebDAV avec une session requests mockée (pas de vrai serveur)."""

import pytest

from photos_importer.nextcloud_dav import NextcloudWebDAV

BASE = "https://cloud.example.org/remote.php/dav/files/thomas"


class FausseReponse:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = status_code
        self.text = text


class FausseSession:
    """Session factice : enregistre les appels, renvoie des statuts programmés."""

    def __init__(self):
        self.auth = None
        self.appels: list[tuple] = []
        self.statuts: dict[tuple[str, str], int] = {}
        self.statut_put = 201

    def request(self, methode: str, url: str, headers: dict | None = None, **kwargs):
        self.appels.append((methode, url, headers))
        return FausseReponse(self.statuts.get((methode, url), 404))

    def put(self, url: str, data=None, **kwargs):
        self.appels.append(("PUT", url, data))
        return FausseReponse(self.statut_put)


def _dav(session: FausseSession) -> NextcloudWebDAV:
    return NextcloudWebDAV(BASE + "/", "thomas", "tok-secret", session=session)


def test_auth_et_url_sans_slash_final():
    s = FausseSession()
    dav = _dav(s)
    assert s.auth == ("thomas", "tok-secret")
    assert dav._url("Photos/2024") == f"{BASE}/Photos/2024"


def test_dossier_existe_propfind_depth0():
    s = FausseSession()
    dav = _dav(s)
    s.statuts[("PROPFIND", f"{BASE}/Photos")] = 207
    assert dav.dossier_existe("Photos") is True
    assert dav.dossier_existe("Inconnu") is False
    methode, _, headers = s.appels[0]
    assert methode == "PROPFIND"
    assert headers == {"Depth": "0"}


def test_creer_dossier_201_et_405_ok():
    s = FausseSession()
    dav = _dav(s)
    s.statuts[("MKCOL", f"{BASE}/Photos/2024")] = 201
    dav.creer_dossier("Photos/2024")
    s.statuts[("MKCOL", f"{BASE}/Photos/2024/07")] = 405  # existe déjà : OK
    dav.creer_dossier("Photos/2024/07")


def test_creer_dossier_autre_statut_erreur():
    s = FausseSession()
    dav = _dav(s)
    s.statuts[("MKCOL", f"{BASE}/Photos")] = 500
    with pytest.raises(RuntimeError, match="MKCOL"):
        dav.creer_dossier("Photos")


def test_creer_dossier_en_cache_ne_renvoie_pas():
    s = FausseSession()
    dav = _dav(s)
    s.statuts[("MKCOL", f"{BASE}/Photos")] = 201
    dav.creer_dossier("Photos")
    dav.creer_dossier("Photos")
    mkcol = [a for a in s.appels if a[0] == "MKCOL"]
    assert len(mkcol) == 1


def test_fichier_existe():
    s = FausseSession()
    dav = _dav(s)
    s.statuts[("PROPFIND", f"{BASE}/Photos/2024/07/IMG_0042.JPG")] = 207
    assert dav.fichier_existe("Photos/2024/07/IMG_0042.JPG") is True
    assert dav.fichier_existe("Photos/2024/07/IMG_0043.JPG") is False


def test_envoyer_put_streame_succes(tmp_path):
    s = FausseSession()
    dav = _dav(s)
    local = tmp_path / "IMG_0042.JPG"
    local.write_bytes(b"donnees")
    for statut in (201, 204):
        s.statut_put = statut
        assert dav.envoyer(local, "Photos/2024/07/IMG_0042.JPG") is True
    methode, url, data = s.appels[-1]
    assert methode == "PUT"
    assert url == f"{BASE}/Photos/2024/07/IMG_0042.JPG"
    assert hasattr(data, "read")  # descripteur de fichier, pas de chargement en RAM


def test_envoyer_echec(tmp_path):
    s = FausseSession()
    dav = _dav(s)
    s.statut_put = 500
    local = tmp_path / "x.jpg"
    local.write_bytes(b"x")
    assert dav.envoyer(local, "Photos/x.jpg") is False
