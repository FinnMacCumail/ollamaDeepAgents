#!/usr/bin/env python
"""Replay recorded benchmark tool calls through FilterValidator (offline gate).

Reads the research prototype's per-call results (tmp/research/..., not committed)
and reports how many calls the current validator rejects, split into: calls whose
keys the OpenAPI index marked unknown (expected rejections), calls rejected by a
hand rule only, and calls rejected although every key was honoured live (false
positives - must be zero). Also scores the suggestion layer against the 27
expected corrections.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NOTES = ROOT / "tmp/research/research_notes/OpenAPI schema driven filter validation"

from src.tools.netbox_tools import FilterValidator, endpoint_params, _schema_suggestion  # noqa: E402

res = json.load(open(NOTES / "proto_results.json"))
calls = res["calls"]
expected_missing = sum(len(c["missing"]) for c in calls)
rej_missing = rej_hand = false_pos = passed_missing = 0
hand_reasons = Counter(); fp_examples = []; miss_examples = []
for c in calls:
    ok, err = FilterValidator.validate_filter(c["filters"], c["object_type"])
    if c["missing"]:
        if ok:
            passed_missing += 1; miss_examples.append((c["object_type"], c["missing"]))
        else:
            rej_missing += 1
    elif not ok:
        key = (err or "").split("Invalid filter pattern: ", 1)[-1].split(" ")[0]
        live = c.get("live", {}) or {}
        verdict = (live.get(key) or {}).get("verdict")
        if verdict in ("honoured",):
            false_pos += 1; fp_examples.append((c["object_type"], key, (err or "")[:90]))
        else:
            rej_hand += 1; hand_reasons[key] += 1
print(f"calls {len(calls)}; keys the index marked unknown: {expected_missing} uses on {sum(1 for c in calls if c['missing'])} calls")
print(f"rejected (unknown-key calls): {rej_missing}   passed despite unknown key: {passed_missing} {miss_examples[:5]}")
print(f"rejected by hand/enum rules on known keys: {rej_hand} {dict(hand_reasons)}")
print(f"FALSE POSITIVES (rejected though live-honoured): {false_pos} {fp_examples[:5]}")
# suggestion gate
good = 0; bad_n = 0; rows = []
for s in res["suggest"]:
    ot = next((c["object_type"] for c in calls if c["endpoint"] == s["endpoint"]), None)
    params = endpoint_params(ot) or {}
    msg = _schema_suggestion(s["key"], params)
    hit = any(exp in msg for exp in s["suggestions"]) if s["suggestions"] else False
    fam = s["key"].split("__")[-1] in ("in", "empty", "null", "isnull")
    if fam and "__n" in msg.replace("__n ", "__n").split("'")[1::2].__str__(): bad_n += 1
    good += hit; rows.append((s["key"], s["suggestions"][:2], "OK" if hit else "miss", msg[:70]))
print(f"suggestions: {good}/{len(res['suggest'])} name the expected fix; '__n' suggested for an __in-family key: {bad_n}")
for r in rows:
    if r[2] != "OK": print("   miss:", r)
