# NetBox GraphQL Read Tool — Implementation Note

**Date:** 2026-07-20
**Status:** ✅ Completed (PRP 1 of 2)
**PRP:** `PRPs/netbox-graphql-read-tool.md` (generated from
`PRPs/initials/netbox-graphql-read-tool.md`)
**Related:** PRP 2 (`PRPs/initials/netbox-graphql-routing-and-evaluation.md`) —
routing skill + eval A/B, not yet started.

## Problem

The four MCP read tools cannot express multi-hop relationship filters — the
entire `netbox-mcp-filters` skill + `FilterValidator` exist to route around that
by decomposing cross-domain questions into sequential two-step lookups. That is
slow (multiple model turns) and brittle.

## Solution

Added two **standalone, read-only** tools that hit NetBox's GraphQL endpoint,
letting the agent retrieve nested/cross-model data in one server-side request:

- `netbox_graphql(query, variables?)` — execute one read-only GraphQL query.
- `netbox_graphql_schema(type_name?)` — introspect the live schema (root query
  fields, or one type's fields), cached in-process.

Files: `src/tools/netbox_graphql.py` (new), `tests/test_netbox_graphql.py` (new,
23 tests), wired into `src/agents/netbox_agent.py` via
`tools.extend(build_graphql_tools(self.netbox_config))` after the MCP tools.
Dependency added: `graphql-core>=3.2,<4`.

## Design decisions

- **Complementary, not a replacement.** GraphQL is for nested / 3+-hop reads;
  simple single-object lookups stay on the (possibly cheaper) MCP tools. The
  agent is NOT yet steered to choose it — that (and the measurement) is PRP 2.
  Under PRP 1 the tool is callable and works when explicitly invoked, but the
  system prompt still points at the MCP skill, so spontaneous routing is not
  expected (same "won't-use-it-unless-told" dynamic seen in the QuickJS spike).
- **Standalone → bypasses `FilterValidator` by design.** The GraphQL tools are
  NOT passed through `NetBoxToolWrapper`; GraphQL has its own filter grammar, so
  the Django→MCP suffix validator must not touch it. No special wiring needed.
- **Read-only enforcement is defense-in-depth, not the primary risk.** NetBox's
  GraphQL endpoint has no mutation resolvers server-side, so mutation-blocking
  cannot actually protect data — it is hygiene + clean errors. The real safety
  surface is **query cost**, so the implementation weights depth / document-size
  / response-size / timeout limits (env-overridable) as primary. Mutations,
  subscriptions, mixed docs, and malformed documents are still rejected **before
  any HTTP call** via `graphql-core` AST inspection (never regex).
- **Structured errors as strings.** Mirrors `netbox_tools.py`: failures return a
  `TOOL_VALIDATION_ERROR:` / `TOOL_API_ERROR:` string (never raise), so the model
  recovers on its next turn. Same prefixes → the model's trained recovery
  behaviour transfers.
- **Secrets hygiene.** Endpoint + `Authorization: Token <token>` header are built
  internally from `NetBoxConfig`; the token is redacted from any returned/logged
  message and the model cannot supply a URL/method/headers.

## Live-verified facts (2026-07-20, against the configured instance)

Confirmed by direct `curl` + the tool's own direct-call integration check:

- endpoint `http://localhost:8000/graphql/`; auth `Authorization: Token <40-hex>`
  (legacy token, **not** `Bearer`, not an `nbt_` v2 token).
- introspection **enabled**.
- filter grammar is the **4.3/4.4 Strawberry line, not 4.5**: ID filters are bare
  (`filters: {id: 6}`); `filters: {id: {exact: 6}}` FAILS; string fields use
  lookup objects (`filters: {name: {exact: "..."}}`). Root query fields are
  `<model>_list`; the device type is `DeviceType` (discover via the schema tool).
- verified end-to-end: `device_list(filters: {name: {exact: "dmi01-nashua-rtr01"}})
  { name site { name region { name } } }` → DM-Nashua / New Hampshire.

## Validation

- Gate 1: `ruff` clean on the new files; `mypy` clean on `netbox_graphql.py`.
  (Pre-existing `E402` in `netbox_agent.py` and a `mypy` note in `logging.py` are
  unrelated and predate this change.)
- Gate 2: 23/23 new unit tests pass (mock HTTP via `httpx.MockTransport`; real
  parsing/validation/limits). Regression suites show the **same** 7 pre-existing
  failures with and without this change (verified by stashing) — regression-neutral.
- Gate 3: live direct-call integration + mutation-rejection confirmed against the
  real instance (above).

## Not done here (PRP 2)

Routing skill (`src/skills/netbox-graphql/`), a one-line pointer from
`netbox-mcp-filters`, extending `evaluators.py` with wall-time / token /
GraphQL-duration / error-rate axes, and the GraphQL-on-vs-MCP-only A/B on the
existing `netbox-benchmark-v3` harness. **No performance claim is made until then.**
