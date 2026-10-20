# 2026-10-20: Schema-driven filter validation, implemented (plan steps 0–5 and 7)

Implements the plan in `2026-10-20_openapi-schema-driven-filter-validation.md`. Step 6, the
full 90-question run, is deliberately **not** run yet; every other step has its offline gate
recorded below.

## Step 0 — JSON null never reached NetBox (bug fix)

`requests` drops parameters whose value is `None`, and the MCP server builds `params=`
straight from the filters dict, so `{"tenant_id": None}` arrived as no filter at all. The
tool wrapper now normalises values before the call (`normalise_filter_values`): `None` →
`"null"`, `True`/`False` → `"true"`/`"false"`, lists element-wise.
**Gate (live, through the wrapped tool):** `{"tenant_id": None}` on `dcim.device` → **15**
(was 141); `"null"` → 15; `{"has_primary_ip": False}` → 97. The 18 October note's "null used
correctly" counts are corrected in place; `without=` on ip-addresses reclassified as ignored.

## Step 1 — whitelists corrected

`regex`/`iregex` removed from `VALID_SUFFIXES` (silently ignored on 4.3.3; the lookup lands
in 4.3.5, netbox#19903), with a hint to `__isw`/`__iew`/`__ic`. `ordering` removed from the
GraphQL `_list` argument whitelist (no `_list` field takes it). The name-based GraphQL `*_id`
rule is superseded by step 5. Fixtures and tests that treated `regex` as valid updated.

## Step 2 — the index

`scripts/build_netbox_filter_index.py` fetches `/api/schema/?format=json` (9.3 MB, 0.15 s
warm), builds `{endpoint: {param: {t, m, e}}}` with `x-spec-enum-id` resolved from
`components`, maps the MCP server's 126 object types to endpoints (parsed from
`netbox_types.py`, no import), stamps `info.version`, and writes
`src/tools/netbox_filter_index.json.gz`.
**Gate:** 145 list endpoints, 11,520 parameters, 919 with enums, 126/126 object types
resolved, 27.6 KB, loads in 1 ms (plan asked for < 50 ms).

## Step 3 — layers 1 and 2 in `FilterValidator`

`validate_against_schema` runs after the hand rules: unknown key → rejected ("not a filter on
<type>; NetBox silently ignores unknown filters and returns the UNFILTERED set"); enum
mismatch → rejected with the allowed values. Exempt: `fields`, `brief`, `q`, `limit`,
`offset`, `ordering`, `export`, `format`, `cf_*`. Fail-open when the index, the object type
or the endpoint is unknown. No HTTP per call.
**Gate (replay of the 1,237 recorded calls, `scripts/replay_filter_validator.py`):**
52 of 52 calls with index-unknown keys rejected (54 uses), 0 passed despite an unknown key,
**0 false positives** against the 349 live verdicts, hand/enum rules still fire on their 9
calls (6 `action`, `tenant__n: null`, `vrf` ×2).

## Step 4 — suggestions

Order: alias table (`parent_prefix` → `parent`, `assigned_object_*` → `object_*`,
`devicetype_id` → `device_type_id`, `ip_address_id` → `address`), then "longest real
parameter the key ends with, with an alphabetic remainder" (`device_role_id` /
`devicerole_id` → `role_id`, `circuit_type_id` → `type_id`, `vlan_group_id` → `group_id`,
`contact_role_id` → `role_id`), then `_id` → bare key, then difflib with a guard that never
offers `__n` for an `__in`/`__empty`/`__null`/`__isnull` input, then the endpoint's relation
filters. **Gate:** 20 of 27 replay keys match the prototype's expected fix; the 7 "misses"
are cases where the prototype's expectation was difflib's own guess and this layer gives the
right rewrite instead (`device_role` → `role`, `tenant__empty` → `tenant_id: 'null'`,
`id__in` → list form); `__n` suggested for an `__in`-family key: 0.

## Step 5 — GraphQL validated against the introspected schema

