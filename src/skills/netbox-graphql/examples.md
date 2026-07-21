# NetBox GraphQL — Worked Patterns

These are **patterns**, not a schema. Every one adapts to ANY object type: swap
the model and, if you are unsure of its fields, call
`netbox_graphql_schema("<Model>Type")` first. The domains below (devices, IPs,
power, circuits) are illustrations — the same shapes work for wireless, tenancy,
VMs, plugin objects, anything on the instance.

All queries are live-verified against NetBox 4.4 (Strawberry). Grammar recap:
root field = `snake_case(model)_list`; IDs bare (`{id: 6}`); strings as lookup
objects (`{name: {exact: …}}` / `{i_contains: …}` / `{in_list: […]}`); nested
relationship filters work; select only needed fields.

---

## Pattern 1 — nested traversal (A → B → C in one request)

*Intent:* one object plus fields from related models. Replace `device_list` /
`site`/`region` with any type + relations (call `netbox_graphql_schema` if unsure).

```graphql
query {
  device_list(filters: {name: {exact: "dmi01-nashua-rtr01"}}) {
    name
    site { name region { name } }
  }
}
```

## Pattern 2 — multi-value + cross-model filter (the MCP-can't case)

*Intent:* list children of several parents at once, filtered by a parent field
the MCP tools cannot traverse. `in_list` takes any list of values.

```graphql
query {
  device_list(filters: {site: {name: {in_list: ["DM-Nashua", "DM-Akron", "DM-Scranton"]}}}) {
    name
    site { name }
    device_type { model }
  }
}
```

## Pattern 3 — aggregation done RIGHT (fetch → count client-side → verify membership)

*Intent:* "utilization / how many". GraphQL returns rows, not computed counts.
Fetch the rows, count them yourself, and confirm each belongs to the scope you
were asked about. NEVER report a global count as if it were per-scope.

```graphql
# Prefixes for a site (discover the site's prefixes, then look inside each).
query {
  prefix_list(filters: {scope_type: "dcim.site", scope_id: 7}) {
    prefix
    vlan { vid name }
    status
  }
}
```
Then, to answer "IP allocation %": for each prefix, fetch its IPs
(`ip_address_list(filters: {parent: "10.112.149.0/24"})`), count them, divide by
capacity. **Trap:** a bare `ip_address_list` returns ALL IPs on the instance —
here all 180 live in `172.16.0.0/24`, none in the site's `10.112.x` prefixes, so
that site's utilization is **0%**. Confirm the `parent` prefix before attributing
any IP to a site.

## Pattern 4 — out-of-benchmark domain: circuits → provider → terminations

*Intent:* proves the grammar is domain-agnostic — nothing here is device/site
specific. (Discover fields first: `netbox_graphql_schema("CircuitType")`.)

```graphql
query {
  circuit_list {
    cid
    provider { name }
    type { name }
    terminations { term_side }
  }
}
```
*Verified:* returns e.g. `cid 1002840283 / provider CenturyLink / term_side Z`.

## Pattern 5 — out-of-benchmark domain: power feed → panel → rack

*Intent:* a domain not in the benchmark at all. Root field is `power_feed_list`
(snake_case of `PowerFeed`); discover with `netbox_graphql_schema("PowerFeedType")`
if unsure of the relations.

```graphql
query {
  power_feed_list(filters: {rack: {name: {exact: "IDF128"}}}) {
    name
    power_panel { name }
    rack { name }
  }
}
```
*Verified:* valid query (returns `[]` where a rack has no feeds — an empty result
is a valid answer, not an error).

---

## Reverse-filter gotcha (generalizes)

Some `<X>Filter` types don't expose a nested filter for a related model. E.g.
`ip_address_list(filters: {device: {...}})` FAILS — `IPAddressFilter` has no
`device` field. When a "filter X by related Y" fails:
1. filter the OTHER direction (query Y, read its X-typed fields), or
2. use a `parent` / `scope` filter (IPs → `parent` prefix; prefixes →
   `scope_id`/`scope_type`), or
3. `netbox_graphql_schema("<X>Filter")` to see which filters actually exist.

## Read-only

`netbox_graphql` rejects mutations/subscriptions before any request. If asked to
create/update/delete/allocate, refuse — outside this agent's scope; there is no
GraphQL write path here.
