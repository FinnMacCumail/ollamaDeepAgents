# GraphQL introspection-driven validation vs the hand-written pre-check

Scope: whether `graphql.validate(schema, parse(query))` against NetBox 4.3.3's live, introspected
GraphQL schema could replace or strengthen `_validate_filter_grammar` / `_check_filter_object` in
`src/tools/netbox_graphql.py`. All measurements are from the local instance
(`http://localhost:8000/graphql/`, NetBox `4.3.3-Docker-3.3.0`, `plugins: {}` per `/api/status/`),
graphql-core 3.2.11 in the project venv, on 2026-10-20. Prototype scripts and their raw output sit
next to this file: `gql_introspect_probe.py` / `.out` (introspection cost + 25 validation cases, each
also sent live to NetBox for comparison) and `gql_probe2.py` / `.out` (schema facts, multi-error
behaviour, a custom null-ID rule, gzip size). Read-only throughout; nothing in the repo was changed.

Source key (local): PRECHECK = `/home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py`;
FAILDOC = `/home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md`;
PROBE1 = `.../research_notes/OpenAPI schema driven filter validation/gql_introspect_probe.out`;
PROBE2 = `.../gql_probe2.out`; TESTS = `/home/ola/dev/netboxdev/ollamaDeepAgents/tests/test_netbox_graphql.py`.

## Q1. What does the current pre-check do, and does it already hold a reusable schema object?

### Takeaway
The module already fetches a full introspection and builds a `GraphQLSchema` with
`build_client_schema`, cached per endpoint in `_schema_cache`, but only for the
`netbox_graphql_schema` discovery tool; `execute_graphql` never touches it and instead runs six
hand-written AST rules. The cached object is exactly what `graphql.validate` needs, so reuse is a
matter of wiring, not new infrastructure.

### Cited Findings
- `discover_schema()` posts `get_introspection_query(descriptions=False)`, calls
  `build_client_schema(result["data"])` and stores the result in the module-level
  `_schema_cache: dict[str, object]` keyed by endpoint URL; the comment says the schema "is stable
  for the life of the process; a new thread/process rebuilds it lazily on first use" — [PRECHECK lines 62-64, 342-378](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- `execute_graphql()` runs `_validate_read_only(query)` (parse, reject non-`query` operations,
  depth > `GQL_MAX_DEPTH`=12) which ends by calling `_validate_filter_grammar(document)`; the schema
  cache is not consulted on the execute path — [PRECHECK lines 149-183, 291-311](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- The hand-written rules are: `filter:` → "the argument is 'filters' (plural)"; `limit:`/`offset:` at
  field level → "use pagination: {limit, offset}"; any argument not in
  `_LIST_FIELD_ARGS = {"filters","pagination","ordering"}` → "unknown argument"; on any key named `id`
  or `*_id` at any nesting depth: list value, object value, or `null` value are rejected; more than
  `GQL_MAX_ALIASES = 10` aliases rejected. Rules apply only to fields whose name ends in `_list` — [PRECHECK lines 186-271](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- The rules were added because "20 of 31 GraphQL calls failed in the 2026-10-17 run; each failure
  costs a model round trip", and "each rule is verified against NetBox 4.3.3's strawberry schema on
  2026-10-18" — [PRECHECK lines 180-184](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- The test suite already serves a *real* introspection result from an SDL (`build_schema` +
  `graphql_sync(schema, get_introspection_query(...))`) through `httpx.MockTransport`, and clears
  `gql._schema_cache` per test — so a validate-based path is testable offline — [TESTS lines 13-36, 236-252](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tests/test_netbox_graphql.py)

### Inferences
- The hand-written `_LIST_FIELD_ARGS` whitelist includes `ordering`, but on this instance no
  `_list` field has an `ordering` argument (see Q3); the pre-check lets `ordering:` through and NetBox
  then rejects it. This is a concrete instance of hand-written rules drifting from the schema, which
  schema-driven validation cannot do.

### Gaps
- None for this question.

## Q2. Introspection cost: size, time, type/field counts, build time, memory

### Takeaway
A full introspection is 1.15 MB of JSON (38 KB gzipped), returned in ~0.6 s; `build_client_schema`
takes 188 ms cold / 44 ms warm and ~2.4 MB of traced allocations; the resulting schema has 382 types,
234 root query fields (117 `_list`), 2,595 output fields, 2,769 input fields, 1,039 field arguments.
Validation then costs 1-11 ms per document. All of this is well under one model round trip.

### Cited Findings
- `get_introspection_query(descriptions=False)` (1,406-char query): HTTP 200, **1,146,768 bytes**,
  **586 ms**; with descriptions: 1,356,605 bytes, 572 ms — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out)