`execute_graphql` now parses the document, runs the read-only / depth / alias-cap guards,
then `graphql.validate(schema, document, rules=specified_rules + [NoNullIdFilterRule])` on
the schema `discover_schema` already introspects and caches (refactored into `_introspect`
/ `_ensure_schema`). graphql-core's messages are the ones NetBox returns, with "Did you
mean" on names; two shapes get the old hints appended (`limit:` → pagination; ID list → one
bare id / `in_list` / parent / aliases). `NoNullIdFilterRule` rejects `null` on any ID-typed
input field at any depth. If introspection is unavailable the hand-written grammar rules
run as before.
**Gate (offline, MockTransport serving a NetBox-shaped introspection):** 12 failure shapes
rejected before HTTP, including the field-name errors the hand rules could never see
(`Cannot query field 'virtualmachine_count'`, `'tenant_name' is not defined by type
'DeviceFilter'`); 4 valid documents pass; alias cap still enforced; forbidden transport
falls back to the hand rules. 63 tests in the file.

## Step 7 — staleness

The index is stamped with the NetBox version; `NetBoxToolWrapper.get_tools` compares it
with `/api/status/` once per agent start and logs a warning naming the rebuild script on a
mismatch (`index_version_warning`, unit-tested). The GraphQL schema cache is per process,
refreshed by an agent restart. Upstream reports (the `None` drop, `action` docstring,
search defaults) are drafted but **not filed**.

## Not done

Step 6, the full v5 run. The replay guarantees the catches; what it cannot measure is
whether the model recovers in one turn from the new messages. The session ladder was run
as a regression check (see below).

## Regression gate: the session ladder (2026-10-20 11:43–12:07)

`docs/traces/2026-10-20_netbox-session_schema-validation.{md,json}`, same 11 questions and
order as every previous ladder. Seconds / tool calls / score:

| turn | 2026-10-06 | 2026-10-18 | 2026-10-19 | **2026-10-20** |
|---|---|---|---|---|
| 1 devices at HVL-SEA-DC1 | 132 / 2 / 1.0 | 73 / 2 / 1.0 | 74 / 2 / 1.0 | **33** / 2 / 1.0 |
| 2 racks | 34 / 1 / 1.0 | 24 / 1 / 1.0 | 25 / 1 / 1.0 | 23 / 1 / 1.0 |
| 3 rack with most devices | 87 / 1 / 1.0 | 55 / 4 / 1.0 | 37 / 1 / 1.0 | 35 / 1 / 1.0 |
| 4 outlets per PDU | 131 / 7 / 0.0 | 240 / 7 / 1.0 | 221 / 4 / 1.0 | **149 / 2** / 1.0 |
| 5 outlets in use | 177 / 1 / 0.5 | 171 / 2 / 1.0 | 168 / 1 / 1.0 | **55** / 1 / 1.0 |
| 6 PDUs with any outlet in use | 27 / 0 / 0.5 | 117 / 12 / 0.5 | 22 / 0 / 1.0 | 54 / 1 / 1.0 |
| 7 feeds not active | 72 / 1 / 1.0 | 210 / 3 / 1.0 | 139 / 1 / 1.0 | 120 / 1 / 1.0 |
| 8 PDUs fed by a modelled feed | 76 / 1 / 0.0 | 84 / 1 / 1.0 | 75 / 1 / 1.0 | 110 / 3 / 1.0 |
| 9 hypervisor power supplies | 124 / 1 / 1.0 | 132 / 3 / 1.0 | 99 / 1 / 1.0 | 88 / 1 / 1.0 |
| 10 feeds DC vs branch | 303 / 4 / 1.0 | 212 / 1 / 1.0 | 232 / 4 / 0.5 | 216 / 2 / 1.0 |
| 11 summary | 150 / 0 | 126 / 0 | 156 / 0 | 89 / 0 |
| **total** | 1,312 s / 20 / 7.0 | 1,444 s / 36 / 9.5 | 1,248 s / 16 / 9.5 | **971 s / 15 / 10.0** |
| context at turn 10 · decode | 54k · 12.1 | 77k · 14.0 | 88k · 13.3 | 69k · 14.4 |
| validation errors fired | 0 | 0 | 0 | 0 |

Fastest ladder by 22%, fewest calls, and the first perfect score. No validator rejection
fired, so this ladder does not exercise the schema layers; it shows no false positives on
real traffic and the effect of the null wire fix plus the smaller results (turn 5, the
outlets-in-use question: 55 s against 168–177 s on the three earlier runs, one call). Turn 4
is now the two-call shape the 19 October guidance described. One run, as always; the
schema layers' own evidence is the offline replay above.
