"""Client WebDAV minimal pour l'API fichiers de Nextcloud (MKCOL / PROPFIND / PUT).

Authentification par mot de passe d'application (Réglages -> Sécurité), jamais
par le mot de passe principal du compte.
"""

from __future__ import annotations

from pathlib import Path

import requests


class NextcloudWebDAV:
    """Petit client WebDAV pour l'API fichiers de Nextcloud."""

    def __init__(
        self,
        base_url: str,
        utilisateur: str,
        token: str,
        session: requests.Session | None = None,
    ) -> None:
        self.base = base_url.rstrip("/")
        self.session = session if session is not None else requests.Session()
        self.session.auth = (utilisateur, token)
        self.dossiers_crees: set[str] = set()

    def _url(self, chemin_distant: str) -> str:
        return f"{self.base}/{chemin_distant}"

    def dossier_existe(self, chemin_distant: str) -> bool:
        """PROPFIND Depth: 0 — 207 = le dossier existe."""
        reponse = self.session.request(
            "PROPFIND", self._url(chemin_distant), headers={"Depth": "0"}
        )
        return reponse.status_code == 207

    def creer_dossier(self, chemin_distant: str) -> None:
        """MKCOL — 201 = créé, 405 = existe déjà : les deux sont OK (idempotent)."""
        if chemin_distant in self.dossiers_crees:
            return
        reponse = self.session.request("MKCOL", self._url(chemin_distant))
        if reponse.status_code not in (201, 405):
            raise RuntimeError(
                f"MKCOL {chemin_distant} : HTTP {reponse.status_code} — {reponse.text[:200]}"
            )
        self.dossiers_crees.add(chemin_distant)

    def fichier_existe(self, chemin_distant: str) -> bool:
        """PROPFIND Depth: 0 — 207 = le fichier existe (dédup par nom côté WebDAV)."""
        reponse = self.session.request(
            "PROPFIND", self._url(chemin_distant), headers={"Depth": "0"}
        )
        return reponse.status_code == 207

    def envoyer(self, chemin_local: Path, chemin_distant: str) -> bool:
        """PUT streamé — le fichier est envoyé bloc par bloc, jamais chargé en RAM.

        201/204 = succès.
        """
        with open(chemin_local, "rb") as f:
            reponse = self.session.put(self._url(chemin_distant), data=f)
        return reponse.status_code in (201, 204)
