# Prototype replay: a schema-driven filter validator over the recorded benchmark tool calls

Scope: a throwaway validator built only from NetBox 4.3.3's OpenAPI file, replayed over every recorded `netbox_get_objects` / `netbox_get_changelogs` call of four 90-question v5 runs (2026-09-23, 2026-10-17, 2026-10-18, 2026-10-19), with every distinct (endpoint, key, value) ground-truthed live against NetBox (GET only).

Artefacts (all in this folder, nothing in the repo was modified):
- `proto_replay.py` — the prototype (index build, replay, live checks, enum checks, difflib suggestions, cost timings).
- `proto_results.json` — per-call records (1,237 calls), enum checks, suggestions, cost block.
- `live_checks.json` — 349 distinct live GETs: `endpoint|key|value` -> http, count, unfiltered count, verdict, exact URL sent.
- `langsmith_tool_runs_1018_1019.json` — cached LangSmith tool runs of the two later projects (449 + 404 runs), pulled once with `Client().list_runs(project_name=..., run_type="tool")`.

Method notes. Endpoint = `/api/` + `NETBOX_OBJECT_TYPES[object_type]["endpoint"]` + `/` (`netbox_get_changelogs` -> `/api/core/object-changes/`). A key is "found" iff it is literally a `get.parameters[].name` of that path (so `name__ic`, `tenant_id__n` are their own names; list values are the bare key, as NetBox repeats the query param). Live verdict per (endpoint, key, value): `rejected_400`; `honoured` (count differs from the unfiltered count); `ignored_or_coincident` (count equals the unfiltered count); `dropped_by_requests` (value is JSON `null` — see KQ3). Coincident cases were then probed with a nonsense value (`999999`): an honoured key answers 400 or 0, an ignored key answers the unchanged total.

## KQ1. How many filter keys are found / not found per run, and what are the unknown keys?

### Takeaway
Across 1,237 calls and 1,190 filter keys the schema index finds 1,136 (95.5%) and rejects 54 key uses (27 distinct endpoint/key pairs) on 52 calls. Every one of the 27 distinct unknown keys was verified live to be silently ignored by NetBox (filtered count == unfiltered count, unchanged under a nonsense value): zero false positives in the recorded data.

### Cited Findings
- Index: 145 list endpoints, 11,520 query parameters, 919 with an enum (49 inline, the rest resolved through `x-spec-enum-id` from `components`) — [proto_results.json `cost`](proto_results.json)
- Per run (calls = get_objects + get_changelogs; keys = filter keys; rejected calls = calls with at least one non-exempt unknown key) — [proto_replay.py summary](proto_replay.py):

| run | calls | get_objects | changelogs | keys | found | not found | calls rejected | questions affected |
|---|---|---|---|---|---|---|---|---|
| 2026-09-23 | 307 | 283 | 24 | 299 | 276 | 23 | 22 | 12 |
| 2026-10-17 | 315 | 292 | 23 | 293 | 279 | 14 | 14 | 10 |
| 2026-10-18 | 307 | 280 | 27 | 286 | 277 | 9 | 9 | 1 |
| 2026-10-19 | 308 | 279 | 29 | 312 | 304 | 8 | 7 | 1 |
| total | 1,237 | 1,134 | 103 | 1,190 | 1,136 | 54 | 52 | — |

- No recorded call used an object_type absent from `NETBOX_OBJECT_TYPES` (`unknown_endpoint=0` in all four runs) — [proto_replay.py summary](proto_replay.py)
- None of the 54 unknown keys was an MCP-level parameter (`limit/offset/ordering/q/fields/brief`): the model always passed those as tool arguments, never inside `filters`; `q`, `limit`, `offset`, `ordering` are in the schema anyway, `fields` and `brief` are not — [proto_results.json](proto_results.json); [schema suffix/param scan](proto_results.json)
- The 27 distinct unknown keys, with uses, runs, live verdict and the recorded outcome of the call (all 54 uses returned HTTP 200 with the unfiltered population, except the two that the existing hand-written validator had already intercepted) — [live_checks.json](live_checks.json):

