"""Lecture de la date de prise de vue d'un fichier.

Cascade de repli : EXIF (``DateTimeOriginal`` puis ``DateTime``) -> pour les
vidéos, date de tournage via ``ffprobe`` -> modtime distante (rclone, RFC 3339)
-> date de modification du fichier local -> instant présent. Aucun fichier
n'est jamais « sauté » faute de date.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False

EXTS_IMAGES = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".tif", ".tiff"}
EXTS_VIDEOS = {".mp4", ".mov", ".m4v", ".avi", ".mkv"}

TAG_DATE_PRISE = 36867  # DateTimeOriginal : date de prise de vue
TAG_DATE_MODIF = 306  # DateTime : dernier enregistrement par l'appareil

EXIF_DATE_FORMAT = "%Y:%m:%d %H:%M:%S"


def parse_exif_date(brute: object) -> datetime | None:
    """Parse une date EXIF brute (« YYYY:MM:DD HH:MM:SS »).

    Retourne None si la valeur est vide, nulle (« 0000:... ») ou corrompue.
    """
    if not brute:
        return None
    texte = str(brute).strip().strip("\x00")
    if not texte or texte.startswith("0000:"):
        return None
    try:
        return datetime.strptime(texte, EXIF_DATE_FORMAT)
    except ValueError:
        return None


def date_exif(chemin: Path) -> datetime | None:
    """Date de prise de vue lue dans l'EXIF (tag 36867 puis 306), ou None."""
    try:
        with Image.open(chemin) as img:
            exif = img.getexif()
            brute = exif.get(TAG_DATE_PRISE) or exif.get(TAG_DATE_MODIF)
    except Exception:
        return None
    return parse_exif_date(brute)


def parse_iso8601(brute: str) -> datetime | None:
    """Parse une date ISO 8601 / RFC 3339 (« 2024-07-15T10:30:00Z », offsets acceptés).

    Retourne une datetime « naive » (fuseau ignoré), ou None si illisible.
    """
    if not brute:
        return None
    texte = brute.strip()
    try:
        return datetime.fromisoformat(texte.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        pass
    try:
        return datetime.strptime(texte[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def date_video(chemin: Path) -> datetime | None:
    """Date de tournage d'une vidéo via ffprobe (format_tags=creation_time), ou None.

    Retourne None si ffprobe est absent (paquet ffmpeg) ou illisible.
    """
    try:
        resultat = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format_tags=creation_time",
                "-of",
                "default=nokey=0:noprint_wrappers=1",
                str(chemin),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_iso8601(resultat.stdout.strip())


def date_modtime_rfc3339(brute: str) -> datetime | None:
    """Date de modification d'un remote rclone (RFC 3339, ex. ModTime de lsjson)."""
    return parse_iso8601(brute)


def date_fichier(chemin: Path) -> datetime:
    """Date de dernière modification du fichier local."""
    return datetime.fromtimestamp(chemin.stat().st_mtime)


def date_prise(chemin: Path, modtime: str | None = None) -> datetime:
    """Date de prise de vue d'un fichier, par cascade de repli.

    Images : EXIF. Vidéos : date de tournage ffprobe. Puis modtime distante
    (RFC 3339, migration rclone), puis mtime du fichier, puis l'instant présent.
    """
    extension = chemin.suffix.lower()
    if extension in EXTS_IMAGES:
        date = date_exif(chemin)
        if date:
            return date
    elif extension in EXTS_VIDEOS:
        date = date_video(chemin)
        if date:
            return date
    if modtime:
        date = date_modtime_rfc3339(modtime)
        if date:
            return date
    try:
        return date_fichier(chemin)
    except OSError:
        return datetime.now()


def chemin_yyyy_mm(date: datetime) -> str:
    """Dossier relatif « YYYY/MM » (mois zéro-paddé, ex. « 2024/07 »)."""
    return f"{date.year:04d}/{date.month:02d}"
