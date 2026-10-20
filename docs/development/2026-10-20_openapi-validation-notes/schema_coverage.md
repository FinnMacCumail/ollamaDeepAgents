# Is NetBox's OpenAPI schema an accurate authority for REST filter keys, lookups and enum values? (NetBox 4.3.3, local instance, 2026-10-20)

Method. Python over `/home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/netbox-openapi.json` (fetched today from `http://localhost:8000/api/schema/?format=json`, 9,313,713 bytes, `openapi: 3.0.3`, `info.version: "4.3.3-Docker-3.3.0 (4.3)"`), read-only `curl` GETs against `http://localhost:8000/api/` with the token from `.env` (all counts below are the `count` field of the response; a filter is "silently ignored" when its count equals the unfiltered count), and NetBox/drf-spectacular source read from the running container `netbox-docker-netbox-1` (`netboxcommunity/netbox:v4.3-3.3.0`). `/api/status/` reports `netbox-version 4.3.3`, `drf_spectacular 0.28.0`, `django_filters 25.1`, `rest_framework 3.16.0`, `django 5.2.3`. Baselines used: `dcim/devices/` = **141**, `ipam/ip-addresses/` = **616**, `core/object-changes/` = **3,543**, `tenancy/tenants/` = **12**, `dcim/sites/` = **30**.

## KQ1. For each hand-found form: is it in the schema, what does the schema say, what does live NetBox do, would a schema key check catch it?

### Takeaway
A pure key check against `paths[...].get.parameters[].name` catches **every silently-ignored key form** found by hand (`device_role_id`, `devicerole_id`, `device_role`, `<field>__in`, `tenant__empty`, `tenant__isnull`, `tenant_id__empty`, `name__contains`, `within`/`prefix`/`without`/`contains` on ip-addresses, `tenant__ic`, `devicetype_id`, `time__gte`, `action__n`) plus a form the project's own validator currently whitelists as valid (`__regex`/`__iregex`, which 4.3.3 silently ignores). It does **not** catch the semantic traps where the key exists but the value or meaning is wrong: `tenant__n=null` (complement), `vrf=<name>` (key exists; description says RD), `site=DM-Scranton` (key exists; description says slug), `action=created` (key exists; needs enum check), `created__empty=true` (key exists; schema types it as date-time and NetBox answers 400), and boolean values like `has_primary_ip=1` (ignored).

### Cited Findings (table: form | in schema? | schema says | live NetBox does | schema key check catches?)
All schema facts from `netbox-openapi.json` (`/api/dcim/devices/` has 292 `get.parameters`; `/api/ipam/ip-addresses/` 131; `/api/core/object-changes/` 61). All live facts from `http://localhost:8000/api/...` today.

