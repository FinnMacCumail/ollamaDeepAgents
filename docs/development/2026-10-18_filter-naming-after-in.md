# 2026-10-18: After `__in` — four more filters NetBox ignores, inverts or rejects

**Question.** ADR-0041 turned one silently-ignored filter (`__in`) into a structured error
and halved the tool calls on the question that exposed it. With the September and October
v5 runs both in LangSmith, were there other filter-naming mistakes costing model calls?

**Method.** Dumped every tool call of both 90-question runs (497 and 439), classified the
`netbox_get_objects` calls that errored, returned an empty set and were retried with
different keys, or returned the unfiltered-size set with a filter present, plus every
`netbox_graphql` call that returned `errors`. Then verified each suspect filter live
against NetBox 4.3.3 with the read-only token.

## What the runs showed

| category (October run, 439 tool calls) | calls | questions |
|---|---|---|
| GraphQL query rejected by NetBox | 20 | 9 |
| GraphQL schema introspection (mostly preceding the above) | 21 | 9 |
| "no X assigned" written as `__empty` / `__isnull` / `__null` / `__n: null` | 9 | 5 |
| tenant looked up as a `circuits.provider` (always empty) | 7 | 5 |
| ip-address containment / VRF filter wrong (`within`, `without`, `vrf=`) | 3 | 2 |
| slug-vs-name 400s (`site=HVL-SEA-DC1`, `tenant=halvorsen-logistics`) | 2 | 2 |

41 suspect calls, 9% of the run, roughly 23 minutes of the 5.3 h at 34 s per following
model call. September: 67 calls, 13%. The `__in` fix had already removed its share
(8 uses on 5 questions in September, 0 in October).

## Live verification (NetBox 4.3.3, read-only token, 2026-10-18)

`dcim.device`: 141 total, 15 with no tenant.

| filter | HTTP | count | verdict |
|---|---|---|---|
| `tenant_id=null` | 200 | **15** | correct, the only working form |
| `tenant__empty=true` | 200 | 141 | **silently ignored** |
| `tenant__isnull=true` | 200 | 141 | **silently ignored** |
| `tenant_id__empty=true` | 200 | 141 | **silently ignored** |
| `tenant__n=null` / `tenant_id__n=null` | 200 | 126 | **the complement** (devices WITH a tenant) |
| `has_primary_ip=false` | 200 | 97 | correct (dedicated boolean filter) |
| `primary_ip4__n=null` | 200 | 44 | complement again |

`ipam.ipaddress`: 616 total.

| filter | HTTP | count | verdict |
|---|---|---|---|
| `parent=10.0.0.0/8` | 200 | 436 | correct |
| `within=10.0.0.0/8` | 200 | 616 | **silently ignored** (prefix-only filter) |
| `without=...` | 400 | — | not a filter |
| `vrf=hvl-guest` | 400 | — | wants the route distinguisher |
| `vrf_id=null` | 200 | 30 | correct (global table) |

Relation values: `site=hvl-sea-dc1` 200/30, `site=HVL-SEA-DC1` 400; `tenant=hvl` 200/68,
`tenant=halvorsen-logistics` 400 (the slug is `hvl`). `circuits.provider?name__ic=halvorsen`
is 0: Halvorsen Logistics is a tenant; its circuits are `circuits.circuit?tenant_id=14` (14).
`circuits/?type_id=3` (point-to-point) is genuinely 0 — not a filter problem.

GraphQL (strawberry, introspected): `DeviceFilter.id`, `site_id`, `tenant_id`, `device_id`
are plain `ID` scalars. `{id: [146, 147]}` and `{id: {in_list: [...]}}` both fail with
*"ID cannot represent a non-string and non-integer value"*; `{tenant_id: null}` returns all
141 devices. `StrFilterLookup` is `exact, is_null, in_list, i_exact, contains, i_contains,
starts_with, i_starts_with, ends_with, i_ends_with, regex, i_regex` — so `{name: {in_list:
[...]}}` works and `icontains` does not. `pagination: {limit, offset}` works; `limit:` is an
unknown argument. Alias cap is 10. **The GraphQL skill stated that `{id: [6, 7, 8]}` is
valid**; six of October's twenty GraphQL failures were the model following that line.

## Changes

1. **`src/tools/netbox_tools.py`** — `validate_filter(filter_dict, object_type=None)`:
   - `<relation>__empty` rejected (`RELATION_FIELDS`, or any `*_id` key) → "use `<relation>_id: null`".
   - `<relation>__n` with a null value rejected → names the complement and the right form.
   - `suggest_alternative` for `__null`/`__isnull`/`__empty`/`__n` on relations gives `_id: null`.
   - On `ipam.ipaddress`: `within`/`within_include`/`without`/`contains` rejected → `parent`.
   - On `ipam.*`: `vrf` rejected → `vrf_id`.
   - The tool wrapper passes `object_type` through.
