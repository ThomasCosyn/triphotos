"""Tests de organize : rangement local (SHA-256, suffixes) et WebDAV (mocké)."""

import os
from datetime import datetime
from pathlib import Path

from PIL import Image

from photos_importer.organize import Compteurs, avertir_heic, est_media, ranger_local, ranger_webdav


def _jpg(chemin: Path, date_exif: str | None = None) -> None:
    img = Image.new("RGB", (8, 8))
    if date_exif:
        exif = Image.Exif()
        exif[36867] = date_exif
        img.save(chemin, exif=exif)
    else:
        img.save(chemin)


class FauxDAV:
    """Client WebDAV factice : mémorise dossiers créés et fichiers envoyés."""

    def __init__(self, existants: set[str] | None = None, succes: bool = True):
        self.existants = set(existants or set())
        self.succes = succes
        self.dossiers: list[str] = []
        self.envoyes: list[tuple[Path, str]] = []

    def fichier_existe(self, distant: str) -> bool:
        return distant in self.existants

    def creer_dossier(self, dossier: str) -> None:
        self.dossiers.append(dossier)

    def envoyer(self, local: Path, distant: str) -> bool:
        if self.succes:
            self.envoyes.append((local, distant))
            self.existants.add(distant)
        return self.succes


def test_est_media():
    assert est_media(Path("a.JPG"))
    assert est_media(Path("b.mp4"))
    assert est_media(Path("c.MTS"))  # AVCHD, casse quelconque
    assert est_media(Path("d.m2ts"))
    assert est_media(Path("e.wav"))  # son
    assert est_media(Path("f.mp3"))
    assert not est_media(Path("notes.txt"))


def test_avertir_heic_sans_pillow_heif(capsys, monkeypatch):
    from photos_importer import organize

    monkeypatch.setattr(organize, "HEIC_OK", False)
    avertir_heic([Path("a.heic")])
    assert "pillow-heif" in capsys.readouterr().out
    avertir_heic([Path("a.jpg")])
    monkeypatch.setattr(organize, "HEIC_OK", True)
    avertir_heic([Path("a.heic")])
    assert capsys.readouterr().out == ""


def test_ranger_local_dry_run_ne_touche_rien(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "Photos"
    dest.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    c = ranger_local([f], dest, deplacer=True, dry_run=True)
    assert c.ranges == 1 and c.erreurs == 0
    assert f.exists()
    assert list(dest.rglob("*")) == []


def test_ranger_local_deplace_dans_yyyy_mm(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "Photos"
    dest.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    c = ranger_local([f], dest, deplacer=True, dry_run=False)
    assert c.ranges == 1
    assert (dest / "2024" / "07" / "IMG_0001.JPG").exists()
    assert not f.exists()


def test_ranger_local_copie_conserve_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "Photos"
    dest.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    c = ranger_local([f], dest, deplacer=False, dry_run=False)
    assert c.ranges == 1
    assert f.exists() and (dest / "2024" / "07" / "IMG_0001.JPG").exists()


def test_ranger_local_doublon_hash_identique(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "Photos" / "2024" / "07"
    dest.mkdir(parents=True)
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    shutil_copie = dest / "IMG_0001.JPG"
    _jpg(shutil_copie, "2024:07:15 10:30:00")
    # même contenu binaire
    shutil_copie.write_bytes(f.read_bytes())
    c = ranger_local([f], tmp_path / "Photos", deplacer=True, dry_run=False)
    assert c.doublons == 1 and c.ranges == 0
    assert not f.exists()  # doublon supprimé en mode déplacement


def test_ranger_local_nom_pris_contenu_different_suffixe(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "Photos" / "2024" / "07"
    dest.mkdir(parents=True)
    (dest / "IMG_0001.JPG").write_bytes(b"autre contenu")
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    c = ranger_local([f], tmp_path / "Photos", deplacer=False, dry_run=False)
    assert c.ranges == 1 and c.doublons == 0
    assert (dest / "IMG_0001_1.JPG").exists()
    assert f.exists()  # mode copie : source conservée


def test_ranger_local_extension_ignoree(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "Photos"
    dest.mkdir()
    f = src / "notes.txt"
    f.write_text("hello")
    c = ranger_local([f], dest, deplacer=True, dry_run=False)
    assert c.ignores == 1 and f.exists()


def test_ranger_local_repli_mtime_sans_exif(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dest = tmp_path / "Photos"
    dest.mkdir()
    f = src / "IMG_0002.JPG"
    _jpg(f)  # sans EXIF
    stamp = datetime(2019, 3, 8, 12, 0, 0).timestamp()
    os.utime(f, (stamp, stamp))
    c = ranger_local([f], dest, deplacer=False, dry_run=False)
    assert c.ranges == 1
    assert (dest / "2019" / "03" / "IMG_0002.JPG").exists()


def test_ranger_webdav_upload_puis_suppression_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    dav = FauxDAV()
    c = ranger_webdav([f], dav, "Photos", supprimer_apres=True, dry_run=False)
    assert c.ranges == 1 and c.erreurs == 0
    assert dav.envoyes == [(f, "Photos/2024/07/IMG_0001.JPG")]
    assert "Photos/2024" in dav.dossiers and "Photos/2024/07" in dav.dossiers
    assert not f.exists()  # supprimé APRÈS upload confirmé


def test_ranger_webdav_echec_upload_conserve_source(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    dav = FauxDAV(succes=False)
    c = ranger_webdav([f], dav, "Photos", supprimer_apres=True, dry_run=False)
    assert c.erreurs == 1 and c.ranges == 0
    assert f.exists()  # jamais supprimé sans certitude
    assert dav.envoyes == []


def test_ranger_webdav_doublon_nom(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    dav = FauxDAV(existants={"Photos/2024/07/IMG_0001.JPG"})
    c = ranger_webdav([f], dav, "Photos", supprimer_apres=True, dry_run=False)
    assert c.doublons == 1 and dav.envoyes == []
    assert not f.exists()  # doublon déjà à distance : source nettoyée


def test_ranger_webdav_dry_run_ne_supprime_pas(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f, "2024:07:15 10:30:00")
    dav = FauxDAV(existants={"Photos/2024/07/IMG_0001.JPG"})
    c = ranger_webdav([f], dav, "Photos", supprimer_apres=True, dry_run=True)
    assert c.doublons == 1
    assert f.exists() and dav.envoyes == [] and dav.dossiers == []


def test_compteurs_resume():
    c = Compteurs(ranges=3, doublons=1, ignores=2, erreurs=1)
    assert c.resume() == "Terminé : 3 rangé(s), 1 doublon(s), 2 ignoré(s), 1 erreur(s)."
