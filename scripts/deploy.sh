#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
engine="${CONTAINER_ENGINE:-podman}"
bash scripts/init.sh
"$engine" compose -f compose.yaml config --quiet
"$engine" compose -f compose.yaml pull
"$engine" compose -f compose.yaml run --rm --no-deps vector validate --no-environment /etc/vector/vector.yaml
"$engine" compose -f compose.yaml up -d
if "$engine" inspect dg-grafana >/dev/null 2>&1; then
  if ! "$engine" inspect dg-grafana --format '{{range $k, $v := .NetworkSettings.Networks}}{{println $k}}{{end}}' | grep -qx dg-monitoring; then
    "$engine" network connect dg-monitoring dg-grafana
  fi
fi
bash scripts/check.sh
echo 'Deployment verified. Existing Grafana container and Caddy configuration were not replaced.'
