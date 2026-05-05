# NetBox MCP Filter Constraints

## Overview

The NetBox MCP (Model Context Protocol) server implements a strict subset of NetBox API filtering capabilities. Understanding these constraints is critical for successful query execution.

## The Core Problem

MCP translates tool parameters directly to NetBox API calls without Django ORM processing. This means:

1. **No Relationship Traversal**: Cannot follow foreign keys with `__`
2. **No Django Lookups**: Special suffixes like `__icontains` fail
3. **No Query Optimization**: Each filter applied literally

## Constraint Categories

### 1. Multi-Hop Filters (❌ NOT SUPPORTED)

These filters attempt to traverse relationships across models:

```python
# FAILS: Trying to filter by related object's field
{"device__site_id": 5}           # Get devices in site 5
{"interface__device__name": "router01"}  # Interfaces on named device
{"cable__termination_a__device": 10}     # Cables connected to device
{"ipaddress__interface__device_id": 42}  # IPs on device's interfaces
```

**Why it fails**: MCP doesn't resolve the Django ORM relationship chain.

**Solution**: Break into multiple queries:

```python
# Step 1: Get the parent object
site = netbox_get_objects("dcim.site", {"id": 5})

# Step 2: Use its ID directly
devices = netbox_get_objects("dcim.device", {"site_id": 5})
```

### 2. Django ORM Lookups (❌ NOT SUPPORTED)

These special suffixes modify filter behavior:

| Lookup | Purpose | Example | Status |
|--------|---------|---------|--------|
| `__icontains` | Case-insensitive contains | `{"name__icontains": "prod"}` | ❌ |
| `__contains` | Case-sensitive contains | `{"description__contains": "server"}` | ❌ |
| `__startswith` | Starts with pattern | `{"name__startswith": "NYC"}` | ❌ |
| `__endswith` | Ends with pattern | `{"name__endswith": "-01"}` | ❌ |
| `__regex` | Regex match | `{"name__regex": "^[A-Z]{3}"}` | ❌ |
| `__in` | Value in list | `{"id__in": [1,2,3]}` | ❌ |
| `__gt` | Greater than | `{"vlan_id__gt": 100}` | ❌ |
| `__gte` | Greater or equal | `{"created__gte": "2024-01-01"}` | ❌ |
| `__lt` | Less than | `{"prefix_length__lt": 24}` | ❌ |
| `__lte` | Less or equal | `{"asn__lte": 65000}` | ❌ |
| `__isnull` | Null check | `{"tenant__isnull": true}` | ❌ |

**Why it fails**: MCP doesn't process these Django-specific operators.

**Solution**: Use alternatives:

```python
# Instead of name__icontains
netbox_search_objects(query="prod")  # Use search

# Instead of id__in
# Make multiple queries or filter in code
ids = [1, 2, 3]
results = []
for id in ids:
    obj = netbox_get_object_by_id("dcim.device", id)
    results.append(obj)
```

### 3. Supported Filters (✅ WORKING)

These patterns work reliably:

#### Direct ID Filters
```python
{"id": 42}
{"site_id": 5}
{"device_id": 123}
{"rack_id": 7}
{"tenant_id": 3}
{"vlan_id": 100}
{"vrf_id": 2}
```

#### Exact String Matches
```python
{"name": "exact-device-name"}
{"slug": "nyc-dc1"}
{"status": "active"}
{"role": "server"}
{"type": "virtual"}
```

#### Boolean Filters
```python
{"enabled": true}
{"is_primary": false}
{"management_only": true}
```

#### Combined Filters
```python
{
    "site_id": 5,
    "status": "active",
    "role": "server"
}
```

## Common Query Patterns

### Pattern 1: Devices in a Site

❌ **Wrong:**
```python
# Attempts relationship traversal
cables = netbox_get_objects("dcim.cable", {
    "termination_a__device__site_id": 5
})
```

✅ **Correct:**
```python
# Step 1: Get site
site = netbox_get_objects("dcim.site", {"name": "NYC-DC1"})

# Step 2: Get devices in site
devices = netbox_get_objects("dcim.device", {
    "site_id": site['results'][0]['id']
})

# Step 3: Get cables for each device
all_cables = []
for device in devices['results']:
    cables = netbox_get_objects("dcim.cable", {
        "device_id": device['id']
    })
    all_cables.extend(cables['results'])
```

