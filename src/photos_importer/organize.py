"""Rangement d'un dossier de triage dans Photos/YYYY/MM, en local ou via WebDAV.

Invariants : la source locale n'est supprimée qu'après un upload confirmé ;
en mode local, déduplication par empreinte SHA-256 ; en mode WebDAV,
déduplication par nom (les noms de pellicule type IMG_xxxx sont uniques).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .dates import EXTS_IMAGES, EXTS_VIDEOS, HEIC_OK, chemin_yyyy_mm, date_prise
from .dedup import empreinte_sha256, nom_unique
from .nextcloud_dav import NextcloudWebDAV


@dataclass
class Compteurs:
    """Compteurs de traitement d'un lot de fichiers."""

    ranges: int = 0
    doublons: int = 0
    ignores: int = 0
    erreurs: int = 0

    def resume(self) -> str:
        """Ligne de bilan en français."""
        return (
            f"Terminé : {self.ranges} rangé(s), {self.doublons} doublon(s), "
            f"{self.ignores} ignoré(s), {self.erreurs} erreur(s)."
        )


def est_media(chemin: Path) -> bool:
    """Vrai si l'extension est une image ou une vidéo gérée."""
    extension = chemin.suffix.lower()
    return extension in EXTS_IMAGES or extension in EXTS_VIDEOS


def avertir_heic(fichiers: Iterable[Path]) -> None:
    """Avertit si des HEIC sont présents sans pillow-heif (avertissement, pas de crash)."""
    if any(p.suffix.lower() in (".heic", ".heif") for p in fichiers) and not HEIC_OK:
        print("Attention : des HEIC détectés et pillow-heif absent (pip install pillow-heif).")


def ranger_local(
    fichiers: Sequence[Path], dest_racine: Path, deplacer: bool, dry_run: bool
) -> Compteurs:
    """Mode local : copie/déplacement dans dest_racine/YYYY/MM.

    Dédup par SHA-256 : contenu identique = doublon (la source est supprimée
    en mode déplacement) ; nom identique mais contenu différent = suffixe _1, _2…
    """
    compteur = Compteurs()
    for chemin in fichiers:
        if not est_media(chemin):
            print(f"[ignoré]  {chemin.name} (extension non gérée)")
            compteur.ignores += 1
            continue
        date = date_prise(chemin)
        dossier = dest_racine / chemin_yyyy_mm(date)
        cible = dossier / chemin.name

        if cible.exists():
            if empreinte_sha256(chemin) == empreinte_sha256(cible):
                print(f"[doublon] {chemin.name} — déjà présent dans {dossier}")
                compteur.doublons += 1
                if deplacer and not dry_run:
                    chemin.unlink()
                continue
            cible = dossier / nom_unique(chemin.name, lambda n, d=dossier: (d / n).exists())

        print(f"[ok]      {chemin.name} -> {cible.relative_to(dest_racine)}")
        if not dry_run:
            try:
                dossier.mkdir(parents=True, exist_ok=True)
                if deplacer:
                    shutil.move(str(chemin), str(cible))
                else:
                    shutil.copy2(str(chemin), str(cible))
                compteur.ranges += 1
            except OSError as e:
                print(f"[erreur]  {chemin.name} : {e}")
                compteur.erreurs += 1
        else:
            compteur.ranges += 1
    return compteur


def ranger_webdav(
    fichiers: Sequence[Path],
    dav: NextcloudWebDAV,
    racine_distante: str,
    supprimer_apres: bool,
    dry_run: bool,
) -> Compteurs:
    """Mode WebDAV : upload dans racine_distante/YYYY/MM.

    Dédup par nom. Le fichier local n'est supprimé qu'après un upload confirmé
    (201/204).
    """
    compteur = Compteurs()
    for chemin in fichiers:
        if not est_media(chemin):
            print(f"[ignoré]  {chemin.name} (extension non gérée)")
            compteur.ignores += 1
            continue
        date = date_prise(chemin)
        dossier = f"{racine_distante}/{date.year:04d}"
        sous_dossier = f"{dossier}/{date.month:02d}"
        distant = f"{sous_dossier}/{chemin.name}"

        if dav.fichier_existe(distant):
            print(f"[doublon] {chemin.name} — déjà présent à distance")
            compteur.doublons += 1
            if supprimer_apres and not dry_run:
                chemin.unlink()
            continue

        print(f"[upload]  {chemin.name} -> {sous_dossier}/")
        if not dry_run:
            try:
                dav.creer_dossier(dossier)
                dav.creer_dossier(sous_dossier)
                if dav.envoyer(chemin, distant):
                    if supprimer_apres:
                        chemin.unlink()
                    compteur.ranges += 1
                else:
                    print(f"[erreur]  {chemin.name} : échec de l'upload")
                    compteur.erreurs += 1
            except Exception as e:
                print(f"[erreur]  {chemin.name} : {e}")
                compteur.erreurs += 1
        else:
            compteur.ranges += 1
    return compteur
