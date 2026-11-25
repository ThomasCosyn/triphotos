"""photos-copy-folder — copie un dossier Google Drive tel quel vers Nextcloud.

Contrairement à photos-migrate-gdrive (tri par date dans Photos/YYYY/MM),
ici le dossier est recopié **tel quel**, avec sa structure, vers la racine
des Fichiers Nextcloud (ou un sous-dossier avec --dest). Idempotent : rclone
ignore les fichiers déjà copiés (même taille + même modtime). Aucune
suppression des deux côtés (rclone copy, jamais sync --delete).
"""

from __future__ import annotations

import argparse
import sys

from .. import logs_temps_reel, rclone


def construire_parseur() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments de la commande."""
    parseur = argparse.ArgumentParser(
        prog="photos-copy-folder",
        description="Copie un dossier Google Drive tel quel vers Nextcloud "
        "(racine des Fichiers, ou --dest), sans tri par date. Idempotent.",
    )
    parseur.add_argument(
        "--drive-remote",
        default="drive",
        help="nom du remote rclone Google Drive (défaut : drive)",
    )
    parseur.add_argument(
        "--nc-remote",
        default="nc",
        help="nom du remote rclone Nextcloud WebDAV (défaut : nc)",
    )
    parseur.add_argument(
        "--source",
        required=True,
        help="dossier dans le Drive (ex. : Travail, '2015 ski', Photos)",
    )
    parseur.add_argument(
        "--dest",
        default=None,
        help="dossier cible côté Nextcloud (défaut : le nom de --source, "
        "à la racine de tes Fichiers)",
    )
    parseur.add_argument(
        "--dry-run",
        action="store_true",
        help="simulation : rclone affiche ce qui serait copié, sans rien faire",
    )
    return parseur


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée console. Code de sortie 1 si erreur, 0 sinon."""
    logs_temps_reel()
    args = construire_parseur().parse_args(argv)

    source = args.source.rstrip("/")
    dest = (args.dest or source).rstrip("/")
    src = f"{args.drive_remote}:{source}"
    dst = f"{args.nc_remote}:{dest}"

    print(
        f"Copie de {src} vers {dst}"
        + ("  (SIMULATION)" if args.dry_run else "")
        + " — les fichiers déjà présents (même taille + modtime) sont ignorés."
    )
    try:
        rclone.copy(src, dst, dry_run=args.dry_run)
    except rclone.RcloneError as e:
        print(f"[erreur] {e}")
        return 1
    print(f"Terminé : {src} -> {dst}" + (" (simulation)" if args.dry_run else "."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
