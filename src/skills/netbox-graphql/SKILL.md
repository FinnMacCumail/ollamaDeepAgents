---
name: netbox-graphql
description: When to use the read-only netbox_graphql tool instead of the MCP tools, and how to write valid NetBox GraphQL for ANY object type. Load this whenever a query spans two or more NetBox models, needs 3+ ID-joined lookups, or asks for nested/related data (e.g. "devices at these sites with their region", "IPs on interfaces of device X", "circuits per provider and where they terminate"). Teaches grammar + runtime schema discovery, not a fixed schema.
version: 1.0.0
tags: [netbox, graphql, routing, cross-domain, nested, read-only]
priority: high
---

# NetBox GraphQL — Routing & Grammar

`netbox_graphql` runs ONE read-only GraphQL query and returns nested/related
objects in a single server-side request — the cross-model join the MCP two-step
pattern cannot do. It is a **complementary** path, not a replacement: simple
single-object lookups and fuzzy searches stay on the MCP tools.

**This skill teaches grammar + runtime discovery — NOT a fixed list of objects.**
NetBox has 100+ object types plus plugins; you will meet types not shown here.
You handle ANY of them the same way: introspect the type, then apply the
universal grammar below. Do not assume this skill (or the benchmark) enumerates
the schema.

## ROUTING — which tool?

**First, count the anchor objects — this is the deciding test, NOT how many models
the answer touches.** If the query names exactly ONE specific object (by name or ID) and asks
for that object's own fields plus its directly-attached related summary (its site, rack, tenant,
role, status, assigned IPs), it is a **single-object lookup → MCP `netbox_get_objects`** —
**even when the answer spans several models.** Listing a device's site + IPs + tenant is still
ONE object; resolve the object, then read its related IDs in a second MCP call. Reach for
`netbox_graphql` **only** when the query is anchored on a SET/class of objects that must be
filtered or joined across models, or needs 3+ ID-joins whose intermediate objects aren't known
up front.

| Query shape | Tool |
|---|---|
| ONE named object + its own attributes / related summary (**even across models**) | MCP `netbox_get_objects` |
| "Show device X's location, IPs, and tenant" (ONE named object) | MCP `netbox_get_objects` — **NOT** GraphQL |
| Partial / fuzzy name search | MCP `netbox_search_objects` |
| A SET of objects filtered/joined across models (A → B → C for *many* items) | **`netbox_graphql`** |
| 3+ sequential reads joined by IDs (intermediates unknown up front) | **`netbox_graphql`** |
| An unfamiliar type or field | **`netbox_graphql_schema(<Type>)` first**, then `netbox_graphql` |
| Counts / percentages / "utilization" over a set | `netbox_graphql` to fetch, then compute **client-side** (see AGGREGATIONS) |
| Create / update / delete / allocate | Refuse — this agent and this tool are READ-ONLY |

GraphQL is not the default. If a single `netbox_get_objects` call (or a two-step MCP lookup)
answers it, use that — it is cheaper.

## THE GENERALIZATION RULE (how you handle ANY object type)

**For any type or field you are not 100% sure of, call
`netbox_graphql_schema` FIRST — never guess.**

- `netbox_graphql_schema()` (no arg) → lists the root query fields.
- `netbox_graphql_schema("PowerFeedType")` → lists that type's fields + their types.

This reads the LIVE schema (including installed plugins), so it works for power,
circuits, wireless, tenancy, VMs, custom objects — anything on the instance, not
just the examples in this skill. Discover → write → execute.

## UNIVERSAL GRAMMAR (identical for every NetBox type — NetBox 4.4 / Strawberry)

- **Root query fields are the snake_case model name + `_list`**: `device_list`,
  `site_list`, `vlan_list`, `prefix_list`, `ip_address_list` (IPAddress →
  `ip_address_list`), `cable_list`, `circuit_list`, `power_feed_list` (PowerFeed
  → `power_feed_list`), `wireless_lan_list` (WirelessLAN → `wireless_lan_list`),
  `virtual_machine_list`, … If unsure of the exact name, call
  `netbox_graphql_schema()` with no argument to list every root field.
- **Types are `<Model>Type`**: `DeviceType`, `SiteType`, `CircuitType`,
  `PowerFeedType`. Pass these to `netbox_graphql_schema`.
- **ID / PK filters are BARE integers** — `{id: 6}` or `{id: [6, 7, 8]}`.
  NEVER `{id: {exact: 6}}` (that is 4.5 syntax and FAILS on this instance).
- **String / other scalar filters use lookup objects**:
  - `{name: {exact: "dmi01-nashua-rtr01"}}`
  - `{name: {i_contains: "switch"}}`  (case-insensitive contains)
  - `{name: {in_list: ["DM-Nashua", "DM-Akron"]}}`  (multi-value)
- **Nested relationship filters WORK** (the whole reason to use GraphQL — MCP
  cannot): `device_list(filters: {site: {name: {in_list: ["DM-Nashua"]}}})`.
- **Select only the fields you need** (keeps payloads small; results do not
  re-enter the model context the way MCP JSON does).
- **Status/role/type values are lowercase slugs** (`"active"`, not `"Active"`).

## GOTCHAS — as PATTERNS (apply beyond the examples)

1. **A filter that reads "forward" may not exist "reverse."** Some `<X>Filter`
   types do not expose a nested filter for a related model. Verified example:
   `IPAddressFilter` has **no `device` field**, so
   `ip_address_list(filters: {device: {...}})` FAILS. General fix: filter the
   OTHER direction, use a `parent`/`scope`-style filter, or
   `netbox_graphql_schema("<X>Filter")`/`("<X>Type")` to see what filters exist.
   (For IPs specifically: scope by `parent` prefix, or query interfaces.)
2. **Omit optional keys — never pass `{field: undefined}`** (Pydantic rejects it).
3. **Aggregations are client-side.** GraphQL returns lists, not computed counts/
   percentages. Fetch the rows, then count/compute yourself — and VERIFY
   membership. Do NOT report a global count as if it were scoped. (Trap: NetBox's
   180 IP addresses all live in `172.16.0.0/24`; none are in the DM sites'
   `10.112.x` prefixes — so per-site IP utilization there is **0%**, not a share
   of 180. Always confirm which parent an object belongs to before attributing.)
4. **Read-only.** `netbox_graphql` rejects mutations/subscriptions before any
   request. If asked to change data, refuse — outside this agent's scope.

## WORKFLOW

1. **Route.** Nested / cross-model / 3+-hop → GraphQL. Else → MCP.
2. **Discover** (if any type/field is unfamiliar): `netbox_graphql_schema("<Model>Type")`.
3. **Write** one query using the universal grammar; select only needed fields.
4. **Execute** `netbox_graphql`. On a GraphQL error, read it — it usually names
   the bad field; re-introspect and fix, don't guess repeatedly.
5. **Aggregate client-side** if counts/percentages are asked for; verify membership.

See `examples.md` for worked patterns (each adaptable to any `<Model>Type` via
`netbox_graphql_schema`). The examples are illustrations of the grammar, not the
boundary of what you can query.
