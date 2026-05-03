# NetBox MCP Filter Examples

This document provides concrete examples of filter patterns that work and don't work with the NetBox MCP server.

## Failed Queries from Testing

These are real queries that failed in baseline implementations but succeed with our two-step approach:

### Query 1: "Show cables connected to device dmi01-nashua-pdu01"

**Baseline Attempt (FAILS):**
```python
# This generates: {"termination_a__device_id": 19}
# ERROR: Invalid filter: termination_a__device_id
cables = await netbox_get_objects("dcim.cable", {"termination_a__device_id": 19})
```

**Our Approach (SUCCEEDS):**
```python
# Step 1: Get the device
device_result = await netbox_get_objects("dcim.device", {"name": "dmi01-nashua-pdu01"})
device_id = device_result['results'][0]['id']

# Step 2: Get cables connected to this device
# Note: We need to check both termination sides
cables_a = await netbox_get_objects("dcim.cable", {"termination_a_id": device_id, "termination_a_type": "dcim.device"})
cables_b = await netbox_get_objects("dcim.cable", {"termination_b_id": device_id, "termination_b_type": "dcim.device"})

# Combine results
all_cables = cables_a['results'] + cables_b['results']
```

### Query 2: "Show all Dunder-Mifflin sites with device counts"

**Baseline Attempt (FAILS):**
```python
# This generates: {"name__icontains": "dunder"}
# ERROR: Invalid filter: name__icontains
sites = await netbox_get_objects("dcim.site", {"name__icontains": "dunder"})
```

**Our Approach (SUCCEEDS):**
```python
# Step 1: Search for Dunder-Mifflin sites
sites_result = await netbox_search_objects(query="Dunder-Mifflin")

# Step 2: For each site, get device count
site_device_counts = []
for site in sites_result['results']:
    if site['object_type'] == 'dcim.site':
        devices = await netbox_get_objects("dcim.device", {"site_id": site['id']})
        site_device_counts.append({
            'site': site['name'],
            'device_count': devices['count']
        })
```

### Query 3: "List interfaces on device with site_id 5"

**Baseline Attempt (FAILS):**
```python
# This generates: {"device__site_id": 5}
# ERROR: Invalid filter: device__site_id
interfaces = await netbox_get_objects("dcim.interface", {"device__site_id": 5})
```

**Our Approach (SUCCEEDS):**
```python
# Step 1: Get all devices in site 5
devices = await netbox_get_objects("dcim.device", {"site_id": 5})

# Step 2: Get interfaces for each device
all_interfaces = []
for device in devices['results']:
    interfaces = await netbox_get_objects("dcim.interface", {"device_id": device['id']})
    all_interfaces.extend(interfaces['results'])
```

### Query 4: "Find all power outlets in rack R01"

**Baseline Attempt (FAILS):**
```python
# This might generate: {"device__rack__name": "R01"}
# ERROR: Invalid filter: device__rack__name
outlets = await netbox_get_objects("dcim.poweroutlet", {"device__rack__name": "R01"})
```

**Our Approach (SUCCEEDS):**
```python
# Step 1: Get the rack
rack = await netbox_get_objects("dcim.rack", {"name": "R01"})
rack_id = rack['results'][0]['id']

# Step 2: Get devices in the rack
devices = await netbox_get_objects("dcim.device", {"rack_id": rack_id})

# Step 3: Get power outlets for each device
all_outlets = []
for device in devices['results']:
    outlets = await netbox_get_objects("dcim.poweroutlet", {"device_id": device['id']})
    all_outlets.extend(outlets['results'])
```

## Working Filter Examples

### Direct ID Filters
```python
# These always work
{"site_id": 1}
{"device_id": 42}
{"rack_id": 7}
{"tenant_id": 3}
{"vlan_id": 100}
{"circuit_id": 25}
```

### Exact Match Filters
```python
# Exact string matches work
{"name": "nyc-router-01"}
{"slug": "nyc-dc"}
{"status": "active"}
{"role": "server"}
```

### Valid Combined Filters
```python
# Multiple simple filters can be combined
{
    "site_id": 1,
    "status": "active",
    "role": "server"
}
```

## Filters That Will Always Fail

### Relationship Traversals
```python
# These will NEVER work with MCP
{"device__site_id": 1}  # ❌
{"interface__device__name": "router01"}  # ❌
{"ipaddress__interface__device_id": 5}  # ❌
{"cable__termination_a__device": 10}  # ❌
```

### Django Lookups
```python
# These Django ORM lookups are not supported
{"name__icontains": "router"}  # ❌
{"name__startswith": "nyc"}  # ❌
{"created__gte": "2024-01-01"}  # ❌
{"id__in": [1, 2, 3]}  # ❌
{"description__regex": ".*prod.*"}  # ❌
```

## Search Examples

When filters won't work, use search:

```python
# Search across all object types
results = await netbox_search_objects(query="production server")

# Search specific object types
results = await netbox_search_objects(
    query="router",
    object_types=["dcim.device", "virtualization.virtualmachine"]
)

# Search and filter results in code
results = await netbox_search_objects(query="nyc")
nyc_devices = [r for r in results['results'] if r['object_type'] == 'dcim.device']
```

## Performance Tips

1. **Minimize API Calls**: Batch operations when possible
2. **Cache Results**: Store frequently accessed objects (sites, racks) temporarily
3. **Use Field Selection**: Request only needed fields to reduce payload size
4. **Parallel Queries**: When getting data for multiple objects, consider parallel execution

## Debugging Failed Filters

When a filter fails:

1. Check for double underscores (`__`)
2. Verify it's not a Django lookup
3. Try the query with a direct ID instead
4. Consider if search would work better
5. Break complex queries into steps

Remember: The MCP server is strict about filters. When in doubt, use simple filters and combine results in code.