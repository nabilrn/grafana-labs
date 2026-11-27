#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/init.sh
podman compose -f compose.yaml config --quiet
podman compose -f compose.yaml pull
podman compose -f compose.yaml run --rm --no-deps vector validate --no-environment /etc/vector/vector.yaml
podman compose -f compose.yaml up -d
echo 'Waiting for Loki readiness...'
for i in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:13100/ready >/dev/null 2>&1; then
    python3 scripts/smoke.py
    echo 'Local smoke test passed. Existing Grafana and Caddy were not modified.'
    exit 0
  fi
  sleep 2
done
echo 'Loki did not become ready; inspect podman logs dg-loki.' >&2
exit 1