| form (on `dcim/devices/` unless noted) | in schema? | schema says (verbatim) | live NetBox | key check catches? |
|---|---|---|---|---|
| `device_role_id=1` | **no** | — | 200, **141** (ignored) | **yes** |
| `devicerole_id=1` | **no** | — | 200, **141** (ignored) | **yes** |
| `device_role=pdu` | **no** | — | 200, **141** (ignored) | **yes** |
| `role_id=1` | yes | `{"type":"array","items":{"type":"string"}}` (no description; typed **string**, not integer) | 200, **20**; `role_id=abc` → 400 `"abc" is not a valid value`; `role_id=999999` → 400 `Select a valid choice` | n/a (valid); type is wrong in schema |
| `role=pdu` | yes | `array<string>`, no description | 200, **25**; `role=bogus` → 400 | n/a |
| `tenant_id__in=14` | **no** (0 params schema-wide end in `__in`) | — | 200, **141** (ignored); `tenant_id=14` → **68** | **yes** |
| `id__in=1,2,3` | **no** | — | 200, **141** (ignored) | **yes** |
| `tenant__empty=true` | **no** | — | 200, **141** (ignored) | **yes** |
| `tenant__isnull=true` | **no** | — | 200, **141** (ignored) | **yes** |
| `tenant_id__empty=true` | **no** (no `*_id__empty` on any real FK; see KQ2) | — | 200, **141** (ignored) | **yes** |
| `tenant_id=null` | yes | `{"type":"array","items":{"type":"integer","nullable":true}}`, description `"Tenant (ID)"` | 200, **15** (correct) | n/a; but see KQ3: null is a string sentinel the schema cannot express |
| `tenant=null` (slug) | yes (key) | `array<string>` **not** marked nullable, description `"Tenant (slug)"` | 200, **15** (works) | n/a; schema under-reports nullability |
| `tenant__n=null` | yes | `array<string>`, description `"Tenant (slug)"` | 200, **126** (the complement: devices WITH a tenant) | **no** — key is valid; semantics not expressed |
| `tenant_id__n=null` | yes | `array<integer, nullable>`, `"Tenant (ID)"` | 200, **126** (complement) | **no** |
| `has_primary_ip=false` | yes | `{"type":"boolean"}`, description `"Has a primary IP"` | `false` → **97**, `true` → **44**, `False` → 97; **`1` → 141 and `no` → 141 (ignored)** | key: n/a; a value-type check (JSON boolean only) would catch `1`/`no` |
| `name__contains=pdu` | **no** | — | 200, **141** (ignored) | **yes** |
| `name__icontains=pdu` | **no** | — | 200, **141** (ignored) | **yes** |
| `name__ic=pdu` | yes | `array<string>` | 200, **25** | n/a |
| `name__regex=^dmi01-akron` / `name__iregex=...` / `serial__regex=.` | **no** (0 params schema-wide contain a `regex` suffix; the only `regex` strings are the `validation_regex` field of custom-fields) | — | 200, **141** each (ignored); `name__isw=dmi01-akron` → **3** | **yes** — and the project validator's `VALID_SUFFIXES` lists `regex`, `iregex` as valid (`src/tools/netbox_tools.py:15-33`) |
| `site=DM-Scranton` | yes (key) | `array<string>`, description `"Site name (slug)"` | 400 `Select a valid choice. DM-Scranton is not one of the available choices.`; `site=dm-scranton` → **4** | **no** for the key; the description says slug, a value check cannot know the slug list |
| `tenant__ic=hvl`, `role__ic=pd` | **no** | — | 200, **141** (ignored) | **yes** |
| `devicetype_id=1` | **no** | — | 200, **141** (ignored); `device_type_id=1` → **0** (honoured) | **yes** |
| `tenant_id__gt=1` | **no** | — | 200, **141** (ignored) | **yes** |
| `bogus_key=1`, `name__bogus=1`, `cf_bogus=1` | **no** | — | 200, **141** (ignored) | **yes** |
| `created__empty=true` | **yes** | `{"type":"array","items":{"type":"string","format":"date-time"}}` | **400** `Enter a valid date/time.` (also for `=false`, and `last_updated__empty`) | **no** — schema lists it; a type check would demand a date-time, which is nonsense |
| `id__empty=true`, `status__empty=true`, `serial__empty=true`, `name__empty=true` | yes | `{"type":"boolean"}` | 0 / 0 / **72** / **22** (honoured); `serial__empty=maybe` → 141 (ignored) | n/a |
| `ordering=bogusfield` | yes (key) | `{"type":"string"}`, `"Which field to use when ordering the results."` | 200, 141, silently unsorted | no |
| **ip-addresses** `parent=10.0.0.0/8` | yes | `{"type":"array","items":{"type":"string"}}`, no description | **436**; `parent=10.0.0.0/8&parent=192.168.0.0/16` → **466** (OR) | n/a |
| ip-addresses `within=10.0.0.0/8` | **no** | — (on `/api/ipam/prefixes/` `within` is `{"type":"string"}`, `"Within prefix"`) | 200, **616** (ignored) | **yes** |
| ip-addresses `within_include=`, `contains=`, `prefix=` | **no** | — | 200, **616** each (ignored) | **yes** |
| ip-addresses `without=10.0.0.0/8` | **no** | — | 200, **616** today (ignored). *Discrepancy*: the 2026-10-18 doc records `without=...` as 400; today's call with this value is 200/616 | **yes** |
| ip-addresses `vrf=hvl-guest` | yes (key) | `{"type":"array","items":{"type":"string","nullable":true,"title":"Route distinguisher"}}`, description `"VRF (RD)"` | 400 `Select a valid choice`; `vrf=65000:100` → **30**; `vrf=null` → **30** | **no** for the key; the description/title say RD |
| ip-addresses `vrf_id=null` | yes | `array<integer, nullable>`, `"VRF"` | **30** | n/a |
| **object-changes** `action=created` | yes (key) | `{"type":"string","x-spec-enum-id":"544f9b3b28b7ce6a","enum":["create","delete","update"]}`, description `"* \`create\` - Created\n* \`update\` - Updated\n* \`delete\` - Deleted"` | 400 `Select a valid choice. created is not one of the available choices.`; `action=create` → **3,158** | **no** for the key; **yes with an enum value check** (inline enum present) |
| object-changes `action__n=create` | **no** | — | 200, **3,543** (ignored) | **yes** |
| object-changes `time__gte=...` | **no** (schema has `time_after`, `time_before`, both `string, format date-time`) | — | 200, **3,543** (ignored) | **yes** |
| `extras/object-changes/` path | **absent** (schema has `/api/core/object-changes/`) | — | **404** | yes (path check) |

