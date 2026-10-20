"""Throwaway prototype: schema-driven NetBox filter validator, replayed over recorded benchmark tool calls.

Outputs proto_results.json next to this file and prints a summary. GET-only against live NetBox.
"""
import difflib
import json
import os
import pickle
import re
import sys
import time
import tracemalloc
from collections import Counter, defaultdict

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = "/home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/netbox-openapi.json"
BENCH = "/home/ola/.claude/jobs/82fa8c5d/tmp/bench/tool_runs.json"
LS = os.path.join(HERE, "langsmith_tool_runs_1018_1019.json")
sys.path.insert(0, "/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server/src")
from netbox_mcp_server.netbox_types import NETBOX_OBJECT_TYPES  # noqa: E402

BASE = "http://localhost:8000"
TOKEN = os.environ["NETBOX_TOKEN"]
HDR = {"Authorization": f"Token {TOKEN}", "Accept": "application/json"}
MCP_LEVEL = {"limit", "offset", "ordering", "q", "fields", "brief"}  # tool args / generic query params

# ---------------------------------------------------------------- 1. index build
t0 = time.perf_counter()
tracemalloc.start()
with open(SCHEMA, "rb") as f:
    raw = f.read()
t_read = time.perf_counter() - t0
t1 = time.perf_counter()
doc = json.loads(raw)
t_parse = time.perf_counter() - t1
mem_doc = tracemalloc.get_traced_memory()[0]

t2 = time.perf_counter()
# enum values are inline only for scalar params; array params carry only x-spec-enum-id, resolved via components
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


walk(doc["components"])
walk(doc["paths"])

index: dict[str, dict[str, dict]] = {}
for path, item in doc["paths"].items():
    get = item.get("get")
    if not get or "parameters" not in get or path.rstrip("/").split("/")[-1].startswith("{"):
        continue
    params = {}
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
        params[p["name"]] = {"type": typ, "multi": typ == "array", "enum": enum, "nullable": s.get("nullable", False)}
    index[path] = params
t_index = time.perf_counter() - t2
mem_total = tracemalloc.get_traced_memory()[0]
del doc, raw
import gc  # noqa: E402

gc.collect()
tracemalloc.stop()
tracemalloc.start()
idx_copy = pickle.loads(pickle.dumps(index))  # measure index alone
mem_index = tracemalloc.get_traced_memory()[0]
tracemalloc.stop()
del idx_copy
idx_json = json.dumps(index).encode()
idx_pickle = pickle.dumps(index)
t3 = time.perf_counter()
json.loads(idx_json)
t_load_idx = time.perf_counter() - t3

cost = {
    "schema_bytes": os.path.getsize(SCHEMA),
    "read_s": t_read, "parse_s": t_parse, "index_build_s": t_index,
    "mem_parsed_doc_bytes": mem_doc, "mem_peak_total_bytes": mem_total, "mem_index_only_bytes": mem_index,
    "index_json_bytes": len(idx_json), "index_pickle_bytes": len(idx_pickle), "index_json_reload_s": t_load_idx,
    "list_endpoints": len(index), "total_params": sum(len(v) for v in index.values()),
    "params_with_enum": sum(1 for v in index.values() for p in v.values() if p["enum"]),
    "enum_ids_resolved": len(enum_by_id),
}
# live schema fetch cost (GET only)
t4 = time.perf_counter()
r = requests.get(f"{BASE}/api/schema/?format=json", headers=HDR, timeout=120)
cost["live_schema_fetch_s"] = time.perf_counter() - t4
cost["live_schema_http"] = r.status_code
cost["live_schema_bytes"] = len(r.content)

# ---------------------------------------------------------------- 2. load recorded runs
runs = {}
b = json.load(open(BENCH))
runs["2026-09-23"] = b["old"]
runs["2026-10-17"] = b["new"]
ls = json.load(open(LS))
runs["2026-10-18"] = ls["filter_naming_1018"]
runs["2026-10-19"] = ls["search_types_1019"]


def endpoint_for(name, inputs):
    if name == "netbox_get_changelogs":
        return "/api/core/object-changes/"
    ot = inputs.get("object_type")
    m = NETBOX_OBJECT_TYPES.get(ot)
    return f"/api/{m['endpoint']}/" if m else None


def recorded_count(out_head):
    m = re.search(r'\\+"count\\+": (\d+)', out_head) or re.search(r'"count": (\d+)', out_head)
    return int(m.group(1)) if m else None


def outcome(row):
    h = row["out_head"]
    if "TOOL_VALIDATION_ERROR" in h:
        return "validation_error"
    if "TOOL_API_ERROR" in h and "400" in h:
        return "http_400"
    if "TOOL_API_ERROR" in h or "Error" in h[:200]:
        return "error_other"
    c = recorded_count(h)
    if c == 0:
        return "empty"
    return "ok"


# ---------------------------------------------------------------- 3. replay: key lookup
def wire(v):
    """What requests would send (None -> dropped!)."""
    return v


