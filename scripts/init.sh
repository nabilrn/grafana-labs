#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
if [[ -e .env ]]; then
  echo '.env exists; preserving credentials.'
  exit 0
fi
python3 - <<'PY'
import secrets
from pathlib import Path
with Path(".env").open("x") as f:
    f.write("INGEST_USER=datastream\nINGEST_PASSWORD=" + secrets.token_hex(32) + "\n")
PY
echo 'Created .env with a random ingestion password (not printed).'