- `json.dumps(..., separators=(',',':'))` of the no-description result: 1,037,276 bytes; gzip of
  that: **37,617 bytes**; `json.loads` of it: 16 ms — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out); [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out)
- Type census: 382 types = 130 OBJECT, 142 INPUT_OBJECT, 83 ENUM, 16 UNION, 11 SCALAR; 2,595
  object/interface fields; 2,769 input fields; 1,039 field args; 234 root query fields; SDL from
  `print_schema` is 200,068 chars — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out)
- `build_client_schema`: **188 ms** first build (tracemalloc current = peak = 2.4 MB), **44 ms** on a
  second build in the same process; `type_map` has 382 entries — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out)
- Per-document `parse`+`validate` on the 25 test cases: 0.96-10.65 ms each (first calls include
  cold-path overhead); `validate()` on the valid baseline document, 200 iterations: **1.43 ms** each — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out)
- For comparison, live round trips for the small test queries were 33-133 ms each — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out)
- Root `_list` fields: 115 of 117 take exactly `(filters, pagination)`; 2 (`notification_list`,
  `subscription_list`) take only `pagination`; `device_list` args are
  `{filters: DeviceFilter, pagination: OffsetPaginationInput}`;
  `OffsetPaginationInput = {offset: Int!, limit: Int}` — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out)

### Inferences
- Cold start for a validate-before-execute path is ~0.8 s (fetch + build) once per process; the
  module's existing lazy per-endpoint cache already amortises this, and a disk cache of the 38 KB
  gzipped introspection would cut cold start to ~0.2 s (16 ms load + 188 ms build) if desired.
- Memory (2.4 MB traced for the schema object; ~1 MB for the raw JSON if retained) is negligible.

### Gaps
- Memory was measured with `tracemalloc` on the build call only (Python-level allocations); RSS
  growth was not measured. Timings are single runs on a warm local Docker instance, not benchmarks.

## Q3. Which recorded failure categories does standard `graphql.validate` catch, with what messages?

