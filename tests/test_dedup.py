"""Tests du module dedup : SHA-256, suffixes de collision, index nom -> tailles."""

import hashlib

from photos_importer.dedup import IndexNomTailles, empreinte_sha256, nom_unique


def test_empreinte_sha256(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"contenu de test")
    assert empreinte_sha256(p) == hashlib.sha256(b"contenu de test").hexdigest()


def test_empreinte_sha256_gros_fichier(tmp_path):
    p = tmp_path / "gros.bin"
    p.write_bytes(b"\x00" * (3 * 1024 * 1024 + 7))
    assert empreinte_sha256(p) == hashlib.sha256(b"\x00" * (3 * 1024 * 1024 + 7)).hexdigest()


def test_nom_unique_libre():
    assert nom_unique("IMG_0042.JPG", lambda n: False) == "IMG_0042.JPG"


def test_nom_unique_suffixes(tmp_path):
    dossier = tmp_path
    (dossier / "IMG_0042.JPG").write_bytes(b"a")
    (dossier / "IMG_0042_1.JPG").write_bytes(b"b")
    existe = lambda n: (dossier / n).exists()  # noqa: E731
    assert nom_unique("IMG_0042.JPG", existe) == "IMG_0042_2.JPG"


def test_index_nom_tailles():
    index = IndexNomTailles()
    index.ajouter("a.jpg", 100)
    assert index.contient("a.jpg", 100)
    assert not index.contient("a.jpg", 200)  # même nom, taille différente
    assert not index.contient("b.jpg", 100)
    assert index.nom_pris("a.jpg")
    assert not index.nom_pris("b.jpg")
    assert len(index) == 1
    index.ajouter("a.jpg", 200)
    assert index.contient("a.jpg", 200)
    assert len(index) == 1