2. **`src/middleware/filter_recovery.py`** — `null_relation` and `ip_parent_filter` error
   types with recovery strategies; `_extract_filter` understands "Invalid filter pattern:".
3. **`src/tools/netbox_graphql.py`** — `_validate_filter_grammar` runs after the read-only
   check, before HTTP: `filter:` → `filters:`; `limit:`/`offset:` → `pagination`; any other
   argument on a `_list` field → "put it inside filters"; list or lookup object on an ID key;
   `<x>_id: null`; more than 10 aliases. Tool description updated to match.
4. **Skills** — `netbox-graphql`: the ID-list claim reversed, `filters:` plural, exact lookup
   names, `pagination`, alias cap, the null trap. `netbox-mcp-filters`: new *UNASSIGNED
   RELATIONS* and *TENANTS OWN CIRCUITS* sections; `empty` and `n` rows corrected; `parent`
   vs `within` on ip-addresses; `vrf_id`.
5. **System prompt** — circuit → tenant (owner) relationship; the `_id: None` rule.
6. **Tests** — `tests/test_filters.py` (validator + recovery), `tests/test_netbox_graphql.py`
   (grammar pre-checks, parametrised over the recorded failure shapes and the valid forms).

## What this does not fix

The tenant-as-provider detour and the `name` → `name__ic` → unfiltered fall-through are
prompt/skill guidance, not validator rules: a provider name query is a legitimate call, so
it cannot be rejected. The 10-alias cap and `pagination` grammar are instance facts for
NetBox 4.3.3 and should be re-verified on upgrade, as should every "silently ignored" row.

## Gate: the session harness, same 11 questions and order as 2026-10-06

Recorded in `docs/traces/2026-10-18_netbox-session_filter-naming.{md,json}` (server
b11713, `--load-mode none`, node 1, `numa_balancing=0`; the 6 October run was on the old
server). Per turn, seconds / tool calls / score:

| turn | 2026-10-06 | 2026-10-18 |
|---|---|---|
| 1 devices at HVL-SEA-DC1 | 132 / 2 / 1.0 | 73 / 2 / 1.0 |
| 2 racks at HVL-SEA-DC1 | 34 / 1 / 1.0 | 24 / 1 / 1.0 |
| 3 rack with most devices | 87 / 1 / 1.0 | 55 / 4 / 1.0 |
| 4 outlets per PDU | 131 / 7 / 0.0 | 240 / 7 / **1.0** |
| 5 outlets in use | 177 / 1 / 0.5 | 171 / 2 / **1.0** |
| 6 PDUs with any outlet in use | 27 / 0 / 0.5 | 117 / 12 / 0.5 |
| 7 power feeds not active | 72 / 1 / 1.0 | 210 / 3 / 1.0 |
| 8 PDUs fed by a modelled feed | 76 / 1 / 0.0 | 84 / 1 / **1.0** |
| 9 hypervisor power supplies | 124 / 1 / 1.0 | 132 / 3 / 1.0 |
| 10 feeds DC vs branch | 303 / 4 / 1.0 | 212 / 1 / 1.0 |
| 11 summary | 150 / 0 | 126 / 0 |
| **total** | **1,312 s / 20 calls / 7.0 of 10** | **1,444 s / 36 calls / 9.5 of 10** |
| context at turn 10, decode | 54,101 tok, 12.1 tok/s | 76,979 tok, 14.0 tok/s |
| validation errors | 0 | 0 |

Reading. **No regression from the new rules**: zero validation errors fired, because this
ladder contains none of the null / provider / GraphQL patterns the rules target; it is the
`__in` ladder, kept for comparability. **Correctness moved from 7.0 to 9.5 of 10**: turns 4,
5 and 8 scored the tenant-wide population (12 PDUs, 96 outlets) where October scoped to the
site (6 PDUs, 48 outlets) — the contamination the harness documented on 2026-09-25. **Wall
time is 10% longer** despite the faster server, and the call column says why: 36 calls
against 20, twelve of them on turn 6 where October answered from context with none, which
also grew the context 40% and taxed every later turn. That is the same-question planning
variance the harness header warns about (9 vs 14 under identical config), and in this run it
bought the right population. One run each way; the full v5 harness is the measurement that
can show the projected ~20-30 call saving.

## Full 90-question v5 run on this change (2026-10-18/19)

Experiment `llamacpp-qwen3.8-flash-next-UD-Q4_K_XL-v5-filter-naming-full-8b847369`, trace
`docs/traces/2026-10-19_netbox-benchmark-v5_filter-naming-full.md`. Same harness, dataset,
evaluators, judge and server configuration as the 17 October run; the only difference is
this change.