### Takeaway
Every grammar and name category in the recorded failures is caught locally, and the local message is
byte-identical to what NetBox returns (NetBox's Strawberry layer runs the same graphql-core rules).
Not caught: the alias cap, `tenant_id: null`, and `mutation`/`subscription` operations (the schema
has no mutation type, and graphql-core only reports that at execution time).

### Cited Findings
Verbatim results (graphql-core message; NetBox live message was identical in every case unless noted) — all from [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out):

| Recorded category (FAILDOC) | Query shape | graphql-core `validate` | NetBox live |
|---|---|---|---|
| "Unknown argument 'filter'" | `device_list(filter: {site_id: 6})` | `Unknown argument 'filter' on field 'Query.device_list'. Did you mean 'filters'?` | identical |
| "Unknown argument 'limit'" | `device_list(limit: 10)` | `Unknown argument 'limit' on field 'Query.device_list'.` | identical |
| unknown argument (bare filter key) | `device_list(site_id: 6)` | `Unknown argument 'site_id' on field 'Query.device_list'.` | identical |
| "ID cannot represent..." (list) | `filters: {id: [146, 147]}` | `ID cannot represent a non-string and non-integer value: [146, 147]` | identical |
| same (lookup object on ID) | `filters: {id: {exact: 6}}` | `ID cannot represent a non-string and non-integer value: {exact: 6}` | identical |
| same, nested relation | `filters: {tenant: {id: {in_list: [1,2]}}}` | `ID cannot represent a non-string and non-integer value: {in_list: [1, 2]}` | identical |
| "Field 'icontains' is not defined by type 'StrFilterLookup'" | `filters: {name: {icontains: "rtr"}}` | `Field 'icontains' is not defined by type 'StrFilterLookup'. Did you mean 'contains' or 'i_contains'?` | identical |
| "Cannot query field 'virtualmachine_count'" | `tenant_list { id name virtualmachine_count }` | `Cannot query field 'virtualmachine_count' on type 'TenantType'. Did you mean 'virtual_machines'?` | identical |
| "Field X is not defined by type YFilter" | `filters: {tenant_name: {exact: "x"}}` | `Field 'tenant_name' is not defined by type 'DeviceFilter'. Did you mean 'tenant_id', 'tenant', or 'tenant_group'?` | identical |
| wrong root field | `{ devices { id } }` | `Cannot query field 'devices' on type 'Query'. Did you mean 'device' or 'service'?` | identical |
| typo root field | `{ devices_list { id } }` | `Cannot query field 'devices_list' on type 'Query'. Did you mean 'device_list', 'service_list', 'device_bay_list', 'device_bay', or 'device_role'?` | identical |
| string filter without lookup object | `filters: {name: "rtr01"}` | `Expected value of type 'StrFilterLookup', found "rtr01".` | identical |
| wrong lookup key | `filters: {name: {equals: "x"}}` | `Field 'equals' is not defined by type 'StrFilterLookup'.` | identical |
| pagination shape | `pagination: {first: 10}` | `Field 'first' is not defined by type 'OffsetPaginationInput'. Did you mean 'limit'?` | identical |
| `ordering:` (allowed by hand-written whitelist) | `device_list(ordering: {name: ASC})` | `Unknown argument 'ordering' on field 'Query.device_list'.` | identical |
| variable type mismatch | `query($id: Int!) {... filters: {id: $id}}` | `Variable '$id' of type 'Int!' used in position expecting type 'ID'.` | identical |
| scalar with sub-selection | `name { value }` | `Field 'name' must not have a selection since type 'String' has no subfields.` | identical |
| object without sub-selection | `{ id site }` | `Field 'site' of type 'SiteType!' must have a selection of subfields. Did you mean 'site { ... }'?` | identical |
| **"12 aliases found. Allowed: 10"** | 12 aliased `device_list` | **OK (no errors)** | `12 aliases found. Allowed: 10` |
| **`tenant_id: null`** | `filters: {tenant_id: null}` | **OK (no errors)** | no errors; returns all 141 devices |
| **mutation** | `mutation { x }` | **OK (no errors)** | `Schema is not configured to execute mutation operation.` (HTTP 200, `data: null`) |
| `id: "6"` (string ID) | `filters: {id: "6"}` | OK | OK, 1 device |
| valid baselines (3) | `site_id: 6` + pagination; `name: {i_contains: ...}`; `tenant: {id: 14}` | OK | OK (4 / 20 / 68 devices) |

- `schema.mutation_type` and `schema.subscription_type` are both `None` on the introspected schema;
  `validate` returns `[]` for both `mutation { x }` and `subscription { x }` — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out)
- A document with five distinct mistakes yields the same five messages from graphql-core and from
  NetBox, in the same order (`validate` reports up to `max_errors`, default 100) — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out); max_errors default per `validate` docstring: "by default `max_errors` set to 100 errors" (graphql-core 3.2.11 `inspect.getdoc(validate)`, captured in the Q3 probe run)
- graphql-core's default `specified_rules` list has 27 rules including `KnownArgumentNamesRule`,
  `FieldsOnCorrectTypeRule`, `ValuesOfCorrectTypeRule`, `ScalarLeafsRule`,
  `VariablesInAllowedPositionRule`, `ProvidedRequiredArgumentsRule` — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out)