Sources: schema file `/home/ola/dev/netboxdev/ollamaDeepAgents/tmp/research/netbox-openapi.json`; live `http://localhost:8000/api/dcim/devices/`, `/api/ipam/ip-addresses/`, `/api/ipam/prefixes/`, `/api/core/object-changes/`; hand-found forms from [2026-10-18_filter-naming-after-in.md](/home/ola/dev/netboxdev/ollamaDeepAgents/docs/development/2026-10-18_filter-naming-after-in.md) and the validator constants in [netbox_tools.py](/home/ola/dev/netboxdev/ollamaDeepAgents/src/tools/netbox_tools.py) (`VALID_SUFFIXES` lines 28-33, `RELATION_FIELDS` 44-53, `_IPADDRESS_PREFIX_ONLY_KEYS` 64, `CHANGELOG_ACTION_FIX` 71).

- Why `__regex` is ignored on 4.3.3: `FILTER_CHAR_BASED_LOOKUP_MAP` in the container's `/opt/netbox/netbox/utilities/constants.py:5-16` is exactly `n, ic, nic, iew, niew, isw, nisw, ie, nie, empty`; no `regex`. The feature "Add `regex` and `iregex` lookups to filters for string fields" is [netbox issue #19903](https://github.com/netbox-community/netbox/issues/19903), milestone **v4.3.5**, closed 24 Jul 2025 — i.e. two patch releases after this instance.
- Why `created__empty` is listed but returns 400: `FILTER_NUMERIC_BASED_LOOKUP_MAP` maps `empty='isnull'` (`utilities/constants.py:24`); for *declared* filters, `BaseFilterSet.get_additional_lookups` only swaps in `django_filters.BooleanFilter` when `lookup_expr == 'empty'` (`/opt/netbox/netbox/netbox/filtersets.py:189-192`), so `created` (declared as `MultiValueDateTimeFilter` in `ChangeLoggedModelFilterSet`, `filtersets.py:253`) keeps a date-time form field with `lookup_expr='isnull'`. Meta-declared fields (`id`, `serial`, `position`) go through `filter_for_lookup`, which returns `BooleanFilter` for `empty` (`filtersets.py:241-246`), hence `id__empty` is `boolean` in the schema and works. The schema is faithful to the implementation, including its bug.

### Inferences
- A schema-driven *key* validator would have caught 15 of the 20 silently-ignored forms in the table and all of the hand-found ones except the five "key exists, value/semantics wrong" cases. It would also have flagged `__regex`/`__iregex`, which the project currently treats as valid and which only become real in v4.3.5.
- The five misses need per-form rules or value checks: `__n=null` complement (semantic), `vrf` RD (description-driven hint only), slug values (description says slug; the list of slugs is data), `action` values (inline enum, checkable), boolean spellings (type check on JSON booleans).

### Gaps
- The 2026-10-18 doc says `without=...` on ip-addresses returned 400; today's `without=10.0.0.0/8` returns 200/616. The doc does not record the value used, so the discrepancy cannot be resolved from the evidence.
- `facility_id__empty=true` on `dcim/sites/` returns 30 of 30; cannot tell whether that is "all sites have an empty facility ID" or an ignored filter without writing data.

## KQ2. Which lookup suffixes does the schema list per field type? Is `__in` listed? Is `__empty` listed for FK fields?

### Takeaway
The schema reproduces NetBox's four lookup maps exactly: string fields get `n, ic, nic, ie, nie, isw, nisw, iew, niew, empty`; numeric/date-time fields get `n, lt, lte, gt, gte, empty`; FK (`ModelMultipleChoiceFilter`, tree-node, tag) filters get only `n`; booleans and method filters get nothing. `__in` appears **nowhere** (0 of 11,537 parameters) and `__empty` is never generated for a real FK filter.

