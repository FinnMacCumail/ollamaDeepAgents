---
name: netbox-mcp-filters
description: Critical knowledge for successful NetBox queries via MCP — filter constraints, two-step query patterns, pagination handling, and multi-aspect query decomposition. Load this skill whenever building a NetBox query that involves filtering by relationships, paginated result sets, or composing multi-part queries (e.g. "show X with Y and Z").
version: 1.0.0
tags: [netbox, mcp, filters, constraints, recovery, pagination, decomposition]
priority: high
---

# NetBox MCP Filter Constraints

This skill provides essential knowledge about NetBox MCP server filter limitations and how to work around them. Following these patterns will prevent filter errors and ensure successful queries.

## HANDLING PAGINATED RESPONSES

NetBox returns paginated results. A response shaped like this is INCOMPLETE:
```json
{"count": 14, "next": "http://.../?...&offset=5", "previous": null, "results": [<5 items>]}
```

**LIMITS — both matter:**
- The `netbox_get_objects` tool schema caps `limit` at **100**. Passing `limit > 100` will
  fail with a Pydantic validation error before any HTTP request is made.
- The DEFAULT `limit` when you omit it is **5**, not 50. If you do not pass `limit=` on a
  list query, you will get at most 5 results and may silently miss the rest. **Always set
  `limit=100` explicitly for any list query**, then check the `count` field in the
  response envelope to see if pagination is needed.

When `next` is non-null, you have only seen part of the data. You MUST do one of:

1. **Fetch the next page** by re-calling the same tool with `offset=<previous offset + limit>`,
   accumulating `results` until `next` is null.
2. **Raise the limit toward the cap** (e.g. `limit=100`) so all results return in one
   page when you know `count <= 100`.
3. **Tell the user the result is partial** — explicitly state "showing N of M" — but ONLY if
   the user clearly asked for a sample, or if N is large enough to be useful as-is.

NEVER silently ignore a non-null `next`. Returning 5 of 14 sites without flagging it is a
correctness failure.

```python
# Pagination loop pattern (works for any count)
all_results = []
offset = 0
PAGE = 100  # match the tool's max
while True:
    page = netbox_get_objects("dcim.site", filters={"tenant_id": 5}, limit=PAGE, offset=offset)
    all_results.extend(page["results"])
    if not page.get("next"):
        break
    offset += PAGE
```

## BATCHING MULTIPLE IDs IN A SINGLE CALL

A common need: "I have a known list of IDs, fetch them all in one query." TWO forms
both work for standard fields — the canonical `__in` lookup, and the bare-key list form:

```python
# CANONICAL — __in lookup (matches the MCP server's own documented example)
netbox_get_objects("dcim.site", filters={"id__in": [1, 2, 3, 14]})

# ALSO WORKS — bare key with a list value (NetBox accepts repeated query params
#              as multi-value: ?id=1&id=2&id=3)
netbox_get_objects("dcim.site", filters={"id": [1, 2, 3, 14]})

# Both also work for relational *_id keys:
netbox_get_objects("dcim.rack", filters={"site_id__in": [1, 2, 3]}, fields=[...])
netbox_get_objects("dcim.rack", filters={"site_id": [1, 2, 3]}, fields=[...])
```

Prefer the `__in` form — it matches the MCP server's tool-docstring example
(`{'id__in': [1,2,3]}`) and is unambiguous.

### Important exception — GenericForeignKey ID fields are SCALAR

A few filters look like `*_id` but are actually scalar (single value only) because they
target a GenericForeignKey. Neither `__in` nor list-form works on these:

| Object | Scalar GFK ID field | Use this multi-value alias instead |
|---|---|---|
| `ipam.ipaddress` | `assigned_object_id` (paired with `assigned_object_type`) | `interface_id`, `vminterface_id`, `fhrpgroup_id`, `device_id`, `virtual_machine_id` |
| `ipam.prefix` | `scope_id` (paired with `scope_type`) | `site_id`, `location_id`, `region_id`, `site_group_id` |
| `virtualization.cluster` | `scope_id` (paired with `scope_type`) | `site_id`, `location_id`, `region_id` |
| `tenancy.contactassignment` | `object_id` (paired with `object_type`) | `contact_id`, `role_id` |

