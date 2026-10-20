#!/usr/bin/env python
"""Build the vendored NetBox filter index from the instance's OpenAPI document.

The agent's FilterValidator checks REST filter keys against the per-endpoint
query-parameter names NetBox publishes at /api/schema/, and enum-valued
parameters against the schema's enum tables. NetBox silently drops unknown
query parameters (returns the UNFILTERED set with HTTP 200), so a name that is
not in this index is a wrong answer waiting to happen. Verified 2026-10-20 by
replaying 1,237 recorded benchmark calls: 54 unknown-key uses, all silently
ignored live, 0 false positives. See
docs/development/2026-10-20_openapi-schema-driven-filter-validation.md.

Usage:
    ./venv/bin/python scripts/build_netbox_filter_index.py            # uses NETBOX_URL/.env
    NETBOX_URL=http://host:8000 ./venv/bin/python scripts/build_netbox_filter_index.py

Writes src/tools/netbox_filter_index.json.gz (~100 KB) stamped with the NetBox
version. Re-run after a NetBox upgrade or plugin install; the validator warns
when the running instance's version differs from the stamp.
"""
from __future__ import annotations

import ast
import gzip
import json
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "tools" / "netbox_filter_index.json.gz"


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def fetch_schema(url: str, token: str | None) -> dict:
    req = urllib.request.Request(url.rstrip("/") + "/api/schema/?format=json")
    req.add_header("Accept", "application/json")
    if token:
        req.add_header("Authorization", f"Token {token}")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 - local NetBox
        raw = resp.read()
    print(f"fetched {len(raw):,} bytes in {time.perf_counter() - t0:.2f}s", file=sys.stderr)
    return json.loads(raw)


def object_type_map(server_path: str | None) -> dict[str, str]:
    """object_type -> '/api/<app>/<endpoint>/' from the MCP server's NETBOX_OBJECT_TYPES
    (parsed from source so this script never imports the server)."""
    if not server_path:
        return {}
    src = Path(server_path) / "src" / "netbox_mcp_server" / "netbox_types.py"
    tree = ast.parse(src.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "NETBOX_OBJECT_TYPES" for t in node.targets
        ):
            table = ast.literal_eval(node.value)
            return {ot: "/api/" + v["endpoint"].strip("/") + "/" for ot, v in table.items()}
    return {}


def build_index(doc: dict) -> dict[str, dict[str, dict]]:
    enum_by_id: dict[str, list] = {}

    def walk(o):
        if isinstance(o, dict):
            if "x-spec-enum-id" in o and "enum" in o:
                enum_by_id.setdefault(o["x-spec-enum-id"], o["enum"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(doc.get("components", {}))
    walk(doc["paths"])
    index: dict[str, dict[str, dict]] = {}
    for path, item in doc["paths"].items():
        get = item.get("get")
        if not get or "parameters" not in get or path.rstrip("/").split("/")[-1].startswith("{"):
            continue
        params: dict[str, dict] = {}
        for p in get["parameters"]:
            if p.get("in") != "query":
                continue
            s = p.get("schema", {})
            typ = s.get("type")
            enum = s.get("enum")
            spec = s.get("x-spec-enum-id")
            if typ == "array":
                it = s.get("items", {})
                enum = enum or it.get("enum")
                spec = spec or it.get("x-spec-enum-id")
            if enum is None and spec:
                enum = enum_by_id.get(spec)
            entry: dict = {"t": typ, "m": typ == "array"}
            if enum:
                entry["e"] = sorted(str(x) for x in enum)
            params[p["name"]] = entry
        index[path] = params
    return index


def main() -> int:
    _load_dotenv()
    url = os.environ.get("NETBOX_URL", "http://localhost:8000")
    token = os.environ.get("NETBOX_TOKEN")
    doc = fetch_schema(url, token)
    version = doc.get("info", {}).get("version", "unknown")
    t0 = time.perf_counter()
    index = build_index(doc)
    build_s = time.perf_counter() - t0
    types = object_type_map(os.environ.get("MCP_SERVER_PATH"))
    resolved = {ot: path for ot, path in types.items() if path in index}
    missing = sorted(set(types) - set(resolved))
    out = {
        "netbox_version": version,
        "generated": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": url.rstrip("/") + "/api/schema/",
        "endpoints": index,
        "object_types": resolved,
    }
    OUT.write_bytes(gzip.compress(json.dumps(out, separators=(",", ":")).encode(), mtime=0))
    n_params = sum(len(v) for v in index.values())
    n_enum = sum(1 for v in index.values() for e in v.values() if "e" in e)
    t1 = time.perf_counter()
    gzip.decompress(OUT.read_bytes())
    load_ms = (time.perf_counter() - t1) * 1000
    print(
        f"netbox {version}: {len(index)} list endpoints, {n_params:,} parameters, "
        f"{n_enum} with enums; object types resolved {len(resolved)}/{len(types)}"
        + (f" (unresolved: {missing})" if missing else "")
        + f"; build {build_s:.2f}s; wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size:,} bytes, loads in {load_ms:.0f} ms)"
    )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
