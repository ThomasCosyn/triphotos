#!/usr/bin/env python3
"""
range_photos.py — Range les photos d'un dossier de triage dans Photos/YYYY/MM
selon la date de prise de vue lue dans l'EXIF. Deux modes :

  1. LOCAL   : déplacement/copie dans un dossier local (ex. sur le serveur).
  2. WEBDAV  : upload direct dans Nextcloud via son API WebDAV, sans client
               de synchronisation — idéal quand le dossier Photos est trop
               gros pour être synchronisé.

Exemples :

    # Mode local : ~/Triage -> ~/Photos/2026/10/...
    python3 range_photos.py ~/Triage
    python3 range_photos.py ~/Triage --dest /srv/nextcloud/data/thomas/files/Photos

    # Mode WebDAV : upload dans Photos/YYYY/MM du cloud
    export NC_URL=https://cloud.mondomaine.fr/remote.php/dav/files/thomas
    export NC_USER=thomas
    export NC_TOKEN=xxxx-xxxx-xxxx   # mot de passe d'application (Réglages → Sécurité)
    python3 range_photos.py ~/Triage --webdav
    python3 range_photos.py ~/Triage --webdav --dry-run

Détails :
    - Un fichier distant portant déjà le même nom est considéré comme un
      doublon déjà importé : il est ignoré (les noms IMG_xxxx.HEIC de la
      pellicule sont uniques).
    - Les vidéos (.mp4, .mov…) sont envoyées en streaming : pas de limite de
      mémoire, et les limites d'upload de l'interface web ne s'appliquent pas
      au WebDAV.

Dépendances : pip install Pillow requests
(optionnel, si des HEIC resurgissent : pip install pillow-heif)
"""

import argparse
import hashlib
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

# Support HEIC si la bibliothèque est disponible
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False

EXTS_IMAGES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}
EXTS_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

TAG_DATE_PRISE = 36867   # DateTimeOriginal : date de prise de vue
TAG_DATE_MODIF = 306     # DateTime : dernier enregistrement par l'appareil


# ---------------------------------------------------------------- métadonnées

