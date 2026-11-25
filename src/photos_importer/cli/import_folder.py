"""photos-import-folder — range un dossier de triage dans Photos/YYYY/MM.

Deux modes : local (--dest) ou WebDAV Nextcloud (--webdav, avec --user/--token
ou les variables NC_URL/NC_USER/NC_TOKEN). Port de range_photos.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ..config import ConfigError, identifiants
from ..organize import avertir_heic, ranger_local, ranger_webdav

try:
    import requests  # noqa: F401

    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False


def construire_parseur() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments de la commande."""
    parseur = argparse.ArgumentParser(
        prog="photos-import-folder",
        description="Range les photos d'un dossier de triage par date de prise de vue, "
        "en local (--dest) ou via WebDAV Nextcloud (--webdav).",
    )
    parseur.add_argument("source", type=Path, help="dossier de triage à vider")
    parseur.add_argument(
        "--dest",
        type=Path,
        default=Path.home() / "Photos",
        help="mode local : dossier racine Photos (défaut : ~/Photos)",
    )
    parseur.add_argument(
        "--webdav",
        nargs="?",
        const=os.environ.get("NC_URL"),
        default=None,
        metavar="URL",
        help="mode WebDAV : URL remote.php/dav/files/<user> (défaut : variable NC_URL)",
    )
    parseur.add_argument(
        "--remote-dir",
        default="Photos",
        help="mode WebDAV : dossier racine distant (défaut : Photos)",
    )
    parseur.add_argument(
        "--user",
        default=os.environ.get("NC_USER"),
        help="mode WebDAV : utilisateur (défaut : variable NC_USER)",
    )
    parseur.add_argument(
        "--token",
        default=os.environ.get("NC_TOKEN"),
        help="mode WebDAV : mot de passe d'application (défaut : variable NC_TOKEN)",
    )
    parseur.add_argument(
        "--copy",
        action="store_true",
        help="copier au lieu de déplacer / ne pas supprimer après upload",
    )
    parseur.add_argument(
        "--dry-run", action="store_true", help="simulation : affiche sans rien faire"
    )
    return parseur


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée console. Code de sortie 1 si des erreurs, 0 sinon."""
    args = construire_parseur().parse_args(argv)

    if not args.source.is_dir():
        sys.exit(f"Le dossier source {args.source} n'existe pas.")

    fichiers = [p for p in args.source.rglob("*") if p.is_file()]
    if not fichiers:
        sys.exit("Aucun fichier dans le dossier de triage.")

    avertir_heic(fichiers)

    if args.webdav:
        if not REQUESTS_OK:
            sys.exit("Le paquet requests est requis en mode WebDAV : pip install requests")
        try:
            url, user, token = identifiants(args.webdav, args.user, args.token)
        except ConfigError as e:
            sys.exit(str(e))
        from ..nextcloud_dav import NextcloudWebDAV

        dav = NextcloudWebDAV(url, user, token)
        # Vérification de connexion dès le départ
        if not dav.dossier_existe(args.remote_dir):
            try:
                dav.creer_dossier(args.remote_dir)
            except RuntimeError as e:
                sys.exit(f"Impossible de joindre ou de créer le dossier distant : {e}")
        print(
            f"Mode WebDAV : {url} (racine distante : {args.remote_dir})"
            + ("  (SIMULATION)" if args.dry_run else "")
        )
        compteur = ranger_webdav(
            fichiers, dav, args.remote_dir, supprimer_apres=not args.copy, dry_run=args.dry_run
        )
    else:
        if not args.dest.is_dir():
            sys.exit(f"Le dossier destination {args.dest} n'existe pas.")
        print(f"Mode local : {args.dest}" + ("  (SIMULATION)" if args.dry_run else ""))
        compteur = ranger_local(
            fichiers, args.dest, deplacer=not args.copy, dry_run=args.dry_run
        )

    print(f"\n{compteur.resume()}")
    return 1 if compteur.erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
