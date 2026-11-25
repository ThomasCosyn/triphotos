"""Wrappers subprocess autour de rclone : lsjson / cat / mkdir / copyto."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import BinaryIO


class RcloneError(RuntimeError):
    """Échec d'une commande rclone."""


def lsjson(remote: str, chemin: str) -> list[dict]:
    """Listing récursif d'un remote rclone, comme liste de dictionnaires.

    Aucun contenu n'est téléchargé à ce stade.
    """
    cmd = ["rclone", "lsjson", f"{remote}:{chemin}", "--recursive"]
    resultat = subprocess.run(cmd, capture_output=True, text=True)
    if resultat.returncode != 0:
        raise RcloneError(f"rclone a échoué : {' '.join(cmd)}\n{resultat.stderr}")
    return json.loads(resultat.stdout or "[]")


def cat(remote: str, chemin: str, destination: BinaryIO) -> bool:
    """Télécharge un fichier du remote vers un descripteur ouvert en écriture.

    Le flux est streamé vers le disque : jamais de chargement en RAM.
    """
    resultat = subprocess.run(
        ["rclone", "cat", f"{remote}:{chemin}"],
        stdout=destination,
        stderr=subprocess.PIPE,
    )
    return resultat.returncode == 0


def mkdir(remote: str, chemin: str) -> bool:
    """Crée un dossier distant (idempotent : « existe déjà » est un succès)."""
    resultat = subprocess.run(["rclone", "mkdir", f"{remote}:{chemin}"], capture_output=True)
    return resultat.returncode == 0


def copyto(local: Path, remote: str, chemin: str) -> bool:
    """Copie un fichier local vers un chemin distant exact."""
    return subprocess.run(
        ["rclone", "copyto", str(local), f"{remote}:{chemin}"], capture_output=True
    ).returncode == 0
