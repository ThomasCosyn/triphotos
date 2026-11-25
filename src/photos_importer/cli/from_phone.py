"""photos-from-phone — importe les photos d'un iPhone branché en USB.

1. découvre le point de montage GVfs du téléphone
   (/run/user/$UID/gvfs/gphoto2:host=* ou mtp:host=*) ;
2. rsync -rltv --ignore-existing du DCIM vers le dossier de triage
   (rien n'est jamais supprimé du téléphone) ;
3. charge ~/.config/photos-nextcloud.env (chmod 600 : NC_URL, NC_USER, NC_TOKEN)
   puis lance l'upload WebDAV (photos-import-folder).

Prérequis système : libimobiledevice6 libimobiledevice-utils rsync ffmpeg.
Port de import-photos.sh.
"""

from __future__ import annotations

import argparse
import glob
import os
import subprocess
import sys
from pathlib import Path

from ..config import ENV_FILE, ConfigError, charger_env
from . import import_folder

PREREQUIS_APT = "libimobiledevice6 libimobiledevice-utils rsync ffmpeg"


def trouver_montage(uid: int | None = None) -> Path | None:
    """Point de montage GVfs du téléphone (gphoto2:host=* puis mtp:host=*), ou None."""
    uid = uid if uid is not None else os.getuid()
    for motif in (
        f"/run/user/{uid}/gvfs/gphoto2:host=*",
        f"/run/user/{uid}/gvfs/mtp:host=*",
    ):
        trouves = sorted(glob.glob(motif))
        if trouves:
            return Path(trouves[0])
    return None


def rsync_dcim(montage: Path, triage: Path, dry_run: bool) -> None:
    """Copie le DCIM du téléphone vers le dossier de triage (--ignore-existing)."""
    triage.mkdir(parents=True, exist_ok=True)
    cmd = ["rsync", "-rltv", "--ignore-existing", f"{montage}/DCIM/", f"{triage}/"]
    print(f"Copie de {montage}/DCIM/ vers {triage}/ (rien n'est supprimé du téléphone) ...")
    if dry_run:
        print("(SIMULATION) " + " ".join(cmd))
        return
    try:
        resultat = subprocess.run(cmd)
    except FileNotFoundError:
        sys.exit(f"rsync introuvable. Prérequis : sudo apt install {PREREQUIS_APT}")
    if resultat.returncode != 0:
        sys.exit(
            f"rsync a échoué (code {resultat.returncode}). "
            f"Prérequis : sudo apt install {PREREQUIS_APT}"
        )


def construire_parseur() -> argparse.ArgumentParser:
    """Construit le parseur d'arguments de la commande."""
    parseur = argparse.ArgumentParser(
        prog="photos-from-phone",
        description="iPhone branché en USB -> copie du DCIM vers le dossier de triage, "
        "puis upload WebDAV dans Nextcloud (Photos/YYYY/MM).",
    )
    parseur.add_argument(
        "--triage",
        type=Path,
        default=Path.home() / "Triage",
        help="dossier de triage local (défaut : ~/Triage)",
    )
    parseur.add_argument(
        "--env",
        type=Path,
        default=ENV_FILE,
        help="fichier d'environnement (défaut : ~/.config/photos-nextcloud.env)",
    )
    parseur.add_argument(
        "--remote-dir",
        default="Photos",
        help="dossier racine distant Nextcloud (défaut : Photos)",
    )
    parseur.add_argument(
        "--copy",
        action="store_true",
        help="ne pas supprimer les fichiers du triage après upload",
    )
    parseur.add_argument(
        "--dry-run", action="store_true", help="simulation : affiche sans rien faire"
    )
    return parseur


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée console. Code de sortie 1 si des erreurs, 0 sinon."""
    args = construire_parseur().parse_args(argv)

    montage = trouver_montage()
    if montage is None:
        sys.exit(
            "Aucun téléphone monté : branche l'iPhone (déverrouillé, « Faire confiance » "
            "validé) puis relance.\nPoints de montage cherchés : "
            "/run/user/$UID/gvfs/gphoto2:host=* et /run/user/$UID/gvfs/mtp:host=*"
        )
    print(f"Téléphone détecté : {montage}")

    rsync_dcim(montage, args.triage, args.dry_run)

    try:
        env = charger_env(args.env)
    except ConfigError as e:
        sys.exit(str(e))

    return import_folder.main(
        [
            str(args.triage),
            "--webdav",
            env["NC_URL"],
            "--remote-dir",
            args.remote_dir,
            "--user",
            env["NC_USER"],
            "--token",
            env["NC_TOKEN"],
            *(["--copy"] if args.copy else []),
            *(["--dry-run"] if args.dry_run else []),
        ]
    )


if __name__ == "__main__":
    sys.exit(main())