def date_exif(chemin: Path):
    """Retourne la date de prise de vue lue dans l'EXIF, ou None."""
    try:
        with Image.open(chemin) as img:
            exif = img.getexif()
            brute = exif.get(TAG_DATE_PRISE) or exif.get(TAG_DATE_MODIF)
    except Exception:
        return None
    if not brute:
        return None
    brute = str(brute).strip().strip("\x00")
    try:
        return datetime.strptime(brute, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def date_fichier(chemin: Path):
    """Date de dernière modification du fichier (repli)."""
    return datetime.fromtimestamp(chemin.stat().st_mtime)


def date_du_fichier(chemin: Path):
    if chemin.suffix.lower() in EXTS_IMAGES:
        return date_exif(chemin) or date_fichier(chemin)
    return date_fichier(chemin)


def empreinte(chemin: Path):
    """Empreinte SHA-256 du contenu, pour les doublons en mode local."""
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


# ---------------------------------------------------------------- mode local

def destination_disponible(dossier: Path, nom: str):
    """Si un fichier du même nom existe avec un contenu différent, ajoute un suffixe."""
    cible = dossier / nom
    compteur = 1
    while cible.exists():
        cible = dossier / f"{cible.stem}_{compteur}{cible.suffix}"
        compteur += 1
    return cible


def ranger_local(fichiers, dest_racine: Path, deplacer: bool, dry_run: bool):
    compteur = {"ranges": 0, "doublons": 0, "ignores": 0, "erreurs": 0}
    for chemin in fichiers:
        extension = chemin.suffix.lower()
        if extension not in EXTS_IMAGES and extension not in EXTS_VIDEOS:
            print(f"[ignoré]  {chemin.name} (extension non gérée)")
            compteur["ignores"] += 1
            continue
        date = date_du_fichier(chemin)
        dossier = dest_racine / f"{date.year:04d}" / f"{date.month:02d}"
        cible = dossier / chemin.name

        if cible.exists():
            if empreinte(chemin) == empreinte(cible):
                print(f"[doublon] {chemin.name} — déjà présent dans {dossier}")
                compteur["doublons"] += 1
                if deplacer and not dry_run:
                    chemin.unlink()
                continue
            cible = destination_disponible(dossier, chemin.name)

        print(f"[ok]      {chemin.name} -> {cible.relative_to(dest_racine)}")
        if not dry_run:
            try:
                dossier.mkdir(parents=True, exist_ok=True)
                if deplacer:
                    shutil.move(str(chemin), str(cible))
                else:
                    shutil.copy2(str(chemin), str(cible))
                compteur["ranges"] += 1
            except OSError as e:
                print(f"[erreur]  {chemin.name} : {e}")
                compteur["erreurs"] += 1
        else:
            compteur["ranges"] += 1
    return compteur


# ---------------------------------------------------------------- mode WebDAV

class NextcloudWebDAV:
    """Petit client WebDAV pour l'API fichiers de Nextcloud."""

    def __init__(self, base_url: str, utilisateur: str, token: str):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.auth = (utilisateur, token)
        self.dossiers_crees = set()

    def _url(self, chemin_distant: str) -> str:
        return f"{self.base}/{chemin_distant}"

    def dossier_existe(self, chemin_distant: str) -> bool:
        reponse = self.session.request(
            "PROPFIND", self._url(chemin_distant), headers={"Depth": "0"}
        )
        return reponse.status_code == 207

    def creer_dossier(self, chemin_distant: str):
        if chemin_distant in self.dossiers_crees:
            return
        reponse = self.session.request("MKCOL", self._url(chemin_distant))
        # 201 = créé, 405 = existe déjà : les deux sont OK
        if reponse.status_code not in (201, 405):
            raise RuntimeError(
                f"MKCOL {chemin_distant} : HTTP {reponse.status_code} — {reponse.text[:200]}"
            )
        self.dossiers_crees.add(chemin_distant)

    def fichier_existe(self, chemin_distant: str) -> bool:
        reponse = self.session.request(
            "PROPFIND", self._url(chemin_distant), headers={"Depth": "0"}
        )
        return reponse.status_code == 207

    def envoyer(self, chemin_local: Path, chemin_distant: str) -> bool:
        with open(chemin_local, "rb") as f:
            reponse = self.session.put(self._url(chemin_distant), data=f)
        return reponse.status_code in (201, 204)


def ranger_webdav(fichiers, dav: NextcloudWebDAV, racine_distante: str,
                  supprimer_apres: bool, dry_run: bool):
    compteur = {"ranges": 0, "doublons": 0, "ignores": 0, "erreurs": 0}
    for chemin in fichiers:
        extension = chemin.suffix.lower()
        if extension not in EXTS_IMAGES and extension not in EXTS_VIDEOS:
            print(f"[ignoré]  {chemin.name} (extension non gérée)")
            compteur["ignores"] += 1
            continue
        date = date_du_fichier(chemin)
        dossier = f"{racine_distante}/{date.year:04d}"
        sous_dossier = f"{dossier}/{date.month:02d}"
        distant = f"{sous_dossier}/{chemin.name}"

        if dav.fichier_existe(distant):
            print(f"[doublon] {chemin.name} — déjà présent à distance")
            compteur["doublons"] += 1
            if supprimer_apres and not dry_run:
                chemin.unlink()
            continue

        print(f"[upload]  {chemin.name} -> {racine_distante}/{date.year:04d}/{date.month:02d}/")
        if not dry_run:
            try:
                dav.creer_dossier(dossier)
                dav.creer_dossier(sous_dossier)
                if dav.envoyer(chemin, distant):
                    if supprimer_apres:
                        chemin.unlink()
                    compteur["ranges"] += 1
                else:
                    print(f"[erreur]  {chemin.name} : échec de l'upload")
                    compteur["erreurs"] += 1
            except Exception as e:
                print(f"[erreur]  {chemin.name} : {e}")
                compteur["erreurs"] += 1
        else:
            compteur["ranges"] += 1
    return compteur


# ---------------------------------------------------------------- principal

def main():
    parseur = argparse.ArgumentParser(
        description="Range les photos par date EXIF, en local ou via WebDAV Nextcloud."
    )
    parseur.add_argument("source", type=Path, help="dossier de triage à vider")
    parseur.add_argument("--dest", type=Path, default=Path.home() / "Photos",
                        help="mode local : dossier racine Photos (défaut : ~/Photos)")
    parseur.add_argument("--webdav", nargs="?", const=os.environ.get("NC_URL"), default=None,
                        metavar="URL",
                        help="mode WebDAV : URL remote.php/dav/files/<user> "
                             "(défaut : variable NC_URL)")
    parseur.add_argument("--remote-dir", default="Photos",
                        help="mode WebDAV : dossier racine distant (défaut : Photos)")
    parseur.add_argument("--user", default=os.environ.get("NC_USER"),
                        help="mode WebDAV : utilisateur (défaut : variable NC_USER)")
    parseur.add_argument("--token", default=os.environ.get("NC_TOKEN"),
                        help="mode WebDAV : mot de passe d'application "
                             "(défaut : variable NC_TOKEN)")
    parseur.add_argument("--copy", action="store_true",
                        help="copier au lieu de déplacer / ne pas supprimer après upload")
    parseur.add_argument("--dry-run", action="store_true",
                        help="simulation : affiche sans rien faire")
    args = parseur.parse_args()

    if not args.source.is_dir():
        sys.exit(f"Le dossier source {args.source} n'existe pas.")

    fichiers = [p for p in args.source.rglob("*") if p.is_file()]
    if not fichiers:
        sys.exit("Aucun fichier dans le dossier de triage.")

    if any(p.suffix.lower() == ".heic" for p in fichiers) and not HEIC_OK:
        print("Attention : des HEIC détectés et pillow-heif absent (pip install pillow-heif).")

    if args.webdav:
        if not REQUESTS_OK:
            sys.exit("Le paquet requests est requis en mode WebDAV : pip install requests")
        if not args.webdav or not args.user or not args.token:
            sys.exit("Mode WebDAV : NC_URL (--webdav), NC_USER (--user) et NC_TOKEN (--token) requis.\n"
                     "Astuce : crée un mot de passe d'application dans "
                     "Réglages → Sécurité → Nom de l'appareil.")
        dav = NextcloudWebDAV(args.webdav, args.user, args.token)
        # Vérification de connexion dès le départ
        if not dav.dossier_existe(args.remote_dir):
            try:
                dav.creer_dossier(args.remote_dir)
            except RuntimeError as e:
                sys.exit(f"Impossible de joindre ou de créer le dossier distant : {e}")
        print(f"Mode WebDAV : {args.webdav} (racine distante : {args.remote_dir})"
              + ("  (SIMULATION)" if args.dry_run else ""))
        compteur = ranger_webdav(fichiers, dav, args.remote_dir,
                                supprimer_apres=not args.copy, dry_run=args.dry_run)
    else:
        if not args.dest.is_dir():
            sys.exit(f"Le dossier destination {args.dest} n'existe pas.")
        print(f"Mode local : {args.dest}" + ("  (SIMULATION)" if args.dry_run else ""))
        compteur = ranger_local(fichiers, args.dest, deplacer=not args.copy,
                                dry_run=args.dry_run)

    print(
        f"\nTerminé : {compteur['ranges']} rangé(s), {compteur['doublons']} doublon(s), "
        f"{compteur['ignores']} ignoré(s), {compteur['erreurs']} erreur(s)."
    )
    if compteur["erreurs"]:
        sys.exit(1)


if __name__ == "__main__":
    main()