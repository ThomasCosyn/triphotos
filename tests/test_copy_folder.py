"""Tests de la commande photos-copy-folder (subprocess rclone mocké)."""

import subprocess

import pytest

from photos_importer import rclone
from photos_importer.cli import copy_folder


def _capture_run(monkeypatch, code=0):
    captured = {}

    def faux_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, code)

    monkeypatch.setattr(rclone.subprocess, "run", faux_run)
    return captured


def test_copy_dest_par_defaut_egale_source(monkeypatch, capsys):
    captured = _capture_run(monkeypatch)
    code = copy_folder.main(
        ["--drive-remote", "gdrive", "--nc-remote", "nextcloud", "--source", "Travail"]
    )
    assert code == 0
    assert captured["cmd"] == [
        "rclone", "copy", "gdrive:Travail", "nextcloud:Travail", "--create-empty-src-dirs"
    ]
    assert "gdrive:Travail -> nextcloud:Travail" in capsys.readouterr().out


def test_copy_dest_explicite_dry_run_nom_avec_espaces(monkeypatch):
    captured = _capture_run(monkeypatch)
    code = copy_folder.main(
        [
            "--drive-remote", "gdrive",
            "--source", "2015 ski",
            "--dest", "Documents/2015 ski",
            "--dry-run",
        ]
    )
    assert code == 0
    assert captured["cmd"] == [
        "rclone", "copy", "gdrive:2015 ski", "nc:Documents/2015 ski",
        "--create-empty-src-dirs", "--dry-run",
    ]


def test_copy_echec_retourne_1(monkeypatch, capsys):
    _capture_run(monkeypatch, code=1)
    code = copy_folder.main(["--source", "Travail"])
    assert code == 1
    assert "[erreur]" in capsys.readouterr().out


def test_copy_source_requis():
    with pytest.raises(SystemExit):
        copy_folder.main([])