### Cited Findings
- Suffix census over all 151 list-GET endpoints (11,537 parameters): `n` 2,039; `empty` 899; `gte` 497; `lte` 497; `gt` 493; `lt` 493; `ic`/`ie`/`iew`/`isw`/`nic`/`nie`/`niew`/`nisw` 428 each; `after` 4 and `before` 4 (only on `/api/core/jobs/`: `completed__after`, `created__before`, ...); **0** `__in`; **0** `__isnull`/`__icontains`; **0** `regex`/`iregex`; **0** parameter names with two or more `__` (multi-hop) — schema file.
- Per-type examples on `/api/dcim/devices/` (verbatim names): `name` → `name__empty, name__ic, name__ie, name__iew, name__isw, name__n, name__nic, name__nie, name__niew, name__nisw`; `id` → `id__empty, id__gt, id__gte, id__lt, id__lte, id__n`; `created` → `created__empty, created__gt, created__gte, created__lt, created__lte, created__n`; `tenant_id` → `tenant_id__n` only; `tenant` → `tenant__n` only; `tag` → `tag__n`; `has_primary_ip`, `console_ports`, `is_full_depth` (booleans) → no suffixes; `q`, `airflow`, `face`, `created_by_request` → no suffixes; `mac_address` → the char set **without** `empty` — schema file.
- `status` (a `MultipleChoiceFilter`) gets the full char set: `status__empty, status__ic, status__ie, status__iew, status__isw, status__n, status__nic, status__nie, status__niew, status__nisw` — schema file.
- The 32 `*_id__empty` parameters schema-wide are 18 distinct names, all char fields or generic-FK integer columns, not real FK filters: `action_object_id__empty, assigned_object_id__empty, changed_object_id__empty, component_id__empty, facility_id__empty, group_id__empty, interface_id__empty, member_id__empty, object_id__empty, object_type_id__empty, parent_object_id__empty, part_id__empty, related_object_id__empty, scope_id__empty, service_id__empty, termination_id__empty, tunnel_id__empty, xconnect_id__empty` — schema file.
- Source of the maps: `/opt/netbox/netbox/utilities/constants.py:5-33` (`FILTER_CHAR_BASED_LOOKUP_MAP`, `FILTER_NUMERIC_BASED_LOOKUP_MAP` with `empty='isnull'`, `FILTER_NEGATION_LOOKUP_MAP = dict(n='exact')`, `FILTER_TREENODE_NEGATION_LOOKUP_MAP = dict(n='in')`); selection by filter class in `/opt/netbox/netbox/netbox/filtersets.py:117-151` (`_get_filter_lookup_dict`: Number/MultiValueDate/DateTime/Number/Decimal/Time → numeric map; `TreeNodeMultipleChoiceFilter` → tree-node map; `ModelChoiceFilter`/`ModelMultipleChoiceFilter`/`TagFilter` → negation only; `CharFilter`/`MultipleChoiceFilter`/`MultiValueCharFilter`/`MultiValueMACAddressFilter` → char map; anything else → `None`, no extra lookups). `get_additional_lookups` skips filters with a `method` or a `lookup_expr` outside `exact/iexact/in` (`filtersets.py:162`).
- NetBox's own docs in the container (`/opt/netbox/docs/reference/filtering.md`, "Lookup Expressions", lines 53-105) list the same sets and describe `empty` as "Is empty/null (boolean)"; the public copy is [REST API Filtering](https://netboxlabs.com/docs/netbox/reference/filtering/).
- Live confirmation of the map on 4.3.3: `id__gte=100` → 76, `id__gt=100` → 75, `created__gte=2025-01-01` → 69, `created__lt=2025-01-01` → 72, `position__lt=5` → 26, `position__gt=abc` → 400 `Enter a number.`, `name__nic=pdu` → 116, `name__ie=pdu` → 0 — `http://localhost:8000/api/dcim/devices/`.

### Inferences
- Because the schema is generated from the same `base_filters` the request is parsed with, the *set* of generated lookup names is an exact authority for 4.3.3; the risk is in types and semantics, not in which `__suffix` keys exist.
- The MCP server's whitelist (`server.py:143-165`: includes `in`, `regex`, `iregex`) and the project's (`netbox_tools.py:28-33`: includes `regex`, `iregex`) are both wider than 4.3.3 honours; the schema would narrow them automatically and would widen them again on upgrade to ≥ 4.3.5.

### Gaps
- Whether `empty` on `MultiValueMACAddressFilter` is deliberately omitted (schema shows `mac_address` without `__empty`) was not traced to source.

## KQ3. How does the schema represent multi-value filters and nullable FK filters?

### Takeaway
Multi-value filters are `{"type":"array","items":{...}}` with `"explode": true, "style": "form"`, i.e. repeat the parameter (`role_id=1&role_id=2`); the comma form is a 400. Nullability is expressed only as `items.nullable: true` on 128 bare `*_id` parameters whose model FK is `null=True`, which neither says *how* to send null (the literal string `null`) nor covers the slug variants or several FK ids that accept `null` live.