If you try to use multi-value on `assigned_object_id` + `assigned_object_type`, NetBox
returns HTTP 400 (or silently returns the wrong result set). See the
"FILTERING IP ADDRESSES BY ASSIGNED OBJECT" section below for the correct pattern.

### When NOT to batch

If you don't already have the IDs in hand, don't run a separate lookup just to collect
them — usually it's simpler to fetch the parent set (e.g. all sites) and filter
client-side, or use a `tenant_id` / `region_id` / similar relational filter that covers
the group implicitly.

## FILTERING IP ADDRESSES BY ASSIGNED OBJECT

The `ipam.ipaddress` model uses a GenericForeignKey to attach IPs to interfaces (or
VM interfaces, or FHRP groups). The schema fields are `assigned_object_type` (string)
and `assigned_object_id` (int). DO NOT combine these directly with multi-value:

```python
# WRONG — returns HTTP 400. `assigned_object_id` is scalar; combining with
# multi-value `assigned_object_type` is unsupported by NetBox's GFK filter.
netbox_get_objects("ipam.ipaddress",
    filters={"assigned_object_id": [66, 67, 68, ...],
             "assigned_object_type": "dcim.interface"})
```

Use the typed alias filters instead — they accept multi-value and are the recommended path:

```python
# RIGHT — for IPs on a list of interfaces:
netbox_get_objects("ipam.ipaddress",
    filters={"interface_id": [66, 67, 68, 69]},
    fields=["id", "address", "status", "dns_name"])

# RIGHT — for IPs on VM interfaces:
netbox_get_objects("ipam.ipaddress", filters={"vminterface_id": [...]})

# RIGHT — for IPs on FHRP groups:
netbox_get_objects("ipam.ipaddress", filters={"fhrpgroup_id": [...]})

# RIGHT — all IPs on any interface of a device (walks VC):
netbox_get_objects("ipam.ipaddress", filters={"device_id": 27})

# RIGHT — all IPs on any interface of a VM:
netbox_get_objects("ipam.ipaddress", filters={"virtual_machine_id": 14})
```

**Even better — skip the `ipam.ipaddress` query entirely** when possible. Interfaces
expose `count_ipaddresses` as a field — if you only need to know whether a device's
interfaces have IPs (or how many), read that count off the parent interface objects:

```python
# Check first: does the device have any IPs assigned to its interfaces?
ifaces = netbox_get_objects("dcim.interface",
    filters={"device_id": 27},
    fields=["id", "name", "count_ipaddresses"])
total_ips = sum(i["count_ipaddresses"] for i in ifaces["results"])
# If total_ips == 0, skip the ipam.ipaddress query entirely.
```

Devices also expose `primary_ip4`, `primary_ip6`, and `oob_ip` as fully-resolved nested
objects — those don't require a follow-up `ipam.ipaddress` query either.

## AVOID REDUNDANT SEARCHES

When `netbox_search_objects` returns results, USE THEM. Do not issue further searches
with variant query strings ("dunder", "mifflin", "DM-") hoping for more or different
results — NetBox's search is already broad and case-insensitive across multiple fields.

If the first search returned what looks like the right set, post-filter client-side
rather than re-querying. If it returned nothing, try ONE alternative formulation, not
several in parallel.

```python
# WRONG — three searches when one already returned the data
netbox_search_objects(query="Dunder Mifflin")   # returns 14 sites
netbox_search_objects(query="dunder")           # redundant, wastes a tool call
netbox_search_objects(query="mifflin")          # redundant
netbox_search_objects(query="DM-")              # redundant

# RIGHT — trust the first search, post-filter if needed
results = netbox_search_objects(query="Dunder Mifflin")
# (filter results client-side by name prefix, status, etc.)
```

## TAG FILTERING IS "AND", NOT "OR"

