"""Wrappers subprocess autour de rclone : lsjson / cat / mkdir / copyto.

Toutes les fonctions lèvent RcloneError en cas d'échec, avec la sortie stderr
de rclone tronquée dans le message (pour rendre les erreurs WebDAV lisibles).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import BinaryIO


class RcloneError(RuntimeError):
    """Échec d'une commande rclone (message enrichi de la stderr)."""


def _stderr(resultat: subprocess.CompletedProcess) -> str:
    """Extrait la stderr (bytes ou str) d'un CompletedProcess, aplatie, tronquée à 300 car."""
    err = resultat.stderr or ""
    if isinstance(err, bytes):
        err = err.decode(errors="replace")
    return " ".join(err.split())[:300]


def lsjson(remote: str, chemin: str) -> list[dict]:
    """Listing récursif d'un remote rclone, comme liste de dictionnaires.

    Aucun contenu n'est téléchargé à ce stade. Lève RcloneError si échec.
    """
    cmd = ["rclone", "lsjson", f"{remote}:{chemin}", "--recursive"]
    resultat = subprocess.run(cmd, capture_output=True, text=True)
    if resultat.returncode != 0:
        raise RcloneError(f"rclone lsjson {remote}:{chemin} a échoué : {_stderr(resultat)}")
    return json.loads(resultat.stdout or "[]")


def cat(remote: str, chemin: str, destination: BinaryIO) -> None:
    """Télécharge un fichier du remote vers un descripteur ouvert en écriture.

    Le flux est streamé vers le disque : jamais de chargement en RAM.
    Lève RcloneError si le téléchargement échoue.
    """
    resultat = subprocess.run(
        ["rclone", "cat", f"{remote}:{chemin}"],
        stdout=destination,
        stderr=subprocess.PIPE,
    )
    if resultat.returncode != 0:
        raise RcloneError(f"rclone cat {remote}:{chemin} : {_stderr(resultat)}")


def mkdir(remote: str, chemin: str) -> None:
    """Crée un dossier distant (idempotent : « existe déjà » est un succès).

    Lève RcloneError si la création échoue vraiment.
    """
    resultat = subprocess.run(["rclone", "mkdir", f"{remote}:{chemin}"], capture_output=True)
    if resultat.returncode != 0:
        raise RcloneError(f"rclone mkdir {remote}:{chemin} : {_stderr(resultat)}")


def copyto(local: Path, remote: str, chemin: str) -> None:
    """Copie un fichier local vers un chemin distant exact. Lève RcloneError si échec."""
    resultat = subprocess.run(
        ["rclone", "copyto", str(local), f"{remote}:{chemin}"], capture_output=True
    )
    if resultat.returncode != 0:
        raise RcloneError(f"rclone copyto vers {remote}:{chemin} : {_stderr(resultat)}")


def copy(src: str, dst: str, dry_run: bool = False) -> None:
    """Copie récursivement un dossier remote vers un autre (jamais de suppression).

    La sortie de rclone n'est pas capturée : la progression s'affiche en direct
    (utile dans tmux). Idempotent : rclone ignore les fichiers déjà copiés
    (même taille + même modtime). Lève RcloneError si échec.
    """
    cmd = ["rclone", "copy", src, dst, "--create-empty-src-dirs"]
    if dry_run:
        cmd.append("--dry-run")
    resultat = subprocess.run(cmd)
    if resultat.returncode != 0:
        raise RcloneError(f"rclone copy {src} -> {dst} a échoué (code {resultat.returncode})")
