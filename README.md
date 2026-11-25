# photos-importer

Range et importe des photos vers un **Nextcloud auto-hébergé** dans l'arborescence
`Photos/YYYY/MM` (mois zéro-paddé, ex. `Photos/2024/07/IMG_0042.JPG`).

Le dossier `Photos` du serveur n'est **pas** synchronisé par le client desktop
(trop volumineux) : tout passe soit par l'**API WebDAV** de Nextcloud, soit par
**rclone**.

Trois commandes, trois cas d'usage :

| Commande | Rôle |
|---|---|
| `photos-import-folder` | Range un dossier de triage local, en local (`--dest`) ou par upload WebDAV (`--webdav`) |
| `photos-from-phone` | iPhone branché en USB : copie du DCIM vers le triage, puis upload WebDAV |
| `photos-migrate-gdrive` | Migration Google Drive → Nextcloud via deux remotes rclone |

La date de prise de vue est lue en cascade — EXIF (`DateTimeOriginal` puis
`DateTime`) → pour les vidéos, date de tournage via `ffprobe` → modtime distante
(rclone) → date de modification du fichier → instant présent — donc **aucun
fichier n'est jamais sauté** faute de métadonnées.

## Installation

Paquets système (Ubuntu) :

```bash
sudo apt install libimobiledevice6 libimobiledevice-utils rsync ffmpeg rclone
```

- `libimobiledevice6` / `libimobiledevice-utils` : accès à l'iPhone en USB ;
- `rsync` : copie du DCIM ;
- `ffmpeg` (donc `ffprobe`) : date de tournage des vidéos, **optionnel** ;
- `rclone` : migration Google Drive.

Installation Python (recommandé : `pipx`) :

```bash
pipx install .
pipx inject photos-importer pillow-heif   # optionnel : support HEIC
```

Dépendances Python : `Pillow` et `requests` (installées automatiquement).
`pillow-heif` n'est nécessaire que si des `.HEIC` remontent de l'iPhone.

## Identifiants Nextcloud

Crée un **mot de passe d'application** (jamais le mot de passe principal) :
Nextcloud → Réglages → Sécurité → **Nom de l'appareil**.

Puis un fichier env dédié, en permissions 600 uniquement :

```bash
install -m 600 /dev/null ~/.config/photos-nextcloud.env
cat > ~/.config/photos-nextcloud.env <<'EOF'
NC_URL=https://cloud.example.org/remote.php/dav/files/<ton-user>
NC_USER=<ton-user>
NC_TOKEN=<mot-de-passe-d-application>
EOF
chmod 600 ~/.config/photos-nextcloud.env
```

Ce fichier ne doit jamais être commité. `photos-import-folder` accepte aussi
directement les variables d'environnement `NC_URL` / `NC_USER` / `NC_TOKEN` ou
les options `--webdav`, `--user`, `--token`.

## Configuration rclone (migration Google Drive)

Deux remotes à créer avec `rclone config` :

**1. `drive` — Google Drive, scope read-only** (la migration ne doit jamais
pouvoir modifier le Drive) :

```text
n) New remote
name> drive
Storage> drive
client_id> (laisser vide, celui de rclone convient)
client_secret> (laisser vide)
scope> 1        # 1 = read-only : accès en lecture seule
root_folder_id> (laisser vide)
service_account_file> (laisser vide)
Edit advanced config? n
Use auto config? y   # OAuth dans le navigateur
```

**2. `nc` — Nextcloud en WebDAV** :

```text
n) New remote
name> nc
Storage> webdav
url> https://cloud.example.org/remote.php/dav/files/<ton-user>
vendor> nextcloud
user> <ton-user>
pass> <mot-de-passe-d-application>   # caché par rclone (obscuré dans la config)
```

Vérifie que les deux remotes répondent :

```bash
rclone lsd drive:
rclone lsd nc:
```

## Les commandes

### `photos-import-folder` — ranger un dossier de triage

```bash
# Mode local : ~/Triage -> ~/Photos/YYYY/MM (déplacement)
photos-import-folder ~/Triage

# Mode local explicite, en copie (la source est conservée)
photos-import-folder ~/Triage --dest /srv/nextcloud/data/<user>/files/Photos --copy

# Mode WebDAV : upload vers Nextcloud, suppression du local après upload confirmé
photos-import-folder ~/Triage --webdav
photos-import-folder ~/Triage --webdav --remote-dir Photos --copy

# Simulation (rien n'est déplacé, copié, uploadé ni supprimé)
photos-import-folder ~/Triage --webdav --dry-run
```

- En mode WebDAV, un fichier distant de même nom est un doublon (les noms
  `IMG_xxxx` de la pellicule sont uniques) : il est ignoré, et le fichier local
  est supprimé **uniquement** si l'upload a abouti (sauf `--copy`).
- En mode local, la déduplication se fait par empreinte SHA-256 : contenu
  identique = doublon ; nom identique mais contenu différent = suffixe `_1`, `_2`…
- Les vidéos sont uploadées en streaming (PUT WebDAV avec descripteur de
  fichier) : pas de limite mémoire, pas de limite d'upload de l'interface web.
