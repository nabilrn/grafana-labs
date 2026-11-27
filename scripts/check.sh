#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
engine="${CONTAINER_ENGINE:-podman}"
case "${1:-}" in
  --deploy) exec bash scripts/deploy.sh ;;
  "") ;;
  *) echo "Usage: bash scripts/check.sh [--deploy]" >&2; exit 2 ;;
esac
trap 'echo "CHECK FAILED at line $LINENO. Inspect $engine compose logs --tail=80 (redact secrets)." >&2' ERR
for cmd in "$engine" curl python3; do command -v "$cmd" >/dev/null; done
test -s .env || { echo 'Missing .env. Run bash scripts/check.sh --deploy.' >&2; exit 1; }
"$engine" compose -f compose.yaml config --quiet
echo '=== Container status ==='
"$engine" compose -f compose.yaml ps
for name in dg-loki dg-vector; do
  [[ "$("$engine" inspect --format '{{.State.Running}}' "$name")" == true ]] || { echo "$name is not running. Use --deploy." >&2; exit 1; }
done
echo '=== Loki readiness ==='
for i in $(seq 1 90); do
  if curl --max-time 3 -fsS http://127.0.0.1:13100/ready >/dev/null 2>&1; then
    echo 'PASS: Loki ready'
    break
  fi
  if [[ "$i" == 90 ]]; then echo 'Loki did not become ready' >&2; exit 1; fi
  sleep 2
done
echo '=== Synthetic end-to-end and dashboard LogQL ==='
python3 scripts/smoke.py
echo '=== Resource snapshot ==='
"$engine" stats --no-stream dg-vector dg-loki
if "$engine" inspect dg-grafana >/dev/null 2>&1; then
  echo '=== Existing Grafana network ==='
  "$engine" inspect dg-grafana --format '{{range $k, $v := .NetworkSettings.Networks}}{{println $k}}{{end}}'
  if "$engine" inspect dg-grafana --format '{{range $k, $v := .NetworkSettings.Networks}}{{println $k}}{{end}}' | grep -qx dg-monitoring; then
    echo 'PASS: Grafana attached to dg-monitoring'
  else
    echo "INFO: Attach existing Grafana: $engine network connect dg-monitoring dg-grafana"
  fi
fi
echo 'PASS: local ingestion, storage and dashboard query checks.'
