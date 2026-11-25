"""Tests des wrappers rclone (subprocess mocké, pas de binaire rclone requis)."""

import json
import subprocess
from pathlib import Path

import pytest

from photos_importer import rclone


def test_lsjson_ok(monkeypatch):
    def faux_run(cmd, **kwargs):
        assert cmd[:3] == ["rclone", "lsjson", "drive:Photos"]
        assert "--recursive" in cmd
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps([{"Path": "a.jpg", "Size": 10, "ModTime": "2024-07-15T10:30:00Z"}]),
            stderr="",
        )

    monkeypatch.setattr(rclone.subprocess, "run", faux_run)
    entrees = rclone.lsjson("drive", "Photos")
    assert entrees[0]["Path"] == "a.jpg"


def test_lsjson_echec_leve_rcloneerror_avec_stderr(monkeypatch):
    monkeypatch.setattr(
        rclone.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom 401"),
    )
    with pytest.raises(rclone.RcloneError, match="boom 401"):
        rclone.lsjson("drive", "Photos")


def test_lsjson_sortie_vide(monkeypatch):
    monkeypatch.setattr(
        rclone.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
    )
    assert rclone.lsjson("nc", "Photos") == []


def test_cat_ecrit_dans_le_flux(tmp_path, monkeypatch):
    def faux_run(cmd, stdout=None, stderr=None, **kwargs):
        assert cmd == ["rclone", "cat", "drive:Photos/a.jpg"]
        stdout.write("contenu streamé".encode())
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(rclone.subprocess, "run", faux_run)
    dest = tmp_path / "out.bin"
    with open(dest, "wb") as f:
        rclone.cat("drive", "Photos/a.jpg", f)  # succès : ne lève rien, retourne None
    assert dest.read_bytes() == "contenu streamé".encode()


def test_cat_echec_leve_avec_stderr(tmp_path, monkeypatch):
    monkeypatch.setattr(
        rclone.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 1, stderr=b"not found"),
    )
    with open(tmp_path / "out.bin", "wb") as f:
        with pytest.raises(rclone.RcloneError, match="not found"):
            rclone.cat("drive", "Photos/a.jpg", f)


def test_mkdir_et_copyto_levent_avec_stderr(monkeypatch):
    def faux_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stderr=b"HTTP 403 Forbidden")

    monkeypatch.setattr(rclone.subprocess, "run", faux_run)
    with pytest.raises(rclone.RcloneError, match="403"):
        rclone.mkdir("nc", "Photos/2024/07")
    with pytest.raises(rclone.RcloneError, match="403"):
        rclone.copyto(Path("/tmp/x.jpg"), "nc", "Photos/2024/07/x.jpg")


def test_mkdir_et_copyto_ok(monkeypatch):
    monkeypatch.setattr(
        rclone.subprocess,
        "run",
        lambda cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, stderr=b""),
    )
    assert rclone.mkdir("nc", "Photos/2024/07") is None
    assert rclone.copyto(Path("/tmp/x.jpg"), "nc", "Photos/2024/07/x.jpg") is None
