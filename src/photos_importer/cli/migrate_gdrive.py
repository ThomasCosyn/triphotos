"""photos-migrate-gdrive — migre Google Drive vers Nextcloud (Photos/YYYY/MM).

Deux remotes rclone configurés à l'avance : « drive » (scope read-only) et
« nc » (webdav Nextcloud). Un seul fichier temporaire à la fois : la migration
est relançable, elle reprend où elle s'était arrêtée. Port de
gdrive_vers_nextcloud.py.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .. import rclone
from ..dates import EXTS_AUDIO, EXTS_IMAGES, EXTS_VIDEOS, HEIC_OK, date_modtime_rfc3339, date_prise
from ..dedup import IndexNomTailles, nom_unique


def construire_parseur() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments de la commande."""
    parseur = argparse.ArgumentParser(
        prog="photos-migrate-gdrive",
        description="Migre les photos de Google Drive vers Nextcloud, "
        "rangées par date de prise de vue dans Photos/YYYY/MM.",
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
        "--source", default="Photos", help="dossier source dans le Drive (défaut : Photos)"
    )
    parseur.add_argument(
        "--dest",
        default="Photos",
        help="dossier racine distant Nextcloud (défaut : Photos)",
    )
    parseur.add_argument(
        "--limit", type=int, default=0, help="ne traiter que les N premiers fichiers (essai)"
    )
    parseur.add_argument(
        "--dry-run",
        action="store_true",
        help="simulation : affiche le plan sans rien télécharger "
        "(dates estimées = modtime Drive, car l'EXIF exige le contenu)",
    )
    return parseur


def lister_candidats(drive_remote: str, source: str) -> list[dict]:
    """Liste les photos/vidéos du Drive (métadonnées seules, aucun téléchargement)."""
    candidats = []
    for e in rclone.lsjson(drive_remote, source):
        if e.get("IsDir"):
            continue
        extension = Path(e["Path"]).suffix.lower()
        if extension in EXTS_IMAGES or extension in EXTS_VIDEOS or extension in EXTS_AUDIO:
            candidats.append(
                {
                    "chemin": e["Path"],
                    "taille": e["Size"],
                    "modtime": e["ModTime"],
                    "ext": extension,
                }
            )
    return candidats


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée console. Code de sortie 1 si des erreurs, 0 sinon."""
    args = construire_parseur().parse_args(argv)

    print(f"Listing de {args.drive_remote}:{args.source} ...")
    candidats = lister_candidats(args.drive_remote, args.source)
    if not candidats:
        sys.exit(
            "Aucune photo trouvée. Vérifie --source (ex. : Photos, ou / pour tout le Drive)."
        )
    if args.limit:
        candidats = candidats[: args.limit]
    total = len(candidats)
    print(f"{total} fichier(s) photo/vidéo/son à traiter.")

    if any(c["ext"] in (".heic", ".heif") for c in candidats) and not HEIC_OK:
        print("Attention : des HEIC détectés et pillow-heif absent (pip install pillow-heif).")

    # Index de ce qui existe déjà côté Nextcloud : nom -> tailles connues
    print(f"Listing de {args.nc_remote}:{args.dest} ...")
    try:
        existants = rclone.lsjson(args.nc_remote, args.dest)
    except rclone.RcloneError as e:
        print(f"(dossier distant absent ou illisible, index vide : {e})")
        existants = []  # le dossier n'existe pas encore : on part de zéro
    index = IndexNomTailles()
    for e in existants:
        if not e.get("IsDir"):
            index.ajouter(Path(e["Path"]).name, e["Size"])

    # Boucle de migration : un seul fichier temporaire à la fois
    deja, migres, erreurs = 0, 0, 0
    dossiers_crees: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="mig-") as tmpdir:
        for i, f in enumerate(candidats, 1):
            nom = Path(f["chemin"]).name

            # Déjà migré ? (même nom, même taille)
            if index.contient(nom, f["taille"]):
                print(f"[{i}/{total}] [doublon] {nom}")
                deja += 1
                continue

            # Nom occupé par un autre contenu : on suffixe
            cible = nom_unique(nom, index.nom_pris)
            tmp = Path(tmpdir) / f"fichier{f['ext'] or ''}"

            if args.dry_run:
                date = date_modtime_rfc3339(f["modtime"]) or datetime.now()
                print(
                    f"[{i}/{total}] [plan] {nom} -> {date.year:04d}/{date.month:02d}"
                    "  (date estimée : modtime Drive)"
                )
                migres += 1
                continue

            try:
                with open(tmp, "wb") as sortant:
                    rclone.cat(args.drive_remote, f"{args.source}/{f['chemin']}", sortant)
            except rclone.RcloneError as e:
                print(f"[{i}/{total}] [erreur] {nom} : téléchargement impossible : {e}")
                erreurs += 1
                continue

            date = date_prise(tmp, modtime=f["modtime"])
            sous_dossier = f"{args.dest}/{date.year:04d}/{date.month:02d}"

            if sous_dossier not in dossiers_crees:
                try:
                    rclone.mkdir(args.nc_remote, sous_dossier)
                    dossiers_crees.add(sous_dossier)  # existait déjà : OK aussi
                except rclone.RcloneError as e:
                    print(f"[{i}/{total}] [attention] mkdir {sous_dossier} : {e}")

            try:
                rclone.copyto(tmp, args.nc_remote, f"{sous_dossier}/{cible}")
            except rclone.RcloneError as e:
                print(f"[{i}/{total}] [erreur] {nom} : échec de l'upload : {e}")
                erreurs += 1
                tmp.unlink(missing_ok=True)
                continue
            index.ajouter(cible, f["taille"])
            print(f"[{i}/{total}] [ok] {nom} -> {date.year:04d}/{date.month:02d}/{cible}")
            migres += 1

            tmp.unlink(missing_ok=True)  # libère la place avant le fichier suivant

    print(f"\nTerminé : {migres} migré(s), {deja} déjà présent(s), {erreurs} erreur(s).")
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
