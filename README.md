# Grafana Labs — Akamai DataStream 2 (WAF)

A standalone synthetic-data lab: Akamai-shaped NDJSON → Vector → Loki → existing Grafana OSS. No Enterprise plugin, Alloy, PostgreSQL, Valkey, or S3 scanning. Does not modify the existing ICT Dashboard or MyPaaS projects.

## Quick start: Debian / rootful Podman

Prerequisites: Podman + working Compose provider, Python 3, curl, Git; ports 13100 and 18686 free on loopback. Existing Grafana container is dg-grafana. Do not run on a production data path without organizational approval.

```bash
git clone https://github.com/nabilrn/grafana-labs.git
cd grafana-labs
bash scripts/deploy.sh
```

The script generates a local .env with a random Basic Auth password, validates the config, launches Vector and Loki and executes a synthetic integration test. It does not touch Caddy, cloudflared or Grafana. Image tags are pinned (Vector 0.62.0, Loki 3.7.10); runtime and CI use identical Compose config.

### Connect existing Grafana

```bash
podman network connect dg-monitoring dg-grafana
```

If already connected, skip. Open the existing Grafana UI, Connections → Data sources → Add data source → Loki. Set URL to **http://dg-loki:3100**, Save & test. Then Dashboards → New → Import → upload grafana/akamai-waf.json and select that Loki datasource. Default refresh 10 seconds, time range 15 minutes. No Grafana restart is needed. Do not expose Loki through Caddy.

### Send test events again

```bash
python3 scripts/smoke.py
podman stats --no-stream dg-vector dg-loki dg-grafana
podman compose ps
curl -fsS http://127.0.0.1:13100/ready
```

The smoke test checks invalid auth, wrong path, validation requests, gzip/plain NDJSON, metadata exclusion, applied action versus HTTP status, rule decoding, sanitized diagnostics, original timestamps and query results. All examples use documentation/test IPs and example hosts.

## Architecture and configuration

- Vector HTTP POST receiver: /akamai/waf, container 8686, host loopback 18686. Basic Auth mandatory. UTF-8 JSON objects separated by newlines; gzip requires Content-Encoding: gzip. Arrays and multiline pretty-printed JSON are not accepted as WAF records.
- Loki single binary, TSDB v13, filesystem, 7-day retention, replication factor one, persistent WAL and named volume, container 3100, host loopback 13100. Loki has no built-in authentication, so keep it private.
- Vector disk buffer 512 MiB, one concurrent downstream request, max batch 256 KiB / 1 second. At-least-once intent, not exactly once. Acknowledgements can occur after durable buffer acceptance; crash before fsync, oversized/malformed data and upstream retry exhaustion can still lose records. Invalid schema yields a sanitized diagnostic; control frames are dropped. No raw quarantine on this personal lab.
- RAM limits: Vector 256 MiB, Loki 1024 MiB; CPU limits 0.5 + 1.0 vCPU. Existing Grafana is separate. Limits are initial guesses, not benchmark results. Monitor OOM, disk, Vector errors and Loki query load. Never use global system prune.
- Loki uses collector receipt time as the stream timestamp to tolerate late batches; original Akamai event time is preserved as event_timestamp and event_epoch. Dashboard rates/counts are by receipt time, not precise edge-event time. Invalid/missing timestamp is flagged. WAF action is derived from appliedAction, not status_code. Encoded rule IDs are URL-decoded then split and Base64-decoded; rule messages/actions are not yet decoded. No request headers, response headers, cookies, query strings, raw ruleData, or request path are retained. Source IP, hostname, ASN, request ID and policy ID remain sensitive; use synthetic data only until approved.
- Labels are only source/dataset/action; IP, ASN and request ID remain in JSON to limit cardinality. No full CDN dataset parser yet. No deduplication; replay may inflate counts. No geo coordinates supplied by this schema; country ranking is included, not a fabricated point map.
- No queue/S3 credentials or public ingestion route required for this phase.

## Optional HTTPS ingestion (approved environment only)

Keep the archive stream unchanged. For approved non-sensitive DataStream testing, connect Vector to the proxy routing network if necessary (e.g. podman network connect mypaas-routing dg-vector). ops/Caddyfile.example is a **reference**, not an automatic deployment. Insert the exact host/path via MyPaaS's managed Caddy mechanism, preserve live routes, and use a dedicated Cloudflare hostname/machine authentication policy. Do not reload or replace the active Caddy config blindly. No interactive Access redirects for Akamai; verify machine-to-machine auth, request size limits and endpoint compatibility. Loki must never be externally routed. Set Akamai Custom HTTPS URL to https://<approved-ingest-host>/akamai/waf, Basic auth values from the server's .env, JSON, 30s frequency if supported, and initially compression off. Run validation before enabling a stream. No corporate data on the personal VPS without permission. Do not commit or paste .env or logs containing secrets.

## Operations

```bash
podman compose logs --tail=50
podman stats --no-stream dg-vector dg-loki
podman compose stop
podman compose up -d
```

Use restart policies plus the host Podman restart service or a dedicated systemd/Quadlet unit for reboot persistence, verified locally. Stop/start preserves named volumes. Before compose down, disconnect the external Grafana container from dg-monitoring and any manually attached proxy network if needed; never use down -v on a persistent deployment. Back up volumes during a consistent maintenance window. Retention is time-based, not a disk quota. Monitor filesystem capacity separately.

To update: git pull --ff-only, review changes, then bash scripts/deploy.sh. This is a lab, not a production HA architecture. CI is a Docker Compose synthetic integration test, not proof of Podman, Akamai, or Cloudflare production compatibility. Test outages, restart durability, 1.5/10/50/100 EPS, and actual payload shape separately before enabling real streams.

## References
- https://techdocs.akamai.com/datastream2/reference/security-data-format
- https://techdocs.akamai.com/datastream2/docs/stream-custom-https
- https://vector.dev/docs/reference/configuration/sources/http_server/
- https://vector.dev/docs/reference/configuration/sinks/loki/
- https://grafana.com/docs/loki/latest/operations/storage/retention/
