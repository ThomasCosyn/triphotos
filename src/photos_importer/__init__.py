"""photos-importer : range et importe des photos vers un Nextcloud auto-hébergé.

Arborescence cible : ``Photos/YYYY/MM`` (mois zéro-paddé), alimentée soit par
l'API WebDAV de Nextcloud, soit par deux remotes rclone.
"""

import sys

__version__ = "0.1.0"


def logs_temps_reel() -> None:
    """Passe stdout en buffering ligne : les logs apparaissent en direct dans tmux/tee.

    Sans cela, quand stdout est un pipe (ex. ``... | tee mig.log``), Python
    bufferise par blocs de 8 Ko et le log reste vide des heures.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