| endpoint | key | uses | runs | live (filtered/total) | nonsense-value probe | class |
|---|---|---|---|---|---|---|
| dcim/devices | `devicerole_id` | 6 | 09-23 | 141/141 | — | true catch (ignored); right key `role_id` |
| dcim/cable-terminations | `cable_id` | 5 | all four | 381/381 | 381 (ignored); `cable=999999` -> 400 | true catch; right key `cable` |
| ipam/vlans | `vlan_group_id` | 5 | 10-18 | 94/94 | — | true catch; right key `group_id` |
| dcim/devices | `tenant__empty` | 4 | 09-23, 10-17 | 141/141 | — | true catch; right form `tenant_id="null"` |
| ipam/ip-addresses | `prefix` | 3 | 09-23 | 616/616 | — | true catch; right key `parent` |
| circuits/circuits | `circuit_type_id` | 3 | 10-17, 10-18, 10-19 | 43/43 | — | true catch; right key `type_id` |
| dcim/devices | `device_role_id` | 3 | 10-17, 10-18 | 141/141 | — | true catch; right key `role_id` |
| dcim/power-feeds | `site_id__in` | 2 | 09-23 | 59/59 | — | true catch; right form `site_id=[...]` |
| tenancy/contact-assignments | `assigned_object_id` | 2 | 09-23, 10-19 | 3/3 | 3 (ignored); `object_id=999999` -> 0 | true catch; right key `object_id` |
| tenancy/contact-assignments | `assigned_object_type` | 2 | 09-23, 10-19 | 3/3 | — | true catch; right key `object_type` |
| dcim/devices | `rack` (value null) | 2 | 09-23, 10-19 | 141/141 | dropped (null) | true catch (key also absent: slug filter is `rack_id`) |
| ipam/ip-addresses | `without` | 2 | 10-17 | 616/616 | — | true catch (not a filter here; `parent`) |
| tenancy/tenants | `group_n` | 1 | 09-23 | 12/12 | 12 (ignored) | true catch; typo of `group__n` |
| virtualization/clusters | `cluster_type_id` | 1 | 09-23 | 35/35 | 35 (ignored); `type_id=999999` -> 400 | true catch; `type_id` |
| dcim/power-ports | `device_id__in` | 1 | 09-23 | 156/156 | — | true catch; `device_id=[...]` |
| virtualization/clusters | `id__in` | 1 | 09-23 | 35/35 | — | true catch; `id=[...]` |
| dcim/interfaces | `ip_address_id` | 1 | 09-23 | 2712/2712 | — | true catch; no such filter (query ip-addresses with `interface_id`) |
| virtualization/virtual-disks | `tenant_id` | 1 | 10-17 | 8/8 | 8 (ignored) | true catch; virtual disks have no tenant filter |
| ipam/prefixes | `tenant__null` | 1 | 10-17 | 132/132 | — | true catch (hand-written validator already rejected it) |
| ipam/prefixes | `tenant__empty` | 1 | 10-17 | 132/132 | — | true catch; `tenant_id="null"` |
| dcim/power-panels | `tenant_id` | 1 | 10-17 | 7/7 | 7 (ignored) | true catch; power panels have no tenant filter |
| ipam/ip-addresses | `parent_prefix` | 1 | 10-17 | 616/616 | — | true catch; `parent` |
| dcim/devices | `device_role` | 1 | 10-17 | 141/141 | — | true catch; `role` |
| tenancy/contact-assignments | `contact_role_id` | 1 | 10-18 | 3/3 | 3 (ignored); `role_id=999999` -> 400 | true catch; `role_id` |
| virtualization/virtual-machines | `host_id` (null) | 1 | 10-19 | 208/208 | dropped | true catch (no such key; `device_id`) |
| dcim/cable-terminations | `device_id` | 1 | 10-19 | 381/381 | — | true catch; `termination_type`+`termination_id` |
| extras/object-types | `model__in` | 1 | 10-19 | 156/156 | — | true catch (hand-written validator already rejected it); `model=[...]` |