### Cited Findings
- Multi-value representation: e.g. `asset_tag`: `{"in":"query","name":"asset_tag","schema":{"type":"array","items":{"type":"string"}},"explode":true,"style":"form"}`; single-value filters have a scalar schema (`q`: `{"type":"string"}`, `has_primary_ip`: `{"type":"boolean"}`, prefixes `within`: `{"type":"string"}`) — schema file.
- Live multi-value semantics: `role_id=1&role_id=2` → **24** (OR), `role_id=1,2` → 400 `"1,2" is not a valid value.`; `status=active&status=planned` → **139** = 137 + 2; `tenant=hvl&tenant=null` → **83** = 68 + 15; `tenant_id=null&tenant_id=14` → **83**; ip-addresses `parent=10.0.0.0/8&parent=192.168.0.0/16` → 466; prefixes `within=10.0.0.0/8&within=192.168.0.0/16` → 6 (single-value `CharFilter`: last value wins, not OR; `within=10.0.0.0/8` alone → 106) — live.
- Nullable representation: 128 bare `*_id` params schema-wide carry `items.nullable: true`, 400 do not. On devices the nullable four are `cluster_id, config_template_id, platform_id, tenant_id`; the non-nullable include `location_id, rack_id, site_group_id, tenant_group_id, primary_ip4_id, oob_ip_id, virtual_chassis_id, role_id, site_id` — schema file.
- Live `null` on devices: `tenant_id=null` 15, `location_id=null` **70**, `rack_id=null` **9**, `site_group_id=null` **20**, `tenant_group_id=null` **15**, `platform_id=null` 119, `cluster_id=null` 134, `primary_ip4_id=null` **97**, `virtual_chassis_id=null` **133**, `config_template_id=null` 141, `oob_ip_id=null` 141, `role_id=null` 0, `site_id=null` 0 (200 in every case; never a 400) — live. So at least 6 of the "non-nullable" ids accept and honour `null`.
- Slug variant: `tenant=null` → 15 though `tenant` is `array<string>` without `nullable`; `vrf=null` on ip-addresses → 30 (`vrf` items are marked `nullable: true` there) — live.
- Mechanism: `TreeNodeMultipleChoiceFilter.get_filter_predicate` returns `{field_name}__isnull: True` for `None` (`/opt/netbox/netbox/utilities/filters.py:120-128`); django-filter's `ModelMultipleChoiceFilter` maps the `null` sentinel to `isnull` generally (the project's 2026-10-18 doc records the same counts for `tenant_id=null`/`tenant__n=null`).
- Where nullable comes from in the generator: drf-spectacular resolves `ChoiceFilter`/`MultipleChoiceFilter` schemas from the model field (`_get_schema_from_model_field`, `drf_spectacular/contrib/django_filters.py:132-134, 239-257`), so `nullable` mirrors the model column's `null=True`, not the filter's null handling.
- 109 `*_id` parameters schema-wide are typed `array<string>` (e.g. `role_id, region_id, site_group_id, location_id, tenant_group_id, ancestor_id, group_id`) — the `TreeNodeMultipleChoiceFilter` ones (`dcim/filtersets.py:1043-1055` declares device `role_id`/`role` as `TreeNodeMultipleChoiceFilter(..., lookup_expr='in')`), which fall through to drf-spectacular's "Defaulting to string" branch (`contrib/django_filters.py:132-145`). Live they are integers (`region_id=abc` → 400 `"abc" is not a valid value.`).

### Inferences
- A validator can take "array ⇒ repeat the key" and "scalar ⇒ one value" from the schema reliably. It cannot take "accepts `null`" from `nullable` (under-reported) and cannot take integer-ness from `items.type` for 109 FK-id params (typed string).
- The OpenAPI document has no way to say "the string `null` is a sentinel", so the one working unassigned-relation form (`<rel>_id=null`) stays a project rule.

### Gaps
- Not tested whether every `null`-honouring `*_id` is a `TreeNodeMultipleChoiceFilter` or whether plain `ModelMultipleChoiceFilter` (e.g. `rack_id`) also honours null via django-filter's `NULL_CHOICE_VALUE`; the counts show they do, the exact code path was not traced for each.

## KQ4. Filters NetBox honours that are NOT in the schema (`q`, `fields`, `brief`, `limit`, `offset`, `ordering`, `cf_*`, `tag`)?

### Takeaway
`q`, `limit`, `offset`, `ordering`, `tag`, `tag__n`, `tag_id` **are** in the schema; `fields`, `brief` and every custom-field filter `cf_<name>` (plus its lookups) are **not**, because they are implemented outside the class-level filterset that drf-spectacular reads. The schema also cannot describe NetBox's blanket "unknown keys are ignored" behaviour.