- Code de sortie : `1` si au moins une erreur, `0` sinon.

### `photos-from-phone` — iPhone en USB

Branche l'iPhone (déverrouillé, « Faire confiance » validé), puis :

```bash
photos-from-phone                 # DCIM -> ~/Triage, puis upload WebDAV
photos-from-phone --dry-run       # simulation complète (rsync inclus)
photos-from-phone --triage ~/Triage --remote-dir Photos
```

Le script découvre le point de montage GVfs
(`/run/user/$UID/gvfs/gphoto2:host=*` ou `mtp:host=*`) — **échec explicite si
aucun téléphone n'est monté** — copie le `DCIM/` avec
`rsync -rltv --ignore-existing` (rien n'est supprimé du téléphone), charge
`~/.config/photos-nextcloud.env` (chmod 600 attendu) puis lance l'upload
WebDAV.

### `photos-migrate-gdrive` — migration Google Drive → Nextcloud

```bash
photos-migrate-gdrive --dry-run            # plan, dates estimées (modtime Drive)
photos-migrate-gdrive --limit 50           # lot d'essai
photos-migrate-gdrive                      # tout migrer
photos-migrate-gdrive --source Photos --dest Photos --drive-remote drive --nc-remote nc
```

Flux : listing récursif `rclone lsjson` du Drive et de `Photos/` côté
Nextcloud (aucun téléchargement à ce stade) → index des fichiers déjà migrés
(**même nom + même taille = migré, sauté**) → pour chaque fichier restant :
téléchargement **streamé** dans un unique fichier temporaire (`rclone cat` vers
un descripteur, jamais en RAM), lecture de la date (mêmes fonctions que le
trieur), `rclone mkdir` (idempotent) puis `rclone copyto` vers
`Photos/YYYY/MM/NOM`. Nom en collision avec contenu différent : suffixe `_1`, `_2`…

Un seul fichier temporaire à la fois : la migration est **relançable**, une
interruption reprend où elle s'était arrêtée. En `--dry-run`, les dates
affichées sont estimées (modtime Drive), car lire l'EXIF exige le contenu.

## Ce que les scripts ne font jamais

- **Ne suppriment aucune source sans certitude** : le fichier local n'est
  effacé qu'après un upload WebDAV confirmé (201/204) ; le téléphone n'est
  jamais purgé (`rsync` sans `--delete`, `--ignore-existing`) ; le Drive est
  configuré en scope **read-only**.
- **Ne re-traitent rien** à la relance : déduplication par nom/taille (rclone) ou
  par SHA-256 (local), `--ignore-existing` côté rsync.
- **Ne committent aucun secret** : fichier env en chmod 600, mot de passe
  d'application Nextcloud, mot de passe rclone obscurci dans `~/.config/rclone/`.
- **Ne sautent aucun fichier** faute de date (cascade de repli jusqu'à l'instant
  présent).

## Dépannage

- **Gros fichiers** : l'upload WebDAV est streamé (PUT par blocs) — les limites
  d'upload de l'interface web ne s'appliquent pas au WebDAV. Côté rclone, la
  migration ne garde qu'un fichier temporaire à la fois sur le disque.
- **Google Photos vs Drive** : la migration lit le remote `drive` (Google
  Drive). Les photos de Google Photos qui ne sont pas dans Drive (dossier
  « Photos » de Photos, albums partagés…) ne passent pas par ce chemin —
  exporte-les d'abord (Google Takeout) vers le Drive.
- **EXIF perdu** : avec l'option « Stockage économisé » de Google Photos,
  l'EXIF (dont la date de prise de vue) peut être absent des fichiers
  téléchargés. Le script retombe alors sur la modtime Drive en
  `photos-migrate-gdrive`, et sur la date de modification du fichier en mode
  local — les photos sont rangées, mais dans le mois de la sauvegarde plutôt
  que de la prise de vue.
- **Écriture directe dans `data/` du serveur** : si tu écris directement dans
  `data/<user>/files/...` (hors WebDAV/rclone), Nextcloud ne voit pas les
  nouveaux fichiers : lance `sudo -u www-data php occ files:scan --all`
  (ou `occ files:scan <user>`).
- **HEIC sans `pillow-heif`** : avertissement affiché, les fichiers restent
  rangés (date de modification en repli). Installe l'extra : `pipx inject
  photos-importer pillow-heif`.
- **Téléphone non détecté** : vérifie `ls /run/user/$UID/gvfs/` après avoir
  déverrouillé l'iPhone et validé « Faire confiance » ; installe
  `libimobiledevice6 libimobiledevice-utils`.

## Développement

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest          # tests unitaires (pas de vrai serveur requis)
ruff check .    # lint
```

Structure : `dates.py` (EXIF/ffprobe/modtime), `dedup.py` (SHA-256, suffixes,
index nom→tailles), `nextcloud_dav.py` (MKCOL/PROPFIND/PUT), `rclone.py`
(lsjson/cat/mkdir/copyto), `config.py` (env), `organize.py` (logique de
rangement), `cli/` (les trois commandes).