Every other multi-value filter in NetBox uses OR semantics — `?region=na&region=eu`
returns objects matching either region. **Tags invert this**: `?tag=prod&tag=critical`
returns ONLY objects that have BOTH tags. This is the single biggest silent-wrong-result
trap in the NetBox API.

```python
# Returns objects tagged with BOTH "prod" AND "critical" — usually NOT what you mean.
netbox_get_objects("dcim.device", filters={"tag": ["prod", "critical"]})

# If you need OR semantics for tags, issue separate queries and union client-side:
prod = netbox_get_objects("dcim.device", filters={"tag": "prod"})
crit = netbox_get_objects("dcim.device", filters={"tag": "critical"})
combined = {r["id"]: r for r in prod["results"] + crit["results"]}.values()
```

## IPAM PREFIX FILTERING

`ipam.prefix` objects attach to scope objects (sites, locations, regions, vlans) via a
generic `scope` field. For per-site prefix queries, the legacy `site_id` filter is
supported and is the simplest path — DO NOT explore `scope_id` + `scope_type` filtering
for site-scoped queries.

```python
# RIGHT — direct, single-key filter
netbox_get_objects("ipam.prefix", filters={"site_id": 5}, fields=[...])
netbox_get_objects("ipam.prefix", filters={"site_id": [1, 2, 3]}, fields=[...])

# AVOID — unnecessary schema exploration for site-scoped queries
netbox_get_objects("ipam.prefix", filters={"scope_id": 5, "scope_type": "dcim.site"})
```

The `scope_id` + `scope_type` pair is only worth reaching for when the user explicitly
wants prefixes scoped to non-site objects (locations, vlans, etc.). For everything else,
stick with `site_id`.

## STATUS / ENUM / SLUG VALUES ARE LOWERCASE

All status, role, type, and slug values in NetBox filters are lowercase machine-form,
NOT the human-readable display form.

```python
# WRONG — capitalised display labels are rejected with HTTP 400
filters={"status": "Active"}
filters={"status": "Decommissioning"}
filters={"role": "Access Switch"}

# RIGHT — lowercase machine slugs
filters={"status": "active"}
filters={"status": "decommissioning"}
filters={"role": "access-switch"}      # spaces become hyphens
filters={"site": "dm-akron"}            # slug, not "DM-Akron"
```

When in doubt about the allowed values for a status/role enum on a given model, you can
introspect the schema via `OPTIONS /api/<app>/<model>/` (see HIDDEN API LEVERS below).

## DECOMPOSING MULTI-ASPECT QUERIES