### Cited Findings
- Presence counts over 151 list-GET endpoints: `q` on 121; `limit`+`offset`+`ordering` on 126; `cf_*` on **0**; `fields` on **0**; `brief` on **0** — schema file. Devices has `tag` (`array<string>`), `tag__n`, `tag_id` (`array<integer>`), `tag_id__n`.
- Live: `fields=id,name` → 200 with only those keys; `brief=1` → 200; `cf_cust_id__ic=a` on `tenancy/tenants/` → **2** of 12 (honoured), `cf_cust_id__n=` → 12, `cf_bogus=1` → 12 (ignored); the only custom field on this instance is `cust_id` (type `text`, object type `tenancy.tenant`) per `/api/extras/custom-fields/`; `tag=bogus-tag` → 400 `Select a valid choice`; `q=pdu` → 25; `limit=0` → all **141** results in one page — live.
- Where they live: `fields` is read in `/opt/netbox/netbox/netbox/api/viewsets/__init__.py:80` (`self.request.query_params.get('fields')`), `brief` at line 51 (`request.GET.get('brief')`), `limit` in `netbox/api/pagination.py:45`; custom-field filters are added per instance in `NetBoxModelFilterSet.__init__` (`/opt/netbox/netbox/netbox/filtersets.py:294-308`: `filter_name = f'cf_{custom_field.name}'`), whereas drf-spectacular enumerates `filterset_class.base_filters` (`drf_spectacular/contrib/django_filters.py:58-67`), the class-level dict — consistent with the known limitation that `__init__`-added filters are not in `base_filters` ([django_filters.py on GitHub](https://github.com/tfranzel/drf-spectacular/blob/master/drf_spectacular/contrib/django_filters.py)).
- Unknown keys are dropped, never rejected: `bogus_key=1`, `name__bogus=1`, `cf_bogus=1`, `ordering=bogusfield` all 200/141 — live. Values on choice/FK filters *are* validated: `status=bogus`, `face=bogus`, `manufacturer=bogus`, `model=bogus`, `region=bogus`, `role=bogus`, `tenant_id=999999` → 400 — live.

### Inferences
- A schema-driven validator must whitelist `fields`, `brief` and `cf_*` by rule (or pull `/api/extras/custom-fields/` for the real `cf_` names and apply the char/numeric lookup maps to them by custom-field type).

### Gaps
- `cf_cust_id__empty=true` and `=false` both returned 0 of 12; unclear whether that lookup is broken for text custom fields or simply every tenant has a value — not resolvable read-only.

## KQ5. Size, fetch cost, auth, caching of the schema; per-endpoint parameter counts for the MCP-mapped types

### Takeaway
The JSON schema is 9.3 MB, 292 paths, 151 list-GET operations, 11,537 list parameters; all 126 object types in the MCP server's map resolve to a schema path (median 79.5 parameters, max 296). It is served **without a token**, from a 24-hour Django page cache (0.11 s warm, ~5.1 s on a cache miss).

### Cited Findings
- `netbox-openapi.json`: 9,313,713 bytes; YAML default (`/api/schema/`) 4,201,566 bytes, `Content-Disposition: inline; filename="NetBox REST API (4.3).yaml"`; `paths` 292; list-GET operations 151; `components` keys `schemas`, `securitySchemes` — schema file / `curl -D -`.
- MCP map: `NETBOX_OBJECT_TYPES` in `/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server/src/netbox_mcp_server/netbox_types.py` has **126** entries (`{'name':..., 'endpoint': 'circuits/circuits'}` form); 126/126 map to a schema path with `get.parameters`; counts min 3 / median 79.5 / mean 91.3 / max 296 / sum 11,504. Largest: `dcim.interface` 296, `dcim.device` 292, `dcim.rack` 221, `dcim.devicetype` 184, `virtualization.virtualmachine` 183, `dcim.inventoryitem` 176, `dcim.poweroutlet` 167. Smallest: `extras.notification`, `extras.notificationgroup`, `extras.subscription` 3 each; `core.objecttype` 7 — computed from both files.
- List-GET paths in the schema but not in the map (25): sub-resources (`.../{id}/trace/`, `.../{id}/paths/`, `.../{id}/available-ips/`, `/api/dcim/racks/{id}/elevation/`), `/api/core/background-*`, `/api/dcim/connected-device/`, `/api/extras/dashboard/`, `/api/schema/`, `/api/status/`, `/api/users/config/` — schema file.
- Auth: `GET /api/schema/?format=json` without a token → **200** (9,313,713 B); `GET /api/dcim/devices/` without a token → **403**; `/api/schema/swagger-ui/` → 200. `LOGIN_REQUIRED` defaults to `True` in the container config (`/etc/netbox/config/configuration.py:226`) — live / container.
- Caching: `netbox/netbox/urls.py:58-62` wraps the view in `cache_page(timeout=86400, key_prefix=f"api_schema_{settings.RELEASE.version}")`; response headers `Cache-Control: max-age=86400`, `Expires: <+24h>`, `Vary: HX-Request, Accept-Language, Cookie, origin`. Timing: warm hits 0.106 / 0.122 / 0.108 s; a cache miss forced with `Accept-Language: de-DE` (plain GET) took **5.13 s** (9,465,242 B — descriptions are translated, so the size differs per language), the repeat 0.25 s, another miss (`fr-FR`) 5.07 s — live.
- `SPECTACULAR_SETTINGS` (`netbox/settings.py:714-727`): `COMPONENT_SPLIT_REQUEST: True`, `POSTPROCESSING_HOOKS: []`, version `RELEASE.full_version` — container.

### Inferences
- Fetching once per NetBox version (the cache key is version-prefixed) is cheap; parsing 9.3 MB of JSON per process start is the real cost, so a validator should pre-index `path → set(names)` and persist it.
- Because `Vary` includes `Accept-Language`, descriptions (e.g. "Tenant (slug)") are locale-dependent; key names are not.

### Gaps
- Not measured: JSON parse/index time in Python for the validator (would be a benchmark; excluded by the constraints).

## KQ6. Does the schema include enum values for `status`, `action`, `type`-like fields, so value validation is possible?

### Takeaway
Yes, but in two shapes: 49 parameters carry an inline `enum` (e.g. object-changes `action`, device `face`, `airflow`), while 870 parameters (all the array-typed `status`/`type`-style filters) carry only a drf-spectacular `x-spec-enum-id`; the values must be looked up in `components.schemas` by that id, and every one of the 54 distinct ids referenced this way resolves.

### Cited Findings
- Devices `status`: `{"in":"query","name":"status","schema":{"type":"array","items":{"type":"string","x-spec-enum-id":"8d8971779f16ee18"}},"explode":true,"style":"form"}` — no inline enum; the id appears 5 times in components (`Device`, `DeviceWithConfigContext`, `DeviceWithConfigContextRequest`, `PatchedWritableDeviceWithConfigContextRequest`, `WritableDeviceWithConfigContextRequest`) with `enum: ["offline","active","planned","staged","failed","inventory","decommissioning"]` — schema file.
- Inline enums: `face` → `["front","rear"]`; `airflow` → 10 values (`bottom-to-top`, ... `top-to-bottom`), `nullable: true`; object-changes `action` → `["create","delete","update"]` with a bullet description — schema file.
- Census: 49 params with inline `enum`; 870 with `x-spec-enum-id` but no inline enum; 82 distinct ids carry values somewhere in the document; 54 distinct ids are referenced by value-less params; 0 unresolvable — schema file.
- Live value checks: `status=active` 137, `status=planned` 2, `status__n=active` 4, `status=bogus` → 400; `face=front` 111, `face=bogus` → 400; `action=create` 3,158, `action=created` → 400 — live.
- The reason array-typed choice filters lose the inline enum: `_get_field_description` strips the auto-generated choice list when `choices` is callable and the multi-value branch builds the schema from the model field (`drf_spectacular/contrib/django_filters.py:132-134, 259-275`); the `x-spec-enum-id` is drf-spectacular's enum-dedup hook, not OpenAPI standard.

### Inferences
- Value validation for enums is feasible for both `action` (direct) and `status`-style filters (via an `x-spec-enum-id → enum` index built from `components`); it would have caught `action=created` and would catch `status=bogus`. It cannot validate slug/RD values (`site`, `tenant`, `vrf`) because those are data, not schema.

### Gaps
- None for the sampled fields; the 870-param set was not spot-checked beyond `status`.

## KQ7. NetBox / drf-spectacular version caveats and known gaps in filter parameter generation

### Takeaway
On 4.3.3 (drf-spectacular 0.28.0, django-filter 25.1) the generator is exact for key names but wrong or silent about: FK-id types for tree-node filters (109 `*_id` params typed string), `created__empty`/`last_updated__empty` (listed, unusable), nullability (under-reported), the `null` sentinel, `__n=null` complement semantics, descriptions present on only 18% of parameters, instance-level `cf_*` filters, and non-filterset params (`fields`, `brief`). `__regex`/`__iregex` arrive in v4.3.5, so the schema is version-specific and must be re-fetched per upgrade.

### Cited Findings
- Versions: `netbox-version 4.3.3`, `drf_spectacular 0.28.0`, `drf_spectacular_sidecar 2025.6.1`, `django_filters 25.1`, `rest_framework 3.16.0` — `http://localhost:8000/api/status/`.
- Descriptions: 2,105 of 11,537 parameters have a `description`; on devices 72 of 292. Slug hints present verbatim: `cluster_group`/`__n` "Cluster group (slug)", `device_type` "Device type (slug)", `manufacturer` "Manufacturer (slug)", `model` "Device model (slug)", `platform` "Platform (slug)", `site` "Site name (slug)", `tenant` "Tenant (slug)"; `role`/`role_id` have **no** description — schema file. Descriptions come from `filter_field.label` / `help_text` (`drf_spectacular/contrib/django_filters.py:259-265`), so only labelled declared filters get one.
- Boolean filters: schema says `{"type":"boolean"}`; django-filter's `BooleanWidget` accepts only `"true"`/`"false"` (`django_filters/widgets.py:155-167`), so `has_primary_ip=1`/`=no` are dropped silently (141) while `true`/`false`/`False` work (44/97) — live + container.
- `regex`/`iregex` for string fields: [netbox issue #19903](https://github.com/netbox-community/netbox/issues/19903), milestone v4.3.5, closed 2025-07-24; absent from 4.3.3's `FILTER_CHAR_BASED_LOOKUP_MAP` and from this schema; live ignored.
- The object-changes endpoint moved to `/api/core/object-changes/` (the `extras` path is 404 and absent from the schema) — live + schema file.
- Known drf-spectacular/django-filter typing complaints exist upstream ([issue #317 "Wrong django-filter types"](https://github.com/tfranzel/drf-spectacular/issues/317), [issue #234](https://github.com/tfranzel/drf-spectacular/issues/234)); the concrete 4.3.3 symptom is the "Defaulting to string" fallback in `contrib/django_filters.py:132-145`.

### Inferences
- Treat the schema as an authority for **key existence per path** and for **enum values**, and as a hint only for types, nullability and descriptions; keep the hand rules for `__n=null`, `<rel>_id=null`, `vrf`→`vrf_id`, slug values, `fields`/`brief`/`cf_*`, and boolean spellings.
- Re-generating the index on each `netbox-version` change is required: the lookup set changes at 4.3.5 (regex) and the project's whitelist would otherwise drift in both directions.

### Gaps
- I did not find a NetBox-side changelog entry documenting the `created__empty` 400 behaviour; it is inferred from the `empty='isnull'` map and the `lookup_expr == 'empty'` check in `filtersets.py:189`, and confirmed live, but not cross-checked against an upstream issue.
- Whether the 109 string-typed `*_id` params are all `TreeNodeMultipleChoiceFilter` instances was verified for device `role_id` only (`dcim/filtersets.py:1043`), the rest is inferred from the name set (`region_id`, `site_group_id`, `location_id`, `tenant_group_id`, `group_id`, `ancestor_id`).

## Coverage summary (what a schema-driven validator would and would not catch)

| class of mistake | example | schema key check | schema value/enum check | needs a hand rule |
|---|---|---|---|---|
| wrong key name | `device_role_id`, `devicetype_id`, `tenant__ic`, `time__gte`, `action__n` | **catches** | — | no |
| unsupported lookup | `__in`, `__contains`, `__icontains`, `__isnull`, `__empty` on FK, `__gt` on FK, `__regex`/`__iregex` (4.3.3) | **catches** | — | no |
| prefix-only filters on ip-addresses | `within`, `within_include`, `without`, `contains`, `prefix` | **catches** | — | no (but keep `parent` hint) |
| wrong enum value | `action=created`, `status=bogus` | — | **catches** (inline enum or `x-spec-enum-id` lookup) | no |
| wrong boolean spelling | `has_primary_ip=1`, `serial__empty=maybe` | — | catches if value must be JSON boolean | no |
| name instead of slug | `site=DM-Scranton`, `tenant=halvorsen-logistics` | misses | misses (description says "(slug)" only) | **yes** |
| VRF name instead of RD | `vrf=hvl-guest` | misses | misses (description "VRF (RD)", title "Route distinguisher") | **yes** (`vrf_id`) |
| complement trap | `tenant__n=null` | misses | misses | **yes** |
| listed but broken | `created__empty=true` (400) | misses (listed) | misleads (wants date-time) | **yes** |
| nullable under-reported | `location_id=null` works, schema not nullable | n/a | would wrongly reject if enforced | **yes** (do not enforce `nullable`) |
| honoured but unlisted | `fields`, `brief`, `cf_<name>[__lookup]` | would wrongly reject | — | **yes** (whitelist) |
| wrong type in schema | `role_id` as string (109 params) | n/a | would wrongly accept `abc` | do not enforce integer-ness from schema |
