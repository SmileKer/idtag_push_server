#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root: sudo bash scripts/install_ubuntu.sh" >&2
  exit 1
fi

APP_DIR=/opt/idtag-push
APP_USER=idtagpush

apt-get update
apt-get install -y postgresql postgresql-contrib python3-venv

if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"

echo "Base packages and service user are ready."
echo "Next: copy the project to $APP_DIR and create the PostgreSQL role/database as described in README.md."