- The alias cap is a NetBox runtime setting: `GRAPHQL_MAX_ALIASES`, default `10`, "The maximum
  number of queries that a GraphQL API request may contain"; `GRAPHQL_MAX_QUERY_DEPTH` default `None`
  (no limit) — [NetBox docs: GraphQL configuration](https://netboxlabs.com/docs/netbox/configuration/graphql-api/)
- Why `tenant_id: null` passes: `DeviceFilter.tenant_id` is a nullable `ID`; across the schema there
  are 325 ID-typed input fields of which 324 are nullable, and **zero** input fields of list-of-ID
  type — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out)
- FAILDOC's 18 Oct run recorded 16 NetBox rejections, of which 0 were grammar, **14 were field/type
  names** ("Cannot query field", "not defined by type") and 2 were lookup objects on nested relation
  ids; plus 7 caught by the pre-check (6x `limit:`, 1x id list) — [FAILDOC lines 160-166](file:///home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md)

### Inferences
- All 14 residual name failures and both nested-lookup failures from the 18 Oct run are in
  categories that `validate` catches locally with a "Did you mean" hint; the hand-written rules
  cannot address them at all without the schema.
- Because the output is identical to the server's, local validation is literally the server's
  validation step moved client-side; the only differences are the three runtime/semantic checks.
- `_validate_read_only` must stay: `validate` does not reject mutations against a schema with no
  mutation type (that check lives in `execute`).

### Gaps
- I reconstructed representative queries per category rather than replaying the exact recorded
  failing documents (the trace docs record message categories, not full query text).

## Q4. Comparison with `_validate_filter_grammar`: which hand-written rules remain necessary?

### Takeaway
Of the hand-written rules, only three survive as necessary: the alias cap (NetBox runtime), the
`*_id: null` semantic trap (needs a custom schema-aware rule, prototyped in ~12 lines), and the
read-only/depth guard. Everything else is subsumed, and the hand-written versions are both narrower
(only `_list` fields, only `id`/`*_id` keys) and already drifting (`ordering`).

### Cited Findings
- Hand-written rules fire only for fields named `*_list` and only inspect keys named `id`/`*_id`; 53
  input fields named `*_id` are **not** `ID` scalars (e.g. `TenantFilter.group_id: TreeNodeFilter`,
  `ObjectChangeFilter.request_id: StrFilterLookup`, `L2VPNTerminationFilter.assigned_object_id:
  IntegerLookup`) — on these the hand-written "takes no lookup object" rule would reject *valid*
  lookup objects — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out); rule at [PRECHECK lines 197-232](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- A custom rule subclassing `graphql.validation.ValidationRule` with `enter_object_field` using
  `self.context.get_input_type()` flags a `null` literal on any `ID`-typed input field at any depth
  (`tenant_id: null` and `tenant: {id: null}` both flagged; `name: {is_null: true}` passes); passed as
  `validate(schema, doc, rules=[*specified_rules, NoNullIdFilterRule])` — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out); API: "you can also use a subset or create custom rules" extending `ValidationRule` — [graphql-core docs](https://graphql-core-3.readthedocs.io/en/latest/usage/validator.html)
- `validate` signature: `validate(schema, document_ast, rules=None, max_errors=None, type_info=None)
  -> List[GraphQLError]` (graphql-core 3.2.11 `inspect.signature`, captured in the Q3 probe run)
- The alias limit is enforced by NetBox at runtime (`GRAPHQL_MAX_ALIASES`, default 10) and is not
  part of the schema — [NetBox docs](https://netboxlabs.com/docs/netbox/configuration/graphql-api/); hand-written rule at [PRECHECK lines 263-268](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- Depth: NetBox's own `GRAPHQL_MAX_QUERY_DEPTH` defaults to no limit, so the local `GQL_MAX_DEPTH=12`
  is a client-side cost guard, not a schema fact — [NetBox docs](https://netboxlabs.com/docs/netbox/configuration/graphql-api/); [PRECHECK line 60](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)

Rule-by-rule mapping:

| Hand-written rule | `validate` covers? | Remains needed? |
|---|---|---|
| `filter:` → `filters` | yes, with "Did you mean 'filters'?" | no |
| `limit:`/`offset:` top-level | yes ("Unknown argument 'limit'"), no hint | no (but see Q6 on hints) |
| unknown argument on `_list` | yes, on every field not just `_list` | no |
| `id`/`*_id` list value | yes, generically via `ValuesOfCorrectTypeRule` | no |
| `id`/`*_id` object value | yes, and without false positives on `TreeNodeFilter`/`IntegerLookup` `*_id` keys | no |
| `id`/`*_id` null value | **no** | yes - as a custom `ValidationRule` (prototype works) |
| > 10 aliases | **no** | yes - keep the alias counter |
| non-`query` operation | **no** | yes - keep `_validate_read_only` |
| depth > 12 | no (schema has no depth) | yes - keep |

### Inferences
- Replacing the five grammar rules with `validate` removes the maintenance surface that already
  produced one drift (`ordering`) and one class of false positive (`*_id` keys that are lookup
  objects), while extending coverage to the categories that are now 14/16 of residual failures.

### Gaps
- Whether `TreeNodeFilter`-typed `*_id` keys (e.g. `TenantFilter.group_id`) are actually used by the
  model in practice was not checked in the traces; the false-positive risk is schema-proven but its
  frequency is unknown.

## Q5. Caching strategy and staleness

### Takeaway
The existing per-endpoint, per-process cache is adequate for cost; the real risk is staleness after
a NetBox upgrade or plugin install (both change the schema), which would turn local validation into
false rejections. Keying the cache on `netbox-version` + plugin list from `/api/status/`, and
refreshing once when a locally-valid query is rejected by NetBox (or vice versa), covers this cheaply.

### Cited Findings
- Cache is `_schema_cache[endpoint]`, filled lazily, never expired; comment: "NetBox schema is stable
  for the life of the process" — [PRECHECK lines 62-64, 350-378](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- `/api/status/` returns `netbox-version: "4.3.3"`, `netbox-full-version: "4.3.3-Docker-3.3.0"`,
  `plugins: {}` and the installed-apps map in a single small GET (observed in the Q1 connectivity
  check against the live instance, 2026-10-20)
- Refresh cost is bounded: 586 ms fetch + 188 ms build; disk-persisted gzip is 37,617 bytes and
  loads in 16 ms + 188 ms build — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out); [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out)
- `GRAPHQL_ENABLED` (default True) can disable the endpoint entirely; `discover_schema` already
  handles "introspection is disabled or returned no schema" by returning a `TOOL_API_ERROR` — [NetBox docs](https://netboxlabs.com/docs/netbox/configuration/graphql-api/); [PRECHECK lines 368-371](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)

### Inferences
- Fail-open is the safe default: if introspection is unavailable, skip local validation and send the
  query (NetBox validates anyway); never block execution on a missing schema.
- Self-healing invalidation: if NetBox returns a validation-class error (`Cannot query field`,
  `Unknown argument`, `not defined by type`) for a document that passed local validation, the cache
  is stale - drop it and rebuild on next call. The converse (local rejects, server would accept) is
  invisible unless the cache is version-keyed, hence the `/api/status/` key.

### Gaps
- No measurement of how NetBox plugins change the introspection size or whether a plugin install
  changes `/api/status/` output atomically with the GraphQL schema (this instance has no plugins).

## Q6. Error-message quality: can the model self-correct in one step?

### Takeaway
graphql-core's messages are the same ones the model already receives from NetBox and self-corrects
on today, with "Did you mean" suggestions on field, argument and input-field names; they are weaker
than the hand-written hints for the two value-shape cases (`limit:` and ID lists), where the
hand-written text names the correct alternative. A thin enrichment layer (pattern-match the
graphql-core message, append the existing hint) keeps the best of both.

### Cited Findings
- Suggestions appear for: unknown argument with a near match (`'filter'` → `'filters'`), unknown
  input field (`'icontains'` → `'contains' or 'i_contains'`; `'tenant_name'` → `'tenant_id',
  'tenant', or 'tenant_group'`; `'first'` → `'limit'`), unknown output field
  (`'virtualmachine_count'` → `'virtual_machines'`), wrong root (`'devices_list'` → five
  candidates), missing sub-selection (`Did you mean 'site { ... }'?`) — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out)
- No suggestion for: `Unknown argument 'limit'` (no lexically-close argument), `Unknown argument
  'site_id'`, `Unknown argument 'ordering'`, `ID cannot represent a non-string and non-integer value:
  [146, 147]`, `Field 'equals' is not defined by type 'StrFilterLookup'.` — [PROBE1](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_introspect_probe.out)
- The hand-written messages for those cases carry the fix: "there is no 'limit' argument; use
  pagination: {limit: <n>, offset: <n>}"; "'id' takes ONE id, not a list ... For several objects use
  a string lookup (name: {in_list: [...]}), a parent filter (site_id, tenant_id), or up to 10 aliased
  queries with one id each"; "filters go inside 'filters: {...}' (e.g. filters: {site_id: ...})" — [PRECHECK lines 207-213, 251-262](file:///home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_graphql.py)
- FAILDOC attributes six of twenty 17-Oct failures to the model following the skill's wrong claim
  that `{id: [6, 7, 8]}` is valid, i.e. the ID-list mistake is guidance-driven and recurred until the
  guidance and the error hint were fixed — [FAILDOC lines 63-64](file:///home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md)
- All errors in a document are reported together (5 of 5 in the multi-error test), so one local pass
  can surface every mistake at once rather than one per round trip — [PROBE2](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out)

### Inferences
- Since the 18 Oct run shows the model recovering from these exact server messages (16 rejections,
  53 queries, 30 accepted), the message quality is at least sufficient for the recovery that already
  happens; the gain from local validation is the saved HTTP round trip and the multi-error report,
  not better wording. Where wording matters (`limit:`, ID list), prepend the existing hint via a
  regex on the graphql-core message.
- `GraphQLError` objects also carry `locations` (line/column) and `path`; the current
  `TOOL_VALIDATION_ERROR` string could include them, which NetBox's response already does.

### Gaps
- No controlled measurement of one-step self-correction rate per message type exists in the traces;
  the FAILDOC counts are per-run aggregates, not per-message outcomes.

## Q7. REST parallel: could the OpenAPI schema play the same role?

### Takeaway
The analogue exists (`/api/schema/` lists every filter parameter per endpoint) but it is an order of
magnitude heavier (9.3 MB, 5 s to generate) and, unlike GraphQL, has no equivalent of
`graphql.validate` - a parameter-name whitelist would have to be hand-assembled from it. Noted
briefly; the REST researcher covers it.

### Cited Findings
- `GET /api/schema/?format=json`: HTTP 200, **9,313,713 bytes**, **5.004 s**; OpenAPI 3.0.3; 292
  paths; 740 component schemas; `/api/dcim/devices/` GET declares 292 query parameters, including
  `tenant_id`, `tenant_id__n`, `tenant_group_id`, `tenant_group_id__n` but no `tenant__isnull` /
  `tenant_id__empty` (the forms FAILDOC records as silently ignored) — [PROBE2 tail](file:///home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/research_notes/OpenAPI%20schema%20driven%20filter%20validation/gql_probe2.out); [FAILDOC lines 34-38](file:///home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md)
- NetBox's REST and GraphQL APIs share the same token authentication — [NetBox docs: GraphQL API](https://netboxlabs.com/docs/netbox/integrations/graphql-api/)

### Inferences
- The OpenAPI parameter list would catch the "silently ignored" REST filter names (`tenant__isnull`)
  that the REST side currently handles with hand-written suffix rules - the same class of win as
  `validate` gives GraphQL - but it needs a one-off build of a `{endpoint: set(param names)}` index
  and a disk cache given the 5 s generation time.

### Gaps
- Whether drf-spectacular's parameter list is complete for every NetBox filterset (custom-field
  filters, `q`, nested lookups) was not verified here.