| | 2026-09-23 | 2026-10-17 (server change) | 2026-10-18 (this change) |
|---|---|---|---|
| wall, first question to last | 6.78 h | 5.30 h | **5.26 h** |
| agent time, sum of 90 | 19,345 s | 14,396 s | **14,248 s** |
| mean / median / max per question | 215 / 153 / 1,588 s | 160 / 120 / 761 s | **158 / 113 / 743 s** |
| simple / medium / advanced mean | 109 / 206 / 331 s | 97 / 168 / 216 s | 91 / 173 / 211 s |
| questions faster than the previous run | — | 73 of 90 | 48 of 90 |
| correctness | 0.906 | 0.922 | **0.928** |
| completeness | 0.944 | 0.944 | **0.978** |
| tool calls per question | 5.52 | 4.88 | 4.99 |
| errors | 0 | 0 | 0 |

**Where the targeted calls went** (every tool call classified, both October runs):

| category | 17 Oct | 18 Oct |
|---|---|---|
| "no X assigned" fumble that reached NetBox (`__empty`, `__n: null`, ...) | 4 | **0** |
| `<relation>_id: null` used correctly | 1 | **13** |
| ip-address `within` / `vrf` that reached NetBox | 2 | **0** |
| REST 400 from a filter value | 2 | **0** |
| REST validation error returned to the model | 1 | 0 |
| tenant looked up as a provider | 7 | **2** |
| GraphQL queries issued / questions using GraphQL | 31 / 9 | 53 / 18 |
| GraphQL accepted by NetBox | 15 | **30** |
| GraphQL caught by the pre-check before HTTP | 0 | 7 (6× `limit:`, 1× id list) |
| GraphQL rejected by NetBox | 16 | 16 |
| ... of which grammar (`filter:`, `limit:`, id list, unknown argument) | 8 | **0** |
| ... of which field/type names (`Cannot query field`, `not defined by type`) | 2 | 14 |
| ... of which a lookup object on a nested relation id (`tenant: {id: {exact: 14}}`) | 0 | 2 |
| schema introspections | 21 | 30 |
| empty results / followed by a retry with other keys | 30 / 4 | 38 / 5 |
| `netbox_get_changelogs` 400 (`action=created`) | 0 | 3 |

**Reading.** On the REST side the change did what it was built to do: every "no X assigned"
fumble, every ip-address containment mistake and every filter-value 400 disappeared, and the
model wrote the working null form thirteen times. The tenant-as-provider detour is only
reduced, as expected of guidance rather than a rule. On the GraphQL side the grammar errors
are gone from NetBox's rejections, but the model now uses GraphQL twice as often (53 queries
in 18 questions against 31 in 9) — the corrected skill reads as more usable — and the
residual rejections are field-name mistakes the pre-check cannot know about. Net: the same
number of GraphQL rejections, more schema calls, more successful GraphQL answers, and three
points of completeness. Wall time is a wash (1% faster, median 6% faster, 48 of 90 quicker)
with correctness and completeness up. The projected 20–30 call saving did not materialise as
wall time because the GraphQL usage grew into the space the REST fixes freed.

**Two new findings from this run, not yet fixed.**
1. `netbox_get_changelogs(action="created")` is a 400 three times: NetBox's values are
   `create` / `update` / `delete` (verified live: `action=create` → 3,158, `action=created` →
   400), and the MCP server's own docstring says *"(created, updated, deleted)"* — the same
   shape as the `id__in` example that caused ADR-0041.
2. The GraphQL pre-check only inspects top-level filter keys; `tenant: {id: {exact: 14}}` and
   `device: {id: {in_list: [...]}}` reached NetBox twice. The rule should apply to `id` keys at
   any nesting depth (the valid nested form is `tenant: {id: 14}`).

## Follow-up fixes (2026-10-19)

Both findings from the full run are now closed; unit-tested (8 new tests, 71 passing in the two
files) and the change-log rule exercised through the real wrapped MCP tool, but **not re-gated
on the full harness** — three 400s and two GraphQL rejections per run is below what a single
run can resolve.

1. **Change-log `action` values.** `validate_filter` rejects `{"action": "created" | "updated" |
   "deleted"}` with the bare verb in the message; the tool wrapper also catches `action` as a
   direct argument; the recovery middleware has a `changelog_action` strategy; the filters skill
   says so under *STATUS / ENUM / SLUG VALUES*. The local MCP server copy's docstring is
   corrected (commit `d05d3f4` in `netbox-mcp-server`), diff saved as
   `2026-10-19_netbox-mcp-server-changelog-action.patch` beside the `__in` one for the same
   upstream report. Verified: `action=create` → 3,158, `update` → 363, `delete` → 22;
   `created`/`updated`/`deleted` → 400 "Select a valid choice".
2. **GraphQL ID rule at any depth.** `_check_filter_object` now recurses into every nested
   relation filter, so `tenant: {id: {exact: 14}}`, `device: {id: {in_list: [...]}}`,
   `site: {id: [30, 28]}` and `site: {region: {id: [1, 2]}}` are rejected before HTTP with the
   nested path in the message; `tenant: {id: 14}` and string lookups inside relations pass.
   The GraphQL skill's ID bullet says the rule holds inside nested filters.
