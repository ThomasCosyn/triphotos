"""Déduplication : empreintes SHA-256, suffixes de collision, index nom -> tailles."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

TAILLE_BLOC = 1 << 20  # lecture par blocs de 1 Mio : les gros fichiers passent en streaming


def empreinte_sha256(chemin: Path) -> str:
    """Empreinte SHA-256 du contenu d'un fichier (mode local : détection des doublons)."""
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(TAILLE_BLOC), b""):
            h.update(bloc)
    return h.hexdigest()


def nom_unique(nom: str, existe: Callable[[str], bool]) -> str:
    """Retourne ``nom`` s'il est libre, sinon « nom_1.ext », « nom_2.ext », ...

    ``existe`` teste si un fichier portant ce nom est déjà présent (localement
    ou dans l'index distant).
    """
    if not existe(nom):
        return nom
    p = Path(nom)
    compteur = 1
    while existe(f"{p.stem}_{compteur}{p.suffix}"):
        compteur += 1
    return f"{p.stem}_{compteur}{p.suffix}"


class IndexNomTailles:
    """Index des fichiers déjà présents côté destination : nom -> tailles connues.

    Un fichier de même nom ET même taille est considéré comme déjà migré ;
    un nom occupé par un contenu différent reçoit un suffixe.
    """

    def __init__(self) -> None:
        self._index: dict[str, set[int]] = {}

    def ajouter(self, nom: str, taille: int) -> None:
        """Enregistre un fichier présent (nom, taille)."""
        self._index.setdefault(nom, set()).add(taille)

    def contient(self, nom: str, taille: int) -> bool:
        """Vrai si un fichier de même nom et même taille existe déjà (doublon)."""
        return taille in self._index.get(nom, set())

    def nom_pris(self, nom: str) -> bool:
        """Vrai si le nom est déjà occupé (par n'importe quelle taille)."""
        return nom in self._index

    def __len__(self) -> int:
        return len(self._index)
