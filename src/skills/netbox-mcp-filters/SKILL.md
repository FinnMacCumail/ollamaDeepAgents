---
title: NetBox MCP Filter Constraints
description: Critical knowledge for successful NetBox queries via MCP
version: 1.0.0
tags: [netbox, mcp, filters, constraints, recovery]
priority: high
trigger: netbox queries with filtering
---

# NetBox MCP Filter Constraints

This skill provides essential knowledge about NetBox MCP server filter limitations and how to work around them. Following these patterns will prevent filter errors and ensure successful queries.

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