#!/usr/bin/env python3
"""Synthetic-only authenticated NDJSON + gzip + Loki query test."""
import base64
import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env = dict(line.strip().split("=", 1) for line in (root / ".env").read_text().splitlines()
           if line.strip() and not line.lstrip().startswith("#") and "=" in line)
auth = "Basic " + base64.b64encode((env["INGEST_USER"] + ":" + env["INGEST_PASSWORD"]).encode()).decode()
receiver = "http://127.0.0.1:18686/akamai/waf"
loki = "http://127.0.0.1:13100"
run = "synthetic-" + uuid.uuid4().hex
started = time.time_ns() - 5_000_000_000

def post(data, *, authenticated=True, compressed=False, url=receiver):
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["Authorization"] = auth
    if compressed:
        headers["Content-Encoding"] = "gzip"
        data = gzip.compress(data)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code

def expect(name, actual, expected):
    if isinstance(expected, int):
        expected = (expected,)
    if actual not in expected:
        raise RuntimeError(f"{name}: HTTP {actual}; expected {expected}")
    print(f"PASS: {name} (HTTP {actual})", flush=True)

def query(selector):
    params = urllib.parse.urlencode({"query": selector, "start": started, "end": time.time_ns(), "limit": 1000})
    with urllib.request.urlopen(loki + "/loki/api/v1/query_range?" + params, timeout=10) as r:
        data = json.load(r)
    return [json.loads(v[1]) for stream in data["data"]["result"] for v in stream["values"]]

def event(suffix, action, status):
    return {
        "type": "akamai_siem",
        "attackData": {"clientIP": "192.0.2.10", "appliedAction": action, "rules": "OTUwMDAy%3bOTUwMDA2", "ruleData": "never-store-raw"},
        "geo": {"asn": "64500", "country": "ID"},
        "httpMessage": {"start": str(int(time.time()) - 30), "host": "example.test", "method": "GET", "status": str(status), "requestId": run + suffix, "query": "never-store-raw", "requestHeaders": "never-store-raw"},
    }

def ndjson(*records):
    return ("\n".join(json.dumps(x) for x in records) + "\n").encode()

# Wait for receiver startup without creating log events.
for attempt in range(60):
    try:
        if post(ndjson({"access_validation": True}), authenticated=False) in (401, 403):
            break
    except (OSError, urllib.error.URLError):
        pass
    time.sleep(1)
else:
    raise RuntimeError("Vector authentication/receiver not ready")

expect("authenticated validation", post(ndjson({"access_validation": True})), 200)
expect("plain NDJSON and metadata", post(ndjson(event("-denied", "deny", 403), {"offset": "test", "limit": 10, "total": 1})), 200)
expect("gzip NDJSON", post(ndjson(event("-alert", "alert", 403)), compressed=True), 200)
expect("malformed JSON sanitized", post(b"{not-json}\n"), 200)
expect("missing credentials rejected", post(ndjson(event("-unauth", "deny", 403)), authenticated=False), (401, 403))
expect("wrong path rejected", post(ndjson(event("-wrongpath", "deny", 403)), url=receiver + "/other"), (404, 405))

for attempt in range(60):
    try:
        records = [r for r in query('{source="akamai",dataset="waf"} |= "' + run + '"')]
        diagnostics = query('{source="akamai",dataset="diagnostic"}')
        controls = query('{source="akamai",dataset="control"}')
        if len(records) >= 2 and len(controls) >= 2 and any(r.get("reason") == "invalid_json" for r in diagnostics):
            break
    except (OSError, urllib.error.URLError):
        pass
    time.sleep(1)
else:
    raise RuntimeError("Expected WAF and diagnostic events not found in Loki")
assert len(records) == 2, records
assert {r["action"] for r in records} == {"deny", "alert"}, records
assert all(r["status_code"] == 403 for r in records), records
assert all(r["rule_ids"] == ["950002", "950006"] for r in records), records
assert all(r["event_time_valid"] and 25 <= r["ingestion_lag_seconds"] <= 120 for r in records), records
assert all("never-store-raw" not in json.dumps(r) for r in records), records
assert len(controls) >= 2 and all(r.get("reason") == "validation_or_batch_metadata" for r in controls), controls
assert all(r.get("dataset") == "waf" for r in records)
print("PASS: control records are isolated from WAF statistics", flush=True)
print("PASS: auth, exact path, validation, NDJSON, gzip, normalization, rule decoding, diagnostics and Loki query")

# Execute every dashboard metric expression against Loki, not just JSON syntax.
dashboard = json.loads((root / "grafana/akamai-waf.json").read_text())
for panel in dashboard["panels"]:
    for target in panel.get("targets", []):
        if panel["type"] == "logs":
            continue
        expr = target["expr"].replace("$__range", "15m")
        params = urllib.parse.urlencode({"query": expr, "time": time.time_ns()})
        with urllib.request.urlopen(loki + "/loki/api/v1/query?" + params, timeout=20) as r:
            assert json.load(r)["status"] == "success", panel["title"]
        print("PASS: LogQL " + panel["title"], flush=True)

