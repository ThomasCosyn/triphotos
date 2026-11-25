"""Configuration : fichier env (~/.config/photos-nextcloud.env) et variables d'env.

Le fichier env contient les identifiants WebDAV de Nextcloud et ne doit jamais
être commité : permissions 600 (chmod 600), mot de passe d'application et non
mot de passe principal.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

ENV_FILE = Path.home() / ".config" / "photos-nextcloud.env"
CLES = ("NC_URL", "NC_USER", "NC_TOKEN")


class ConfigError(RuntimeError):
    """Configuration invalide (fichier env manquant, incomplet, ou identifiants absents)."""


def charger_env(chemin: Path = ENV_FILE) -> dict[str, str]:
    """Charge un fichier « KEY=VALUE » (commentaires « # » et lignes vides ignorés).

    Lève ConfigError si le fichier est absent ou si une clé manque. Avertit si
    le fichier est lisible par d'autres utilisateurs (chmod 600 recommandé).
    """
    if not chemin.is_file():
        raise ConfigError(
            f"Fichier {chemin} introuvable (voir README : création du fichier env)."
        )
    mode = chemin.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print(
            f"Attention : {chemin} est lisible par d'autres utilisateurs "
            "(chmod 600 recommandé, il contient des secrets)."
        )
    valeurs: dict[str, str] = {}
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        valeurs[cle.strip()] = valeur.strip().strip('"').strip("'")
    manquants = [cle for cle in CLES if not valeurs.get(cle)]
    if manquants:
        raise ConfigError(f"{chemin} : variable(s) manquante(s) : {', '.join(manquants)}")
    return {cle: valeurs[cle] for cle in CLES}


def identifiants(
    url_cli: str | None, user_cli: str | None, token_cli: str | None
) -> tuple[str, str, str]:
    """Résout (URL, utilisateur, token) : option CLI > variable d'environnement.

    Lève ConfigError si l'un des trois est absent.
    """
    url = url_cli or os.environ.get("NC_URL")
    user = user_cli or os.environ.get("NC_USER")
    token = token_cli or os.environ.get("NC_TOKEN")
    if not url or not user or not token:
        raise ConfigError(
            "Mode WebDAV : NC_URL (--webdav), NC_USER (--user) et NC_TOKEN (--token) requis.\n"
            "Astuce : crée un mot de passe d'application dans "
            "Réglages -> Sécurité -> Nom de l'appareil."
        )
    return url, user, token
