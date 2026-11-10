# 2026-11-09: Result envelope with a silently-unfiltered detector

**Every list result from the NetBox MCP tools now starts with a header the model reads
before the rows, and that header warns when a filtered call came back with the endpoint's
whole table.** This is the first of the three levers from the 27 October review of NetBox
Labs' Platform MCP server (envelope, composite reads, upstream reconciliation). Code in
`src/tools/netbox_tools.py` (`UnfilteredTotals`, `list_endpoint`, `scope_filters`,
`list_payload`, `result_header`, `with_header`, `NetBoxToolWrapper._envelope`); the model is
told about the header in `src/skills/netbox-mcp-filters/SKILL.md` ("Read the result header
first") and in the system prompt (`src/agents/netbox_agent.py`).

## The failure it closes

NetBox has two ways of refusing a filter. A wrong *name* that the filterset knows nothing
about is dropped and the request answers 200 with the unfiltered set; the schema layer of
2026-10-20 now rejects those before they are sent. A valid name whose *value* NetBox does
not honour is dropped the same way, and nothing downstream can see it: the JSON-null bug
(ADR-0045) returned 141 devices to a tenant-scoped query through two full benchmark runs
and every reader, model, judge and human, took it for the answer. The same shape recurs
with boolean spellings (`has_primary_ip=no` is dropped, `false` works), with custom-field
filters the index does not carry, and with any key a NetBox upgrade stops honouring before
the index is rebuilt. The validator cannot reach any of these because the key is valid.

The only signal that survives is arithmetic: a scoped call that matched exactly as many
objects as the endpoint holds in total almost certainly matched nothing.

## What the model now sees

```
NETBOX_RESULT scope={"has_primary_ip":"no"} matched_count=141 returned_count=100 complete=false
INCOMPLETE: 100 of 141 returned. Fetch the rest with offset=100 (limit=100), or raise limit; do not report a partial list as the total.
WARNING: filter(s) has_primary_ip had NO EFFECT: NetBox ignores them on dcim.device (a probe with an impossible value still returned all 141). These rows are the UNFILTERED table, not the answer. Re-check the key names and value forms in the netbox-mcp-filters skill and re-query.
```

and, when the filters are honoured and the population really is the whole table:

```
NETBOX_RESULT scope={"device_type_id":8} matched_count=8 returned_count=8 complete=true
NOTE: the filters are honoured and happen to match every dcim.poweroutlettemplate (8 of 8); this result is usable as the answer.
```

| field | source | purpose |
|---|---|---|
| `scope` | the `filters` dict after normalisation, minus view-level keys (`limit`, `offset`, `fields`, `q`, ...) | what was actually sent; a key missing here was never applied |
| `matched_count` | NetBox `count` | the population, all pages |
| `returned_count` | `len(results)` | this page |
| `complete` | `next is None` | the pagination trap the skill warns about at length, as a field |
| `INCOMPLETE:` | `offset + returned_count` | the exact next call |
| `WARNING:` / `NOTE:` | `count >= unfiltered total` with a non-empty scope, then one probe per scoped key | the detector (below) |

The header is the first content block; the adapter's blocks and the artifact follow
unchanged. A honoured call costs about 90 characters; the warning about 640. Tools without
NetBox's paginated shape (`netbox_search_objects`, `netbox_get_object_by_id`, GraphQL) are
untouched, as are the `TOOL_VALIDATION_ERROR` / `TOOL_API_ERROR` paths.

The unfiltered total comes from one `GET <endpoint>?limit=1&fields=id` per endpoint (75 ms
live), fetched lazily on the first scoped call to that endpoint and cached for ten minutes.

**Verify, do not guess.** Equal counts alone cannot tell a dropped filter from a filter that
honestly matches everything, and the first session ladder (below) showed how common the
second case is on small endpoints: all 8 outlet templates belong to one device type, the 25
PDUs the model listed own all 200 outlets. So on a hit the wrapper re-sends each scoped key
alone with an impossible value (`999999999` for numeric keys, `zz-no-such-value-zz` for
strings, kept as a list when the model sent a list), which is exactly how the 2026-10-20
research ground-truthed its replay. A honoured key answers 400 ("Select a valid choice") or
fewer than the total; an ignored key answers the unchanged total. One GET per key, retried
once, verdict cached per (endpoint, key) for ten minutes. Ignored keys get the WARNING by
name; all-honoured gets the NOTE; a probe that fails twice gets the older "no effect or
coincide" wording. Fail-open at every step: no `count` in the payload, an object type the
index does not map, or a failed total probe means no warning, and the counts still appear.

Known blind spot of the probe: a key whose honoured-ness depends on the value form
(`has_primary_ip=true` works, `=no` is dropped) is probed with a string, so a `true` that
coincidentally matched everything would be reported as ignored. No recorded call has that
shape.

## Replay before shipping

Rule: flag a call when it has a non-empty scope and NetBox's `count` equals the endpoint's
unfiltered total. Replayed over the recorded benchmark tool calls from the schema-validation
research (`tmp/research/research_notes/OpenAPI schema driven filter validation/`, the per-key
live verdicts of 349 ground-truth GETs).

| run | scoped calls | flagged | ignored key | dropped null | honoured filter flagged |
|---|---|---|---|---|---|
| 2026-10-18 (counts from the recorded output) | 260 | 14 | 10 | 4 | 0 |
| 2026-10-19 (counts from the recorded output) | 273 | 11 | 5 | 6 | 0 |
| all four runs, simulated from the live per-key verdicts | 1,073 | 53 | 34 | 14 | 0 (7 coincidences, below) |

Every flagged call on the two fully recorded runs was either a key NetBox ignores
(`vlan_group_id`, `circuit_type_id`, `cable_id`, `contact_role_id`, `assigned_object_*`,
`device_id` on cable-terminations, `user_id` / `user` on change-logs) or a `<relation>_id:
null` dropped on the wire. The 2026-09-23 and 2026-10-17 runs have truncated outputs for the
large results, so their numbers are simulated from the live verdicts; they agree in shape.

The seven "coincidences" are two shapes: `user_id=9` / `user=seeder` on
`/api/core/object-changes/` (3,543 of 3,543: one seeding user made every change in this
instance) and `object_id=10` on `/api/tenancy/contact-assignments/` (3 of 3). Both are
honoured filters whose population happens to be the whole table; the impossible-value probe
answers 0 for them and they get the NOTE, not the WARNING.

Live check through the real MCP server and NetBox 4.3.3 (2026-11-09):

| call | header |
|---|---|
| `dcim.device` `{tenant_id: 14, role: pdu}` | `matched_count=12 returned_count=12 complete=true`, no warning |
| `dcim.device` `{has_primary_ip: "no"}` limit 100 | `141 / 100 / complete=false`, INCOMPLETE offset=100, WARNING naming `has_primary_ip` (probe: 141 of 141) |
| `dcim.poweroutlettemplate` `{device_type_id: 8}` | `8 / 8`, NOTE (probe `999999999` -> 400: honoured) |
| `dcim.poweroutlet` `{device_id: [25 ids]}` limit 1 | `200 / 1`, INCOMPLETE, NOTE (probe `[999999999]` -> 400: honoured) |
| `dcim.device` `{name: "zzz-none"}` | `0 / 0 / complete=true`, no warning |
| `dcim.device` `{tenant_id: None}` | sent as `"null"`, `15 / 15`, no warning |
| change-logs `{user_id: 9}` limit 5 | `3543 / 5 / complete=false`, INCOMPLETE, NOTE (probe -> 0: honoured; the seeding user made every change) |
| `dcim.device` `{devicerole_id: 5}` | `TOOL_VALIDATION_ERROR` as before, no header |

Unit tests: `tests/test_filters.py::TestResultEnvelope` (header fields, INCOMPLETE offset,
WARNING / NOTE / ambiguous wording, scope exemptions, payload fail-open, endpoint mapping,
totals cache and TTL, probe verdicts incl. list shape and caching, wrapper end-to-end on a
list tool and a non-list tool) plus the existing content-and-artifact test now asserting the
header is block 0.

## Not claimed

- No benchmark effect is claimed yet. The recorded runs show what the detector *would have*
  flagged; what the model does with the warning is measured by the session ladder (below)
  and the next full v5 run.
- The detector cannot see a filter that is honoured but wrong (the right key with the wrong
  id), nor a dropped filter on a call that also carries an honoured one (`prefix` ignored
  beside `vrf_id` honoured returned 436 of 616, not the total). The schema layer and the
  value rules remain the first line.
- Totals are cached for ten minutes; an instance being edited during a run can drift by a
  few objects and the warning then stays silent. The static benchmark instance does not.

## Gate: session ladder

**Ladder 1, count-only detector** (`docs/traces/2026-11-09_netbox-session_result-envelope.*`,
Strata, 11 turns): 827 s, 39 tool calls, 7.0 of 10 correct, against 839 s / 17 calls /
10 of 10 on 2026-10-20 (llama-server) and an all-correct web-chat thread on the same
questions earlier the same day with the pre-envelope code. The detector fired twice, both
coincidences: `device_type_id=8` on power-outlet-templates (8 of 8) and a 25-device
`device_id` list on power-outlets (200 of 200). The transcript shows the detour started
*before* either warning: on turn 4 the model resolved "Halvorsen PDU" through the device
type (`model__ic=PDU` -> type 8) instead of the tenant, so turns 4-6 counted both tenants'
25 PDUs and 200 outlets. That is plan variance the harness documents (9 vs 14 calls on
identical config), not the header; but two ambiguous warnings landing on an already-wrong
scope are the worst case for the count-only rule, and it is why the probe was added.

**Ladder 2, probe detector** (`docs/traces/2026-11-09_netbox-session_result-envelope-probe.*`,
Strata, same 11 questions): **837 s, 24 tool calls, 10 of 10 correct**, against 840 s / 17 /
10 of 10 on 2026-10-20. Zero whole-table hits (the model scoped by tenant this time, so no
coincidence arose), zero validator rejections, two tool-argument errors on turn 10 (the model omitted a
required `filters` / `object_type` argument; pre-existing behaviour, recovered). Every turn's header carried counts and the complete flag; no WARNING
or NOTE was needed. The gate is therefore "no harm on the ladder"; the detector's value is
shown by the replay and the live checks, and will be measured where it fires, on the next
full v5 run.

| ladder | server | secs | tool calls | correct |
|---|---|---|---|---|
| 2026-10-20 tuple-fix | llama-server | 840 | 17 | 10 / 10 |
| 2026-11-09 envelope, count-only | Strata | 827 | 39 | 7 / 10 |
| 2026-11-09 envelope, probe | Strata | 837 | 24 | 10 / 10 |

## Full v5 with the envelope (2026-11-10)

`EVAL_MODELS=llamacpp:qwen3.8-flash-next-UD-Q4_K_XL EVAL_VARIANT=envelope-full
EVAL_MAX_CONCURRENCY=1 ./venv/bin/python -m tests.eval.run_matrix_v5`, 2026-11-09 22:44 to
2026-11-10 04:05 UTC, on the merged code (master `b33a8ce`). LangSmith
`llamacpp-qwen3.8-flash-next-UD-Q4_K_XL-v5-envelope-full-ced8482f`; harness record
`docs/traces/2026-11-10_netbox-benchmark-v5_envelope-full.md`. Compared with the 2026-11-08
`...-v5-strata-full-00b39a92` run: same server, dataset, evaluators and judge (`gpt-oss:20b`),
the envelope the only change.

| run | correct | completeness | entity cov | agent s | model calls | tool calls | errors |
|---|---|---|---|---|---|---|---|
| 2026-11-08 strata-full | 0.939 | 0.972 | 0.908 | 8,603 | 412 | 400 | 0 |
| 2026-11-10 envelope-full | **0.961** | 0.972 | 0.923 | **8,060** | **384** | **387** | 0 |

Per tier: simple 0.983 -> 0.983 (tools 3.1 -> 2.93), medium 0.917 -> 0.967 (4.27 -> 3.97),
advanced 0.917 -> 0.933 (5.97 -> 6.0). Five questions changed score: four up (two medium
null-relation questions, "hypervisor hosts with no VMs" 0 -> 1 and "devices not at
Dunder-Mifflin sites" 0.5 -> 1, and two advanced), one down ("Google Cloud clusters host
VMs?" 1 -> 0.5, where both runs answered "no, 0 VMs on all 23 clusters" and only the judge
differed). Judge noise on a 90-question set is about ±0.02, so the correctness gain is at the
edge of significance; the 6 % fewer model calls and 3 % fewer tool calls are consistent with
the model no longer re-querying to check counts it can now read in the header.

**What the detector did.** 304 headers; 42 `INCOMPLETE:` lines (paginated results the model
had to continue or raise `limit` on); 2 whole-table hits, both resolved by the probe to NOTE
(`user_id=9` on change-logs, 3,543 of 3,543; `object_id=10` + `object_type` on
contact-assignments, 3 of 3), exactly the two coincidences the replay predicted; **0 WARNINGs**
(the model sent no silently-ignored key in this run) and 0 ambiguous headers. Three tool errors
in the log were all the pre-existing pydantic `filters: Missing required argument` case (the
model omitted `filters`), recovered on the next call. So this run measures "no harm plus the
header's own value" again; the WARNING path is still proven only by the replay and live
checks, because the benchmark model did not reproduce the dropped-value mistake tonight.
