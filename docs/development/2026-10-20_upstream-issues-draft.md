# Draft upstream reports for netboxlabs/netbox-mcp-server (not yet filed)

Three defects found in the local agent, each verified live on NetBox 4.3.3 and carried as a
local patch in this repo (`docs/development/*.patch`). Drafted 2026-10-20; file against the
current upstream (v1.2.2 at the time of writing) after checking the issue tracker again.

## 1. `netbox_get_objects` drops `null` filter values (unfiltered result, HTTP 200)

**What happens.** `netbox_client.get()` passes the tool's `filters` dict straight to
`requests` as `params=`. `requests` omits any parameter whose value is `None`, so a call
such as `netbox_get_objects("dcim.device", filters={"tenant_id": None})` reaches NetBox with
no filter and returns every device. NetBox's own form for "no tenant assigned" is the
literal string `null` (`?tenant_id=null`).

**Reproduction (NetBox 4.3.3, 141 devices, 15 without a tenant).**
`{"tenant_id": null}` → count 141. `{"tenant_id": "null"}` → count 15.

**Impact.** An LLM client writing the natural JSON form gets the whole table as a successful
result; nothing in the response indicates the filter was dropped.

**Suggested fix.** Normalise before the request: `None` → `"null"`, `True`/`False` →
`"true"`/`"false"` (NetBox boolean filters ignore Python's `True`), lists element-wise. Patch:
one small function in `netbox_client.py` or `server.py`.

## 2. `netbox_get_changelogs` docstring teaches `action` values NetBox rejects

**What happens.** The tool description says `action: Filter by action type (created,
updated, deleted)` and the result description repeats it. NetBox's `ObjectChangeFilterSet`
accepts the bare verbs `create`, `update`, `delete`; the past-tense forms return HTTP 400
"Select a valid choice".

**Reproduction.** `?action=create` → 3,158 records. `?action=created` → 400.

**Impact.** An LLM client follows the tool description and burns a round trip per call.
In one 90-question benchmark run the model sent `created`, `updated` and `deleted` once
each. **Patch:** `docs/development/2026-10-19_netbox-mcp-server-changelog-action.patch`.

## 3. `netbox_search_objects` default types cannot see tenants, providers, manufacturers

**What happens.** `DEFAULT_SEARCH_TYPES` is devices, sites, IP addresses, interfaces,
racks, VLANs, circuits and VMs. A search for an organisation name, which is how most
questions start, returns eight empty lists with HTTP 200.

**Reproduction.** `netbox_search_objects("Halvorsen Logistics")` → every list empty;
`netbox_get_objects("tenancy.tenant", filters={"name__ic": "halvorsen"})` → the tenant.

**Impact.** In two 90-question benchmark runs 26 of 35 and 18 of 24 searches returned
nothing for this reason, and the client then guessed other object classes (manufacturer,
device type) for several calls. **Patch:**
`docs/development/2026-10-19_netbox-mcp-server-search-default-types.patch` (appends
`tenancy.tenant`, `circuits.provider`, `dcim.manufacturer`; test updated).

## Optional offer: schema-driven filter-name validation

The server's `validate_filters` is a suffix allow-list. NetBox silently ignores unknown
filter *names* (e.g. `device_role_id` on devices, where the filter is `role_id`), which no
suffix list can see. Checking names against `/api/schema/` per endpoint caught 27 distinct
wrong names across 1,237 recorded calls with zero false positives; pynetbox ships the same
idea as `strict_filters` (7.6.0). Happy to open a PR if wanted; the index build and the
exempt list (`fields`, `brief`, `q`, `limit`, `offset`, `ordering`, `cf_*`) are the only
moving parts.
