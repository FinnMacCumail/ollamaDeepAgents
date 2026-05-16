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

**HARD LIMIT:** the `netbox_get_objects` tool schema caps `limit` at **100**. Passing
`limit > 100` will fail with a Pydantic validation error before any HTTP request is made.
Plan around this cap.

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

A common need: "I have a known list of IDs, fetch them all in one query." The Django
ORM idiom for this is `id__in=[1,2,3]`, but **the `__in` lookup suffix is FORBIDDEN**
by this MCP server (it's a Django-lookup pattern — see CRITICAL FILTER LIMITATIONS
below). The validator will reject any filter containing `__in` before the request is
sent.

The correct alternative is to **pass a list as the value of the non-suffixed key**.
NetBox accepts repeated query parameters as multi-value (`?id=1&id=2&id=3` semantics),
and the MCP layer serialises a Python list to that form automatically:

```python
# WRONG — validator rejects (Django lookup)
netbox_get_objects("dcim.site", filters={"id__in": [1, 2, 3, 14]})

# RIGHT — pass list as value of bare key
netbox_get_objects("dcim.site", filters={"id": [1, 2, 3, 14]})
```

Same pattern works for relational *_id keys when you have multiple specific objects:

```python
# Fetch racks belonging to any of several known sites in one call
netbox_get_objects("dcim.rack", filters={"site_id": [1, 2, 3]}, fields=[...])
```

When NOT to batch: if you don't already have the IDs in hand, don't run a separate
lookup just to collect them — usually it's simpler to fetch the parent set (e.g. all
sites) and filter client-side, or use a `tenant_id` / `region_id` / similar
relational filter that covers the group implicitly.

## DECOMPOSING MULTI-ASPECT QUERIES

When the user asks for one entity *with* multiple related aspects (e.g. "show all sites
with device counts, rack allocations, and IP prefix assignments"), break it down before
issuing tool calls:

1. **List the aspects.** Each "with X" or "and Y" is a separate sub-query.
2. **Identify shared dependencies.** If every aspect needs `site_id`, fetch sites once.
3. **Check whether the parent object already includes the aspect.** Many NetBox objects
   carry counts/relations as fields:
   - Sites include `device_count`, `rack_count`, `prefix_count`, `circuit_count`,
     `vlan_count` — add them to `fields=[...]` and you are done for that aspect, no extra tool call.
   - Devices include `interface_count`, `console_port_count`, `power_port_count`, etc.
   - Racks include `device_count`, `powerfeed_count`.
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

## CRITICAL FILTER LIMITATIONS

### ❌ NEVER Use These Patterns

1. **Multi-hop Relationship Filters**
   - `device__site_id` - FAILS
   - `termination_a__device_id` - FAILS
   - `interface__device__name` - FAILS
   - `rack__site__name` - FAILS

2. **Django ORM Lookup Suffixes**
   - `name__icontains` - FAILS
   - `name__contains` - FAILS
   - `name__startswith` - FAILS
   - `name__endswith` - FAILS
   - `id__in` - FAILS
   - `created__gt` - FAILS
   - `status__regex` - FAILS

3. **Complex Chained Filters**
   - Any filter with double underscores for relationships
   - Filters attempting to traverse foreign key relationships

### ✅ ALWAYS Use These Patterns

1. **Direct ID Filters**
   ```python
   {"device_id": 123}
   {"site_id": 5}
   {"rack_id": 42}
   {"tenant_id": 7}
   ```

2. **Exact Name Matches**
   ```python
   {"name": "exact-device-name"}
   {"slug": "exact-slug"}
   ```

3. **Simple Field Filters**
   ```python
   {"status": "active"}
   {"role": "server"}
   {"type": "virtual"}
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

For pattern matching or partial matches, use the search tool instead of filters:

### Example: Find all Dunder-Mifflin sites

#### ❌ WRONG (Will Fail):
```python
sites = netbox_get_objects("dcim.site", {"name__icontains": "dunder"})
```

#### ✅ CORRECT (Will Succeed):
```python
sites = netbox_search_objects(query="Dunder-Mifflin")
```

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