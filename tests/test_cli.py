"""Tests d'intégration des commandes CLI (sans serveur ni binaire externe)."""

import pytest
from PIL import Image

from photos_importer import rclone
from photos_importer.cli import from_phone, import_folder, migrate_gdrive


def _jpg(chemin, date_exif="2024:07:15 10:30:00"):
    img = Image.new("RGB", (8, 8))
    exif = Image.Exif()
    exif[36867] = date_exif
    img.save(chemin, exif=exif)


def test_import_folder_mode_local(tmp_path, capsys):
    src = tmp_path / "Triage"
    src.mkdir()
    dest = tmp_path / "Photos"
    dest.mkdir()
    _jpg(src / "IMG_0001.JPG")
    code = import_folder.main([str(src), "--dest", str(dest)])
    assert code == 0
    assert (dest / "2024" / "07" / "IMG_0001.JPG").exists()
    assert "Terminé : 1 rangé(s)" in capsys.readouterr().out


def test_import_folder_source_absente(tmp_path):
    with pytest.raises(SystemExit, match="n'existe pas"):
        import_folder.main([str(tmp_path / "absent"), "--dest", str(tmp_path)])


def test_import_folder_dry_run_ne_deplace_pas(tmp_path):
    src = tmp_path / "Triage"
    src.mkdir()
    dest = tmp_path / "Photos"
    dest.mkdir()
    f = src / "IMG_0001.JPG"
    _jpg(f)
    code = import_folder.main([str(src), "--dest", str(dest), "--dry-run"])
    assert code == 0
    assert f.exists() and list(dest.rglob("*")) == []