lookup_times = []
calls = []  # per-call records
for run, rows in runs.items():
    for row in rows:
        if row["name"] not in ("netbox_get_objects", "netbox_get_changelogs"):
            continue
        inp = row["inputs"]
        filters = inp.get("filters") or {}
        if not isinstance(filters, dict):
            filters = {"<non-dict-filters>": filters}
        ep = endpoint_for(row["name"], inp)
        t = time.perf_counter_ns()
        params = index.get(ep) if ep else None
        found, missing = [], []
        for k in filters:
            if params is not None and k in params:
                found.append(k)
            else:
                missing.append(k)
        lookup_times.append(time.perf_counter_ns() - t)
        calls.append({
            "run": run, "trace": row.get("trace"), "q": row.get("q"), "name": row["name"], "object_type": inp.get("object_type"),
            "endpoint": ep, "endpoint_known": params is not None, "filters": filters, "found": found, "missing": missing,
            "outcome": outcome(row), "recorded_count": recorded_count(row["out_head"]),
        })
cost["lookup_ns_mean"] = sum(lookup_times) / len(lookup_times)
cost["lookup_ns_max"] = max(lookup_times)

# ---------------------------------------------------------------- 4. live ground truth per distinct (endpoint, key, value)
sess = requests.Session()
sess.headers.update(HDR)
unfiltered: dict[str, int] = {}


def total(ep):
    if ep not in unfiltered:
        r = sess.get(f"{BASE}{ep}", params={"limit": 1}, timeout=60)
        unfiltered[ep] = r.json()["count"] if r.status_code == 200 else None
    return unfiltered[ep]


def jkey(v):
    return json.dumps(v, sort_keys=True)


live_cache_path = os.path.join(HERE, "live_checks.json")
live = json.load(open(live_cache_path)) if os.path.exists(live_cache_path) else {}


def live_check(ep, key, value):
    """GET ep with only this filter. Returns dict(http, count, unfiltered, verdict). Sends exactly what requests sends."""
    ck = f"{ep}|{key}|{jkey(value)}"
    if ck in live:
        return live[ck]
    params = {"limit": 1, key: value}
    r = sess.get(f"{BASE}{ep}", params=params, timeout=60)
    tot = total(ep)
    rec = {"http": r.status_code, "count": None, "unfiltered": tot, "sent_url": r.url}
    if r.status_code == 200:
        rec["count"] = r.json().get("count")
        if value is None:
            rec["verdict"] = "dropped_by_requests"  # param never sent
        elif rec["count"] == tot:
            rec["verdict"] = "ignored_or_coincident"
        else:
            rec["verdict"] = "honoured"
    elif r.status_code == 400:
        rec["verdict"] = "rejected_400"
        try:
            rec["error"] = r.json()
        except Exception:
            rec["error"] = r.text[:300]
    else:
        rec["verdict"] = f"http_{r.status_code}"
    live[ck] = rec
    return rec


n_live = 0
for c in calls:
    if not c["endpoint_known"]:
        continue
    c["live"] = {}
    for k, v in c["filters"].items():
        if k in MCP_LEVEL:
            continue
        c["live"][k] = live_check(c["endpoint"], k, v)
        n_live += 1
json.dump(live, open(live_cache_path, "w"), indent=1)
cost["live_checks_distinct"] = len(live)

# ---------------------------------------------------------------- 5. enum value checks
enum_checks = []
for c in calls:
    if not c["endpoint_known"]:
        continue
    params = index[c["endpoint"]]
    for k, v in c["filters"].items():
        p = params.get(k)
        if not p or not p["enum"]:
            continue
        vals = v if isinstance(v, list) else [v]
        bad = [x for x in vals if x not in p["enum"]]
        enum_checks.append({"run": c["run"], "endpoint": c["endpoint"], "key": k, "value": v, "bad": bad, "enum": p["enum"],
                            "live": c.get("live", {}).get(k, {}).get("verdict"), "outcome": c["outcome"]})

# ---------------------------------------------------------------- 6. did-you-mean for missing keys
suggest = {}
for c in calls:
    if not c["endpoint_known"]:
        continue
    names = list(index[c["endpoint"]].keys())
    for k in c["missing"]:
        if k in MCP_LEVEL:
            continue
        sk = (c["endpoint"], k)
        if sk not in suggest:
            suggest[sk] = difflib.get_close_matches(k, names, n=3, cutoff=0.6)
suggest_out = [{"endpoint": e, "key": k, "suggestions": s} for (e, k), s in sorted(suggest.items())]

json.dump({"cost": cost, "calls": calls, "enum_checks": enum_checks, "suggest": suggest_out, "unfiltered": unfiltered},
          open(os.path.join(HERE, "proto_results.json"), "w"), indent=1, default=str)

# ---------------------------------------------------------------- 7. summary
print("COST", json.dumps(cost, indent=1))
for run in runs:
    cs = [c for c in calls if c["run"] == run]
    nk = sum(len(c["filters"]) for c in cs)
    nf = sum(len(c["found"]) for c in cs)
    nm = sum(len(c["missing"]) for c in cs)
    nm_mcp = sum(1 for c in cs for k in c["missing"] if k in MCP_LEVEL)
    unk = sum(1 for c in cs if not c["endpoint_known"])
    rej_calls = sum(1 for c in cs if any(k not in MCP_LEVEL for k in c["missing"]))
    print(f"RUN {run}: calls={len(cs)} get_objects={sum(1 for c in cs if c['name']=='netbox_get_objects')} "
          f"changelogs={sum(1 for c in cs if c['name']=='netbox_get_changelogs')} unknown_endpoint={unk} "
          f"keys={nk} found={nf} missing={nm} (of which mcp-level={nm_mcp}) calls_rejected={rej_calls} "
          f"outcomes={dict(Counter(c['outcome'] for c in cs))}")