- The schema contains no `__in` and no `__isnull` parameter anywhere; the only lookup suffixes it lists are `n` (2,039), `empty` (899), `gte/lte` (497 each), `gt/lt` (493 each), `ic/ie/iew/isw/nic/nie/niew/nisw` (428 each), `after/before` (4 each) — [schema scan in this session](proto_results.json)
- The only honoured query parameters that are absent from the schema are the generic ones (`fields`, `brief`, and NetBox's `export`/`format`) and custom-field filters `cf_<name>`; the live instance defines 1 custom field; no recorded call used any `cf_` key — [schema scan; live `/api/extras/custom-fields/` count=1](live_checks.json)
- `__empty` is listed only on scalar fields (e.g. `status__empty`, `name__empty`, `serial__n`), never on relation fields (`tenant__empty`, `tenant_id__empty` are absent from `/api/dcim/devices/`), so the 2026-10-18 "silently ignored" rows for `tenant__empty`/`tenant_id__empty` are exactly what the schema says — [schema parameter list for devices](proto_replay.py)

### Inferences
- Classification of the 54 unknown key uses: (a) true catches 54, (b) false positives 0, (c) exempt MCP-level 0. Thirteen of the 27 keys are "wrong name for an existing filter" (`devicerole_id`, `device_role_id`, `device_role`, `circuit_type_id`, `cluster_type_id`, `vlan_group_id`, `cable_id`, `assigned_object_*`, `contact_role_id`, `parent_prefix`, `group_n`, `rack`, `host_id`), four are the `__in` family, four are the null-relation family (`tenant__empty` x2 endpoints, `tenant__null`), three are ip-address containment (`prefix`, `without`, `parent_prefix`), and three are filters that do not exist on that endpoint at all (`ip_address_id` on interfaces, `tenant_id` on virtual-disks and power-panels, `device_id` on cable-terminations).
- Those "wrong name for an existing filter" keys (31 uses, 17 calls in the two latest runs alone) are invisible to the hand-written validator, which only reasons about suffixes and a few named keys. They were not retried (recorded outcome `ok`), i.e. they produced wrong populations rather than wasted calls, which is why the 2026-10-18 analysis did not count them.
- The three "no such filter on this endpoint" cases are the only ones where a rejection would not have an immediate key fix; the right message is "this endpoint has no filter named X; its relation filters are ...".

### Gaps
- Four of the 27 keys came only from the September run, which pre-dates several prompt/skill fixes; the rates per run above are the honest measure, the 27-key union is an upper bound of what a validator would see today.
- The ground truth is one NetBox 4.3.3 instance; `cf_*`, `export`, `format` were not exercised by any recorded call, so their false-positive risk is reasoned, not measured.

## KQ2. Which known silent-ignore forms are in the schema (misses the schema cannot catch)?

### Takeaway
The known forms are split: `__in`, `<relation>__empty`, `__isnull`, `__null`, `prefix`/`within`/`without` on ip-addresses are NOT in the schema (caught). What the schema lists but NetBox does not honour as the model intends are value-level: `<relation>__n` with `true`/`null` (400 or the complement), `vrf=<name>` on ipam (400, wants the route distinguisher), `role=<non-slug>` (400), and above all the JSON `null` value on any key, which never reaches NetBox at all (KQ3).

### Cited Findings
- Found keys whose live check was not `honoured` (schema misses), with uses and the recorded outcome — [live_checks.json](live_checks.json), [proto_results.json](proto_results.json):

| endpoint | key | value | uses (runs) | live | recorded outcome | class |
|---|---|---|---|---|---|---|
| dcim/devices | `tenant_id` | null | 7 (10-18 x4, 10-19 x3) | dropped, 141/141 | 200, unfiltered | miss (value) |
| core/object-changes | `action` | created/updated/deleted | 6 (09-23 x3, 10-18 x3) | 400 | 400 | caught by enum check |
| dcim/devices | `primary_ip4` | null | 4 (10-18 x2, 10-19 x2) | dropped | 200 | miss (value) |
| virtualization/virtual-machines | `primary_ip4_id` | null | 3 (10-18, 10-19 x2) | dropped | 200 | miss (value) |
| ipam/prefixes | `tenant_id` | null | 3 (10-18 x2, 10-19) | dropped | 200 | miss (value) |
| dcim/devices | `rack_id` | null | 3 (10-18, 10-19 x2) | dropped | 200 | miss (value) |
| tenancy/tenants | `group` / `group_id` | null | 2 + 2 | dropped | 200 | miss (value) |
| ipam/prefixes | `tenant` / `vlan_id` | null | 2 + 2 | dropped | 200 | miss (value) |
| dcim/devices | `primary_ip4_id` | null | 2 (10-18, 10-19) | dropped | 200 | miss (value) |
| virtualization/virtual-machines | `tenant_id` | null | 1 (10-19) | dropped, 208/208 | 200, count 208 | miss (value) |
| ipam/ip-addresses | `vrf` | "hvl-guest" / 8 | 2 (10-17, 10-19) | 400 | 400 / hand-validator error | miss (value; hand-written rule catches) |
| dcim/devices | `tenant__n` | true | 1 (10-17) | 400 | 400 | miss (value) |
| dcim/devices | `tenant__n` | null | 1 (10-17) | dropped, 141/141 | 200, count 141 | miss (value; hand-written rule catches) |
| dcim/devices | `primary_ip4__n` | true | 1 (09-23) | 400 | 400 | miss (value) |
| dcim/devices | `role` | "hypervisor" | 1 (10-19) | 400 (not a slug) | 400 | miss (value) |
| dcim/devices | `serial__n` | false | 1 (09-23) | 141/141, honoured but vacuous | 200 | not catchable |

- Coincident full counts that are genuinely honoured (not misses): `object-changes?user_id=9` (3543/3543; `user_id=999999` -> 400), `user=seeder` (`user=nobody_zz` -> 400), `time_after=2020-01-01` (`2099-01-01` -> 0), `contact-assignments?object_id=10` (3/3; `object_id=999999` -> 0) — [nonsense-value probes in this session](live_checks.json)
- Schema value types for the null-used keys: `tenant_id` on devices is `array of integer, nullable: true`; `primary_ip4_id`, `rack_id` are `array of integer` (no nullable flag); `tenant`, `tenant__n`, `primary_ip4`, `group_id` are `array of string` — [schema parameters](proto_replay.py)
- `vrf` on ip-addresses is `array of string` with description "VRF (RD)"; the schema has no enum or pattern for slugs, so `site=HVL-SEA-DC1` / `tenant=halvorsen-logistics` (the 2026-10-18 slug-vs-name 400s) are not detectable from the schema. Note: neither of those two calls appears as a recorded REST 400 in the 2026-10-17 tool runs (the only recorded REST 400s are `tenant__n=true` and `vrf=hvl-guest`) — [proto_results.json outcomes](proto_results.json); [2026-10-18 doc](/home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md)

### Inferences
- Key-name validation from the schema catches the whole `__in` / `__empty`-on-relation / `__isnull` / `__null` family that ADR-0041 and the 2026-10-18 change addressed by hand, because NetBox's filterset generator simply never emits those names. The misses are all value-level (type/slug/RD/null) and are best handled by a thin value layer: enum membership (KQ4), `nullable`/integer typing where the schema gives it, and the existing hand rules for `vrf`, `__n` with null, and `action`.
- Of the 1,136 found keys, 46 uses were not honoured as intended; 35 of those are the JSON-null problem (KQ3), 6 are enum values (caught), 5 are 400s on values the schema cannot know.

### Gaps
- `nullable: true` appears only on some `*_id` items (`tenant_id` yes, `rack_id`/`primary_ip4_id` no) although NetBox honours `rack_id=null` too; the flag is not a reliable "null is allowed" signal, so a null rule should be rule-based, not schema-based.

## KQ3. The JSON-null finding: `<relation>_id: null` never reaches NetBox through the MCP tool

### Takeaway
Through the real MCP tool, `netbox_get_objects("dcim.device", {"tenant_id": null})` returns count 141 (all devices, tenants included) while `{"tenant_id": "null"}` returns 15: `requests` drops parameters whose value is `None`, so the 13 (10-18) and 16 (10-19) "correct" null-form key uses praised in the 2026-10-18 write-up were unfiltered queries. Neither the schema nor the current hand-written validator catches this.

### Cited Findings
- Live MCP tool calls in this session: `filters={"tenant_id": null}, fields=[id,name,tenant], limit=3` -> `count: 141`, first results have tenant Halvorsen Logistics / Dunder-Mifflin; `filters={"tenant_id": "null"}` -> `count: 15`, results have `tenant: null` — [mcp__netbox__netbox_get_objects calls, this session]
- The MCP server sends `self.session.get(url, params=params)` with no None handling — [netbox_client.py:220](/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server/src/netbox_mcp_server/netbox_client.py)
- Recorded evidence: the 2026-10-18 call `{"tenant_id": null}` on dcim.device recorded `count:141` with `boi-br04-rtr01` (a Halvorsen device) first in the results; the 2026-10-19 call `virtualization.virtualmachine {"tenant_id": null}` recorded count 208 = the unfiltered total; 2026-10-17 `{"tenant__n": null}` recorded 141 — [langsmith_tool_runs_1018_1019.json](langsmith_tool_runs_1018_1019.json), [proto_results.json](proto_results.json)
- Null-valued filter keys per run: 09-23: 4 keys / 4 calls / 3 questions; 10-17: 2 / 2 / 2; 10-18: 13 / 13 / 1 question; 10-19: 16 / 15 / 1 question. Every call whose only filter was a null value recorded exactly the unfiltered total — [proto_results.json `rc` recomputation, this session]
- The 2026-10-18 doc verified `tenant_id=null -> 15` with curl (string `null` on the wire) and then counted "`<relation>_id: null` used correctly: 13" from the recorded inputs, which were JSON nulls — [2026-10-18 doc](/home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md)

### Inferences
- The fix is a one-line wire rule in the wrapper or the MCP server: `None -> "null"` for every filter value (NetBox's filtersets accept the literal string `null` for nullable FK filters). A schema-driven validator cannot see this because the key is valid; a value-level rule can.
- All 29 null-form calls in the two latest runs sat in one question each ("devices with no tenant / VMs with no primary IP"), so the correctness damage is concentrated, but the sentence "the model wrote the working null form thirteen times" in the 2026-10-18 doc is wrong as a statement about what NetBox received.

### Gaps
- Whether FastMCP or langchain-mcp-adapters could have turned JSON null into something else at the time of the runs was not tested separately; the recorded counts (141, 208) and today's live MCP call agree, which is sufficient for the conclusion.

## KQ4. Enum value mismatches

### Takeaway
Of 53 recorded uses of enum-bearing keys (36 `action`, 17 `status`), 6 carried a value outside the enum: `action=created|updated|deleted` three times each in the 09-23 and 10-18 runs, all HTTP 400 live and recorded. The enum check catches 6 of 6; there were no `status` value mistakes.

### Cited Findings
- `/api/core/object-changes/` `action` schema: `enum: [create, delete, update]`, description "* `create` - Created ..." — [netbox-openapi.json](/home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/netbox-openapi.json)
- Enum coverage requires resolving `x-spec-enum-id`: array-typed params (`status` etc.) carry only the id (870 of them), the values live in `components.schemas.<Model>.properties.<field>.value.enum`; 82 enum ids resolve, giving 919 enum-checked parameters — [proto_results.json `cost`](proto_results.json)
- Enum-checked uses: `object-changes.action` 36, `devices.status` 9, `prefixes.status` 4, `circuits.status` 4; mismatches 6, all `action` — [proto_results.json `enum_checks`](proto_results.json)
- The 10-19 run has 0 `action` mismatches (the hand-written `CHANGELOG_ACTION_FIX` landed on 10-19) — [proto_results.json](proto_results.json); [netbox_tools.py](/home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_tools.py)

### Inferences
- The enum check reproduces the 10-19 `action` fix generically and would also cover `status`, `airflow`, `face`, `role` of ip-addresses etc. without hand lists; the description text of enum params is a ready-made "valid values" message.

### Gaps
- None of the recorded calls exercised a wrong `status` value, so the false-positive risk of enum checking on `status` (e.g. a value NetBox accepts case-insensitively) was not measured.

## KQ5. Would a difflib "did you mean" have produced the right correction?

### Takeaway
Plain `difflib.get_close_matches(key, endpoint_params, n=3, cutoff=0.6)` gives the right key as top-1 for 8 of 27 unknown keys and within top-3 for 15; for 3 of the 4 `__in` keys its top-1 is the `__n` negation, an actively harmful suggestion. A small rule layer (strip unknown suffix -> bare key with list value; `__empty/__null/__isnull` on a relation -> `<rel>_id="null"`; an alias table for NetBox's shortened relation names) gets 20 of 27 right.

### Cited Findings
- difflib top-3 per unknown key — [proto_results.json `suggest`](proto_results.json): right top-1: `circuit_type_id->type_id`, `cluster_type_id->type_id`, `rack->rack_id`, `parent_prefix->parent`, `model__in->model`, `group_n->group__n`, `assigned_object_id->object_id`, `assigned_object_type->object_type`; right only lower in the list: `cable_id->[cable_end, cable, ...]`, `device_role_id->[device_type_id, ..., role_id]`, `devicerole_id->[..., role_id]`, `site_id__in->[site_id__n, site_id]`, `device_id__in->[device_id__n, device_id]`, `vlan_group_id->[tenant_group_id, group_id]`, `contact_role_id->[contact_id, ..., role_id]`; wrong or empty: `device_role->device_type`, `tenant__empty->status__empty`, `tenant__null->tenant__n`, `id__in->id__n`, `ip_address_id->mac_address__ie`, `power-panels tenant_id->tag_id`, `virtual-disks tenant_id->tag_id`, `host_id->site_id`, `cable-terminations device_id->[]`, `prefix->[]`, `without->[]`
- Rule-layer results (this session): right for the 8 difflib top-1 cases plus `device_role->role`, `device_role_id/devicerole_id->role_id`, `vlan_group_id->group_id`, `contact_role_id->role_id`, `site_id__in/device_id__in/id__in -> bare key with list`, `tenant__empty/tenant__null -> tenant_id="null"`; still wrong: `cable_id->cable_end` (should be `cable`), `ip_address_id`, `host_id->site_id` (should be `device_id`), the two endpoint-has-no-tenant cases, `cable-terminations device_id`, `prefix`, `without`

### Inferences
- The complement trap (`__in` -> `__n`, `__empty` -> `__n`) means a naive difflib message must never be emitted for `__`-suffixed keys without first stripping the suffix. The hand-written `suggest_alternative` already encodes the right answers for the suffix family; the schema adds the alias/naming cases it cannot know.
- For the 7 residual cases the correct message is not a key but a fact ("virtual disks have no tenant filter; filter by `virtual_machine_id`"), i.e. listing the endpoint's `*_id` parameters is more useful than a fuzzy match.

### Gaps
- No measurement of whether the model, given the right suggestion, actually recovers in one call; that needs a harness run, which was out of scope.

## KQ6. Engineering cost: schema size, build time, lookup time, memory, caching, unavailability

### Takeaway
Parsing the 9.3 MB schema costs 0.23 s and 26 MB transient; building the index another 0.23 s; the index itself is 3.65 MB resident (1.14 MB as JSON, 459 KB pickled, reloads in 12 ms); a per-call lookup is ~1 µs. NetBox serves the same 9.3 MB at `/api/schema/?format=json` in 0.15 s locally, so startup fetch with a vendored fallback is cheap.

### Cited Findings
- Measured on this machine, Python 3 in the project venv — [proto_results.json `cost`](proto_results.json): schema 9,313,713 bytes; read 6 ms; `json.loads` 0.232 s; index build (walk `components` + `paths` for enum ids, then 145 endpoints) 0.231 s; peak traced memory 28.7 MB (parsed doc 26.3 MB); index alone 3.65 MB; `json.dumps(index)` 1,143,470 bytes; pickle 459,145 bytes; reload of the JSON index 11.5 ms; per-call lookup mean 1,095 ns, max 81 µs (first call); live `GET /api/schema/?format=json` 200, 9,313,713 bytes, 0.150 s.
- 349 distinct live checks were needed to ground-truth 1,190 key uses; the validator itself makes no HTTP calls — [live_checks.json](live_checks.json)

### Inferences
- Caching options, from the measurements: (1) vendored pre-built index (1.1 MB JSON / 0.46 MB pickle, 12 ms load, 3.7 MB RAM) — fastest and works offline, must be regenerated on NetBox upgrade; (2) startup fetch of `/api/schema/` + build (~0.6 s, 29 MB transient, then 3.7 MB) — always matches the instance, needs the fallback; (3) lazy per-endpoint — pointless, since the schema is one document and parsing it is the whole cost. A version stamp (`info.version` is `4.3.3-Docker-3.3.0 (4.3)`) can drive "refetch when the instance version changed".
- Unavailability: because the hand-written rules remain and every unknown-key rejection is advisory-safe (0 false positives observed), the right failure mode is fail-open to the hand rules plus a log line; a stale vendored index is still correct for all 27 keys above because none of them depends on instance-specific data.

### Gaps
- Memory was measured with `tracemalloc` on the Python objects, not RSS; the server's actual RSS growth would include allocator overhead.
- The 0.15 s schema fetch is a warm NetBox (spectacular caches the rendered schema); a cold render was not measured.

## KQ7. How many of the identified wasted calls would have been prevented, and how many new ones might false positives cause?

### Takeaway
Of the 41 suspect calls of the 2026-10-17 run, a schema-only validator prevents 6 (4 null-relation fumbles, 2 `without`); 0 of the 7 tenant-as-provider calls, 0 of the 20 GraphQL calls, and 0 of the value-level 400s. It additionally rejects 8 silently-unfiltered calls in that run that the 2026-10-18 analysis did not list, and all 6 `action=created/updated/deleted` 400s (09-23 and 10-18). Measured false positives: 0 across 1,190 keys, so no new wasted calls are predicted from the recorded forms.

### Cited Findings
- 2026-10-17 breakdown of the 41 (GraphQL rejected 20, null fumbles 9, tenant-as-provider 7, ip-address containment/VRF 3, slug-vs-name 2) — [2026-10-18 doc](/home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md)
- 2026-10-17 REST calls flagged by the prototype (missing key or non-honoured value), in order: `tenant__n=true` (400, schema miss), `tenant__empty` x2 (catch), `tenant__n=null` (dropped, miss), `tenancy.tenant group=null` (dropped, miss), `virtualdisk tenant_id=14` (catch), `prefix tenant__null` (catch; hand validator already), `prefix tenant__empty` (catch), `powerpanel tenant_id=14` (catch), `circuit_type_id=3` (catch), `cable_id=183` (catch), `without` x2 (catch), `vrf=hvl-guest` (400, miss), `parent_prefix` (catch), `device_role_id=13` (catch), `device_role=hypervisor-host` (catch), `device_role_id=4` (catch) — [proto_results.json](proto_results.json)
- Head-to-head, calls rejected per run (schema validator = unknown key or enum mismatch; hand-written = current `FilterValidator.validate_filter`) — [this session's comparison script over proto_results.json]:

| run | both | schema only | hand-written only | neither |
|---|---|---|---|---|
| 2026-09-23 | 12 | 13 | 0 | 282 |
| 2026-10-17 | 6 | 8 | 2 | 299 |
| 2026-10-18 | 3 | 9 | 0 | 295 |
| 2026-10-19 | 1 | 6 | 1 | 300 |
| total | 22 | 36 | 3 | 1,176 |

- Hand-written-only rejections are exactly the value rules: `tenant__n: null`, `vrf: "hvl-guest"`, `vrf: 8` — [comparison output]
- Schema-only rejections (36 calls) are the naming family: `devicerole_id` x6, `cable_id` x5, `vlan_group_id` x5, `device_role_id` x3, `circuit_type_id` x3, `assigned_object_*` x2, `contact_role_id`, `cluster_type_id`, `group_n`, `ip_address_id`, `parent_prefix`, `rack`, `host_id`, `device_role`, `cable-terminations device_id`, `virtual-disks tenant_id`, `power-panels tenant_id` — [comparison output]
- Changelog `action` 400s: 3 in 09-23 and 3 in 10-18, all caught by the enum check; 0 in 10-19 after the hand fix — [proto_results.json `enum_checks`](proto_results.json)

### Inferences
- Prevented wasted calls on the 2026-10-17 run: 6 of 41 (15%). The larger payoff is not retries but wrong answers: 17 calls in the 10-18 and 10-19 runs (`vlan_group_id` x5, `cable_id` x2, `circuit_type_id` x2, `device_role_id`, `contact_role_id`, `cable-terminations device_id`, plus the 29 null-valued keys from KQ3) returned populations the question did not ask for and were accepted as answers.
- New wasted calls from false positives: 0 observed. The theoretical exposure is `cf_*`, `fields`, `brief`, `export`, `format` placed inside `filters`, which an exempt list removes; each rejection also costs one extra model turn (~34 s per the 2026-10-18 doc), so a rejection is only worth it when the alternative is a wrong population, which held for all 54 recorded cases.
- The two validators are complementary, not substitutes: schema for names and enums (36 extra catches), hand rules for values (`null` wire form, `__n` with null, `vrf` RD, slug case). Combined they would have rejected 61 of the 1,237 recorded calls (4.9%), with 0 observed false positives.

### Gaps
- The 2026-10-18 doc's two slug-vs-name 400s were not found among the recorded 2026-10-17 REST tool runs (only two REST 400s are recorded: `tenant__n=true`, `vrf=hvl-guest`); they may have been counted from GraphQL or by_id calls. Either way the schema cannot catch them.
- Retry-cost savings are inferred from the per-call recorded outcomes; no run was re-executed with the prototype in place.