def test_import_folder_webdav_sans_identifiants(tmp_path, monkeypatch):
    src = tmp_path / "Triage"
    src.mkdir()
    _jpg(src / "IMG_0001.JPG")
    for var in ("NC_URL", "NC_USER", "NC_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SystemExit, match="NC_URL"):
        import_folder.main([str(src), "--webdav", "https://cloud.example.org/dav"])


def test_from_phone_aucun_telephone_monte(monkeypatch):
    monkeypatch.setattr(from_phone.glob, "glob", lambda motif: [])
    with pytest.raises(SystemExit, match="Aucun téléphone monté"):
        from_phone.main([])


def test_from_phone_trouve_montage_gphoto2(monkeypatch):
    monkeypatch.setattr(
        from_phone.glob,
        "glob",
        lambda motif: (
            ["/run/user/1000/gvfs/gphoto2:host=Apple Inc._iPhone de X"]
            if "gphoto2" in motif
            else []
        ),
    )
    assert from_phone.trouver_montage(uid=1000) == from_phone.Path(
        "/run/user/1000/gvfs/gphoto2:host=Apple Inc._iPhone de X"
    )


def test_from_phone_trouve_montage_mtp(monkeypatch):
    def faux_glob(motif):
        if "mtp" in motif:
            return ["/run/user/1000/gvfs/mtp:host=samsung_Galaxy"]
        return []

    monkeypatch.setattr(from_phone.glob, "glob", faux_glob)
    assert from_phone.trouver_montage(uid=1000) == from_phone.Path(
        "/run/user/1000/gvfs/mtp:host=samsung_Galaxy"
    )


def _faux_lsjson(drive_entries, nc_entries):
    def faux(remote, chemin):
        return drive_entries if remote == "drive" else nc_entries

    return faux


def test_migrate_gdrive_dry_run_plan_et_doublons(monkeypatch, capsys):
    drive = [
        {"Path": "a.jpg", "Size": 10, "ModTime": "2024-07-15T10:30:00Z", "IsDir": False},
        {"Path": "sous/b.jpg", "Size": 20, "ModTime": "2023-01-05T08:00:00Z", "IsDir": False},
        {"Path": "video.MTS", "Size": 30, "ModTime": "2008-06-01T12:00:00Z", "IsDir": False},
        {"Path": "son.wav", "Size": 40, "ModTime": "2008-07-02T12:00:00Z", "IsDir": False},
        {"Path": "doc.txt", "Size": 5, "ModTime": "2024-01-01T00:00:00Z", "IsDir": False},
        {"Path": "dossier", "IsDir": True},
    ]
    nc = [{"Path": "2024/07/a.jpg", "Size": 10, "IsDir": False}]
    monkeypatch.setattr(rclone, "lsjson", _faux_lsjson(drive, nc))
    code = migrate_gdrive.main(["--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "[doublon] a.jpg" in out  # même nom + même taille = déjà migré
    assert "[plan] b.jpg -> 2023/01" in out
    assert "[plan] video.MTS -> 2008/06" in out  # .mts pris en charge
    assert "[plan] son.wav -> 2008/07" in out  # .wav pris en charge
    assert "doc.txt" not in out  # extension non gérée
    assert "4 fichier(s) photo/vidéo/son à traiter" in out


def test_migrate_gdrive_dry_run_dossier_nc_absent(monkeypatch, capsys):
    def faux_lsjson(remote, chemin):
        if remote == "drive":
            return [
                {"Path": "a.jpg", "Size": 10, "ModTime": "2024-07-15T10:30:00Z", "IsDir": False}
            ]
        raise rclone.RcloneError("dossier inexistant")

    monkeypatch.setattr(rclone, "lsjson", faux_lsjson)
    code = migrate_gdrive.main(["--dry-run"])
    assert code == 0
    assert "[plan] a.jpg -> 2024/07" in capsys.readouterr().out


def test_migrate_gdrive_limit(monkeypatch, capsys):
    drive = [
        {"Path": f"f{i}.jpg", "Size": i, "ModTime": "2024-07-15T10:30:00Z", "IsDir": False}
        for i in range(10)
    ]
    monkeypatch.setattr(rclone, "lsjson", _faux_lsjson(drive, []))
    code = migrate_gdrive.main(["--dry-run", "--limit", "3"])
    assert code == 0
    out = capsys.readouterr().out
    assert "3 fichier(s) photo/vidéo/son à traiter" in out
    assert "[plan] f2.jpg" in out and "[plan] f3.jpg" not in out


def test_migrate_gdrive_aucune_photo(monkeypatch):
    monkeypatch.setattr(rclone, "lsjson", _faux_lsjson([], []))
    with pytest.raises(SystemExit, match="Aucune photo trouvée"):
        migrate_gdrive.main([])


def test_migrate_upload_echec_affiche_stderr_rclone(monkeypatch, capsys):
    drive = [
        {"Path": "a.jpg", "Size": 10, "ModTime": "2024-07-15T10:30:00Z", "IsDir": False}
    ]
    monkeypatch.setattr(rclone, "lsjson", _faux_lsjson(drive, []))

    def faux_cat(remote, chemin, dest):
        dest.write(b"faux contenu jpg")

    def faux_copyto(local, remote, chemin):
        raise rclone.RcloneError("rclone copyto vers nc:Photos/2024/07/a.jpg : HTTP 403 Forbidden")

    monkeypatch.setattr(rclone, "cat", faux_cat)
    monkeypatch.setattr(rclone, "mkdir", lambda remote, chemin: None)
    monkeypatch.setattr(rclone, "copyto", faux_copyto)
    code = migrate_gdrive.main([])
    assert code == 1
    out = capsys.readouterr().out
    assert "[erreur] a.jpg" in out and "403 Forbidden" in out
    assert "1 erreur(s)" in out


def test_migrate_upload_ok_puis_doublon_au_relance(monkeypatch, capsys):
    drive = [
        {"Path": "a.jpg", "Size": 10, "ModTime": "2024-07-15T10:30:00Z", "IsDir": False}
    ]
    nc_vide = []
    monkeypatch.setattr(rclone, "lsjson", _faux_lsjson(drive, nc_vide))
    envoyes = []

    def faux_cat(remote, chemin, dest):
        dest.write(b"faux contenu jpg")

    def faux_copyto(local, remote, chemin):
        envoyes.append(chemin)

    monkeypatch.setattr(rclone, "cat", faux_cat)
    monkeypatch.setattr(rclone, "mkdir", lambda remote, chemin: None)
    monkeypatch.setattr(rclone, "copyto", faux_copyto)
    assert migrate_gdrive.main([]) == 0
    assert envoyes == ["Photos/2024/07/a.jpg"]
    assert "[ok] a.jpg -> 2024/07/a.jpg" in capsys.readouterr().out

    # Relance : le fichier est dans l'index (même nom + même taille) -> doublon
    nc_plein = [{"Path": "2024/07/a.jpg", "Size": 10, "IsDir": False}]
    monkeypatch.setattr(rclone, "lsjson", _faux_lsjson(drive, nc_plein))
    assert migrate_gdrive.main([]) == 0
    out = capsys.readouterr().out
    assert "[doublon] a.jpg" in out and envoyes == ["Photos/2024/07/a.jpg"]