### Pattern 2: Search for Partial Matches

❌ **Wrong:**
```python
# Django lookup not supported
sites = netbox_get_objects("dcim.site", {
    "name__icontains": "prod"
})
```

✅ **Correct:**
```python
# Use search instead
results = netbox_search_objects(query="prod")

# Filter for sites in results
sites = [r for r in results['results']
         if r['object_type'] == 'dcim.site']
```

### Pattern 3: Interfaces with IP Addresses

❌ **Wrong:**
```python
# Multi-hop filter
interfaces = netbox_get_objects("dcim.interface", {
    "ipaddress__address__startswith": "192.168"
})
```

✅ **Correct:**
```python
# Step 1: Search for IPs
ips = netbox_search_objects(query="192.168")

# Step 2: Get interfaces for each IP
interfaces = []
for ip in ips['results']:
    if 'interface' in ip:
        interface = netbox_get_object_by_id(
            "dcim.interface",
            ip['interface']['id']
        )
        interfaces.append(interface)
```

## Error Messages

### Recognizing Filter Errors

Common error patterns:

```
"Invalid filter: device__site_id"
"MCP Filter Error: termination_a__device_id not supported"
"Filter 'name__icontains' is not valid"
"Unknown filter field: interface__device"
```

### Error Recovery Strategy

When you see these errors:

1. **Identify the invalid pattern**
   - Look for `__` in the filter
   - Check for Django lookups

2. **Determine the relationship**
   - What objects are involved?
   - What's the connection?

3. **Break into steps**
   - Query parent object first
   - Use its ID in next query
   - Combine results if needed

## Best Practices

### DO ✅

1. **Use Direct IDs When Possible**
   ```python
   {"device_id": 123}  # Fast and reliable
   ```

2. **Cache Frequently Used Objects**
   ```python
   # Cache sites for reuse
   sites = {}
   site = netbox_get_objects("dcim.site", {"name": "NYC"})
   sites['NYC'] = site['results'][0]['id']
   ```

3. **Validate Filters Before Execution**
   ```python
   def is_valid_filter(filter_dict):
       for key in filter_dict:
           if "__" in key:
               return False
       return True
   ```

4. **Use Search for Flexibility**
   ```python
   # More flexible than exact filters
   netbox_search_objects(query="production")
   ```

### DON'T ❌

1. **Don't Chain Relationships**
   ```python
   # This will always fail
   {"rack__site__region_id": 1}
   ```

2. **Don't Assume Django ORM Features**
   ```python
   # Not a Django QuerySet
   {"name__in": ["r1", "r2", "r3"]}
   ```

3. **Don't Concatenate Filters Dynamically**
   ```python
   # Build simple filters instead
   filter = {f"{field}__{lookup}": value}  # Bad
   filter = {field: value}  # Good
   ```

## Workaround Reference

| Need | Wrong Approach | Right Approach |
|------|----------------|----------------|
| Devices in site | `device__site_id` | Get site, then `site_id` |
| Partial match | `name__icontains` | Use `netbox_search_objects` |
| Multiple IDs | `id__in=[1,2,3]` | Multiple queries |
| Related objects | `interface__device` | Two-step query |
| Date filtering | `created__gte` | Get all, filter in code |
| Null checks | `field__isnull` | Get all, filter in code |

## Testing Filter Validity

Quick test to check if a filter will work:

```python
def will_filter_work(filter_dict):
    """
    Check if a filter will work with MCP.
    Returns (bool, reason).
    """
    for key, value in filter_dict.items():
        # Check for relationships
        if "__" in key:
            return False, f"Relationship traversal in '{key}'"

        # Check value types
        if not isinstance(value, (str, int, bool, float)):
            return False, f"Complex value type for '{key}'"

    return True, "Filter should work"

# Test examples
print(will_filter_work({"site_id": 5}))  # (True, "Filter should work")
print(will_filter_work({"name__icontains": "prod"}))  # (False, "Relationship traversal")
```

## Summary

The MCP server's filter constraints require a different approach than standard NetBox API usage:

1. **Think in steps**, not chains
2. **Use IDs**, not relationships
3. **Search** for patterns, don't filter
4. **Validate** before executing
5. **Cache** common objects

Understanding these constraints and their workarounds is essential for achieving high success rates with NetBox queries through MCP.