When the user asks for one entity *with* multiple related aspects (e.g. "show all sites
with device counts, rack allocations, and IP prefix assignments"), break it down before
issuing tool calls:

1. **List the aspects.** Each "with X" or "and Y" is a separate sub-query.
2. **Identify shared dependencies.** If every aspect needs `site_id`, fetch sites once.
3. **Check whether the parent object already includes the aspect.** Many NetBox objects
   carry counts and resolved child objects as native fields — add them to `fields=[...]`
   and you have the answer with NO child query at all. Full catalog:

   | Parent object | Count / resolved fields available |
   |---|---|
   | `dcim.site` | `device_count`, `rack_count`, `prefix_count`, `vlan_count`, `circuit_count`, `virtualmachine_count` |
   | `dcim.region` | `site_count`, `prefix_count`, `_depth` |
   | `dcim.location` | `rack_count`, `device_count`, `prefix_count`, `_depth` |
   | `dcim.rack` | `device_count`, `powerfeed_count` |
   | `dcim.device` | `interface_count`, `console_port_count`, `console_server_port_count`, `power_port_count`, `power_outlet_count`, `front_port_count`, `rear_port_count`, `device_bay_count`, `module_bay_count`, `inventory_item_count` — PLUS resolved nested objects: `primary_ip4`, `primary_ip6`, `oob_ip` (no follow-up IP query needed for these) |
   | `dcim.interface` | `count_ipaddresses`, `count_fhrp_groups`, resolved `connected_endpoints` (with `connected_endpoints_type` and `connected_endpoints_reachable`), `link_peers`, `cable` |
   | `ipam.prefix` | `children` (child-prefix count), `_depth` (tree depth). **No `device_count` / `ip_count`** — those need a child query. |
   | `virtualization.virtualmachine` | `interface_count`, `virtual_disk_count` |
   | `virtualization.cluster` | `device_count`, `virtualmachine_count` |

   Example: to answer "what IPs are on device X?", first read `count_ipaddresses` on
   each of X's interfaces. If they're all zero, the answer is "none" — skip the
   `ipam.ipaddress` query entirely.
4. **Only issue separate tool calls for aspects not on the parent.** For each remaining
   aspect, do a single `netbox_get_objects(<aspect_type>, filters={<parent>_id__in: ...})`
   if supported, otherwise loop. Use `fields=[...]` on every call.
5. **Aggregate, then format.** Build the answer in one pass at the end — do not write
   partial answers between tool calls.

Example planning for "Show all Dunder Mifflin sites with device counts, rack allocations,
and IP prefix assignments":
- Aspect A (devices): `device_count` is a site field → no extra call
- Aspect B (racks): `rack_count` is a site field; for *which* racks, one call:
  `netbox_get_objects("dcim.rack", filters={"tenant_id": 5}, limit=100)` — if the result's
  `next` is non-null, paginate (see HANDLING PAGINATED RESPONSES above)
- Aspect C (IP prefixes): `netbox_get_objects("ipam.prefix", filters={"tenant_id": 5}, limit=100)`,
  paginate if `next` is non-null
- Total: 3-4 tool calls (with pagination), not 14×3=42

## TENANCY INHERITANCE IS NOT AUTOMATIC

Objects in NetBox do NOT automatically inherit their parent's tenant. Filtering
`?tenant_id=N` returns only objects where the tenant is **directly assigned** — not
objects that conceptually belong to the tenant via their site, rack, or device.

This bites hardest with infrastructure objects engineers don't think to tag:
- **Patch panels** typically have no explicit tenant even when their rack does
- **Cables** are not tenanted
- **Interfaces** are not tenanted (they inherit conceptually from the device)
- **IP addresses** are individually tenanted but rarely set when the prefix isn't

So `dcim.device?tenant_id=5` may return fewer devices than there really are at the
tenant's sites. To get accurate counts for tenant-wide aggregations, prefer querying
by **site_id** (which IS reliably tenanted) and walk down:

```python
# UNDERCOUNTS — patch panels without explicit tenant are dropped
devices = netbox_get_objects("dcim.device", filters={"tenant_id": 5})

# ACCURATE — get the tenant's sites first, then everything at those sites
sites = netbox_get_objects("dcim.site",
    filters={"tenant_id": 5}, fields=["id", "device_count"])
# Sum site.device_count for the canonical total
total = sum(s["device_count"] for s in sites["results"])

# Or for a per-device list, query by site_id (multi-value):
device_lists = netbox_get_objects("dcim.device",
    filters={"site_id": [s["id"] for s in sites["results"]]},
    fields=["id", "name", "site", "device_type"])
```

The `device_count` field on the site is computed server-side from the actual
device-to-site relationship, so it does NOT undercount infrastructure objects that
lack an explicit tenant.

## HIDDEN API LEVERS

These NetBox API features rarely surface in tutorials but solve common problems:

- **`brief=True` parameter** — returns a minimal serializer (id, url, display, slug only).
  Use when you only need to populate a lookup list or count rows, NOT when you need
  detailed fields.

- **`exclude=config_context` (via the `fields=` parameter)** — `config_context` on
  `dcim.device` is the documented #1 cause of API timeouts. When listing devices,
  ALWAYS use explicit `fields=[...]` that omits `config_context`. Recommended default:
  `fields=["id", "name", "status", "site", "device_type", "primary_ip4"]`.

- **`/api/<app>/<model>/` `OPTIONS` introspection** — returns the filter schema and the
  list of allowed values for enum fields (status, role, etc.). Use when you need to
  know "what status values does this model support" without guessing.

- **`/api/ipam/prefixes/<id>/available-ips/`** — GET returns the list of free IPs in a
  prefix; POST atomically allocates one. The right way to ask "what's the next free IP
  in 10.4.5.0/24" — never enumerate all IPs and diff against the prefix.

- **`/api/dcim/interfaces/<id>/trace/`** — walks the cable through pass-through ports
  (patch panels, MPO breakouts) until it hits a real endpoint. The right way to ask
  "what's actually on the other end of this cable" — REST-only, no GraphQL equivalent.

- **Containment filters on prefixes:**
  - `?within=10.0.0.0/8` — prefixes strictly inside 10/8
  - `?within_include=10.0.0.0/8` — prefixes inside 10/8, including 10/8 itself
  - `?contains=10.4.5.6` — prefixes that contain a specific IP or CIDR

- **`?q=<term>` per-model search** — different from the cross-model `netbox_search_objects`
  tool. Per-model `?q=` is narrower and faster when you already know the type.

## CRITICAL FILTER LIMITATIONS

### Valid lookup suffixes — the complete whitelist

The MCP server's `validate_filters()` function permits ONLY these `field__suffix`
lookups (verified against `netbox-mcp-server/src/netbox_mcp_server/server.py`):

```
n, ic, nic, isw, nisw, iew, niew, ie, nie, empty, regex, iregex,
lt, lte, gt, gte, in
```

What they mean:

| Suffix | Use for | Example |
|---|---|---|
| `n` | negation (not equal to) | `{"role_id__n": 4}` (role NOT 4) |
| `ic` / `nic` | (not) case-insensitive contains | `{"name__ic": "switch"}` |
| `isw` / `nisw` | (not) case-insensitive starts-with | `{"name__isw": "core-"}` |
| `iew` / `niew` | (not) case-insensitive ends-with | `{"name__iew": "-01"}` |
| `ie` / `nie` | (not) case-insensitive exact | `{"name__ie": "Router01"}` |
| `empty` | is null/empty | `{"serial__empty": "true"}` |
| `regex` / `iregex` | regex match (case-sensitive / -insensitive) | `{"name__iregex": "^core-.*-01$"}` |
| `lt` / `lte` / `gt` / `gte` | numeric / datetime comparisons | `{"created__gt": "2026-05-01T00:00:00Z"}` |
| `in` | multi-value (alternative to bare-key list form) | `{"id__in": [1, 2, 3]}` |

**Common mistake**: the model often writes `name__icontains` or `name__contains` (Django
ORM idioms). Neither is valid — use `name__ic` instead. Same for `__startswith` → `__isw`,
`__endswith` → `__iew`. The server will reject anything not on the whitelist above with
`ValueError`.

### ❌ Still NEVER use these patterns

1. **Multi-hop relationship traversal** (any chain of `__field__field`):
   - `device__site_id`, `interface__device__name`, `rack__site__name` — all FAIL.
   - Always use the two-step query pattern instead.

2. **GenericForeignKey ID fields combined with multi-value** (see BATCHING MULTIPLE IDs
   above for the alias filters to use instead):
   - `assigned_object_id` on `ipam.ipaddress`
   - `scope_id` on `ipam.prefix` and `virtualization.cluster`
   - `object_id` on `tenancy.contactassignment`

### ✅ Always-safe patterns

```python
{"device_id": 123}                  # direct FK
{"site_id": [1, 2, 3]}              # multi-value FK
{"name": "exact-device-name"}       # exact match
{"name__ic": "switch"}              # substring
{"slug": "exact-slug"}              # lowercase slug
{"status": "active"}                # lowercase status
{"role": "access-switch"}           # lowercase role slug
{"type": "virtual"}                 # lowercase type slug
{"created__gt": "2026-05-01T00:00:00Z"}   # datetime comparison
```

## Two-Step Query Pattern (CRITICAL)

When you need to filter by a related object, ALWAYS use a two-step approach:

### Example: Get cables for a specific device

#### ❌ WRONG (Will Fail):
```python
cables = netbox_get_objects("dcim.cable", {"termination_a__device_id": 19})
```

#### ✅ CORRECT (Will Succeed):
```python
# Step 1: Get the device by name
device = netbox_get_objects("dcim.device", {"name": "dmi01-nashua-pdu01"})

# Step 2: Use the device ID in the cable filter
cables = netbox_get_objects("dcim.cable", {"device_id": device['results'][0]['id']})
```

## Pattern Matching with Search

Two valid options for pattern / substring matching — pick by use case:

### Option A — per-model substring filter with `__ic` (case-insensitive contains)

Use when you already know the object type and want a bounded, fast result set:

```python
# Right — __ic is on the validated suffix whitelist
sites = netbox_get_objects("dcim.site",
    filters={"name__ic": "dunder"},
    fields=["id", "name", "slug", "status"])

# Wrong — __icontains is the Django ORM form, not accepted
sites = netbox_get_objects("dcim.site", {"name__icontains": "dunder"})
```

### Option B — cross-model search with `netbox_search_objects`

Use when you don't know the object type, or want a ranked global match:

```python
# Cross-model search — returns ranked results across all indexed object types
results = netbox_search_objects(query="Dunder-Mifflin")
```

`netbox_search_objects` walks a default list of 8 object types (devices, sites, IPs,
interfaces, racks, VLANs, circuits, VMs). Per-model `?name__ic=` is narrower and
faster when you already know the type.

## Common Query Patterns

### 1. Get Devices in a Site
```python
# Step 1: Get site by name
site = netbox_get_objects("dcim.site", {"name": "NYC-DC1"})
site_id = site['results'][0]['id']

# Step 2: Get devices in that site
devices = netbox_get_objects("dcim.device", {"site_id": site_id})
```

### 2. Get Interfaces for a Device
```python
# Step 1: Get device by name
device = netbox_get_objects("dcim.device", {"name": "router01"})
device_id = device['results'][0]['id']

# Step 2: Get interfaces for that device
interfaces = netbox_get_objects("dcim.interface", {"device_id": device_id})
```

### 3. Get IPs for a Device
```python
# Step 1: Get device
device = netbox_get_objects("dcim.device", {"name": "server01"})
device_id = device['results'][0]['id']

# Step 2: Get interfaces
interfaces = netbox_get_objects("dcim.interface", {"device_id": device_id})

# Step 3: Get IPs for each interface
for interface in interfaces['results']:
    ips = netbox_get_objects("ipam.ipaddress", {"interface_id": interface['id']})
```

### 4. Search Across Multiple Object Types
```python
# Use search for broad queries
results = netbox_search_objects(
    query="production",
    object_types=["dcim.site", "dcim.device", "virtualization.virtualmachine"]
)
```

## Error Recovery Strategies

When you encounter a filter error:

1. **Identify the problematic filter pattern**
   - Look for double underscores
   - Check for Django lookups

2. **Break into steps**
   - First query: Get the parent object by name/ID
   - Second query: Use the parent's ID in a simple filter

3. **Use search for patterns**
   - Replace `__icontains` with search
   - Replace complex filters with search + post-filtering

## Quick Reference Decision Tree

```
Need to filter NetBox objects?
├── Is it a direct ID or exact name match?
│   └── YES → Use netbox_get_objects with simple filter
├── Does it involve a relationship (__ in filter)?
│   └── YES → Use two-step query pattern
├── Need pattern matching or partial match?
│   └── YES → Use netbox_search_objects
└── Complex multi-level relationship?
    └── YES → Break into 3+ step queries
```

## Remember

- **Test filters mentally before executing**
- **When in doubt, use two-step queries**
- **Search is your friend for pattern matching**
- **Direct IDs always work**
- **The MCP server validates filters strictly**

This skill ensures your NetBox queries succeed by avoiding MCP filter constraints and using proven workaround patterns.