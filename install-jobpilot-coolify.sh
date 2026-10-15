#!/usr/bin/env bash
set -Eeuo pipefail

# Repair a Coolify Docker Compose Empty service whose Docker build context
# contains the generated compose file but none of the project's Dockerfiles.
# Usage: sudo bash install-jobpilot-coolify.sh <resource-dir> <starter-zip>

RESOURCE_DIR="${1:-/data/coolify/services/hxpvg7jrqq8zln0rdwnayowy}"
ARCHIVE="${2:-/tmp/jobpilot-id-docker-starter.zip}"

if [[ ! -d "$RESOURCE_DIR" ]]; then
  echo "ERROR: Coolify resource directory does not exist: $RESOURCE_DIR" >&2
  exit 2
fi
if [[ ! -f "$RESOURCE_DIR/docker-compose.yml" && ! -f "$RESOURCE_DIR/compose.yaml" ]]; then
  echo "ERROR: no Compose file found in Coolify resource directory: $RESOURCE_DIR" >&2
  exit 2
fi
if [[ ! -r "$ARCHIVE" ]]; then
  echo "ERROR: ZIP file not found or unreadable: $ARCHIVE" >&2
  exit 2
fi
if ! command -v unzip >/dev/null 2>&1; then
  echo 'ERROR: unzip is required (e.g., apt-get install unzip)' >&2
  exit 2
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
unzip -qq "$ARCHIVE" -d "$TMP_DIR"
SOURCE="$TMP_DIR/jobpilot-id-starter"

for required in Dockerfile.worker Dockerfile.dashboard app/jobpilot.py config/filters.yaml config/companies.yaml config/aggregators.yaml; do
  if [[ ! -f "$SOURCE/$required" ]]; then
    echo "ERROR: ZIP missing required file $required" >&2
    exit 2
  fi
done

# Do not alter the Compose definition managed by Coolify; only install
# files required by build contexts and bind mounts.
install -m 0644 "$SOURCE/Dockerfile.worker" "$RESOURCE_DIR/Dockerfile.worker"
install -m 0644 "$SOURCE/Dockerfile.dashboard" "$RESOURCE_DIR/Dockerfile.dashboard"
mkdir -p "$RESOURCE_DIR/app" "$RESOURCE_DIR/config" "$RESOURCE_DIR/private" "$RESOURCE_DIR/data" "$RESOURCE_DIR/applications"
cp -a "$SOURCE/app/." "$RESOURCE_DIR/app/"

# Preserve existing operator-edited configuration, private data and state.
for cfg in "$SOURCE"/config/*; do
  [[ -f "$cfg" ]] || continue
  target="$RESOURCE_DIR/config/$(basename "$cfg")"
  if [[ ! -e "$target" ]]; then
    install -m 0644 "$cfg" "$target"
  fi
done
for template in facts.example.yaml profile.example.yaml; do
  if [[ ! -e "$RESOURCE_DIR/private/$template" ]]; then
    install -m 0644 "$SOURCE/private/$template" "$RESOURCE_DIR/private/$template"
  fi
done
if [[ ! -e "$RESOURCE_DIR/.env" ]]; then
  install -m 0600 "$SOURCE/.env.example" "$RESOURCE_DIR/.env"
fi

# Dockerfiles run the containers with USER node (UID/GID 1000:1000).
# Those users must be able to write to mounted SQLite and output directories.
if [[ "$(id -u)" -eq 0 ]]; then
  chown -R 1000:1000 "$RESOURCE_DIR/data" "$RESOURCE_DIR/applications" "$RESOURCE_DIR/private"
  chmod 0700 "$RESOURCE_DIR/private"
  find "$RESOURCE_DIR/private" -maxdepth 1 -type f -exec chmod 0600 '{}' +
else
  echo 'WARNING: not root; ensure data/, applications/ and private/ are readable/writable by UID 1000.' >&2
fi

for p in Dockerfile.worker Dockerfile.dashboard app/jobpilot.py config/filters.yaml config/companies.yaml config/aggregators.yaml; do
  test -f "$RESOURCE_DIR/$p" || { echo "ERROR: expected file missing: $p" >&2; exit 1; }
done

echo "OK: JobPilot build files installed in $RESOURCE_DIR"
echo 'No candidate applications have been sent. Personal profile files are not automatically filled in.'
echo 'Next: provide real private/facts.yaml and private/profile.yaml, then click Redeploy in Coolify.'
echo 'Note: manual files in Coolify service directories may be removed on migration/recreation.'
echo 'For durable deployments, store the full project in a private Git repo and deploy with Docker Compose from Git.'
