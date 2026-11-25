"""Tests du module config : fichier env et résolution des identifiants."""

import pytest

from photos_importer.config import ConfigError, charger_env, identifiants


def _env(tmp_path, contenu: str, mode: int = 0o600):
    f = tmp_path / "photos-nextcloud.env"
    f.write_text(contenu, encoding="utf-8")
    f.chmod(mode)
    return f


def test_charger_env_complet(tmp_path):
    f = _env(
        tmp_path,
        "# commentaire\n"
        "NC_URL=https://cloud.example.org/remote.php/dav/files/thomas\n"
        'NC_USER=thomas\n'
        'NC_TOKEN="tok-123"\n'
        "\n",
    )
    env = charger_env(f)
    assert env == {
        "NC_URL": "https://cloud.example.org/remote.php/dav/files/thomas",
        "NC_USER": "thomas",
        "NC_TOKEN": "tok-123",
    }


def test_charger_env_absent(tmp_path):
    with pytest.raises(ConfigError, match="introuvable"):
        charger_env(tmp_path / "absent.env")


def test_charger_env_incomplet(tmp_path):
    f = _env(tmp_path, "NC_URL=https://x\n")
    with pytest.raises(ConfigError, match="NC_USER"):
        charger_env(f)


def test_charger_env_permissions_trop_larges_warns(tmp_path, capsys):
    f = _env(tmp_path, "NC_URL=u\nNC_USER=n\nNC_TOKEN=t\n", mode=0o644)
    charger_env(f)
    assert "chmod 600" in capsys.readouterr().out


def test_identifiants_cli(monkeypatch):
    for var in ("NC_URL", "NC_USER", "NC_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert identifiants("https://x", "u", "t") == ("https://x", "u", "t")


def test_identifiants_env(monkeypatch):
    monkeypatch.setenv("NC_URL", "https://env")
    monkeypatch.setenv("NC_USER", "eu")
    monkeypatch.setenv("NC_TOKEN", "et")
    assert identifiants(None, None, None) == ("https://env", "eu", "et")
    assert identifiants("https://cli", None, None) == ("https://cli", "eu", "et")


def test_identifiants_manquants(monkeypatch):
    for var in ("NC_URL", "NC_USER", "NC_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ConfigError, match="NC_URL"):
        identifiants(None, None, None)
