# PRP: Read-Only NetBox GraphQL Tool

**Feature file:** `PRPs/initials/netbox-graphql-read-tool.md`
**Generated:** 2026-07-20 (generate-prp workflow, incl. live NetBox introspection)
**Scope:** PRP **1 of 2**. Builds + secures the mechanism (unit-test validated).
Routing skill + eval A/B are PRP 2 (`netbox-graphql-routing-and-evaluation.md`).
**Confidence for one-pass implementation: 9/10** (see §Confidence).

---

## Goal

Add a **read-only** `netbox_graphql` tool (plus a `netbox_graphql_schema`
discovery tool) to the NetBox DeepAgent so it can retrieve nested/cross-model
NetBox objects in one server-side GraphQL request instead of multi-hop
REST/MCP decomposition. Supplements the four existing MCP read tools; changes
none of them. **No mutations, ever.** No performance claim (that is PRP 2).

## Why

- The current MCP tools cannot do multi-hop relationship filters — the whole
  `netbox-mcp-filters` skill + `FilterValidator` exist to route around that.
  GraphQL does cross-domain joins server-side in one call.
- Data stays on the self-hosted instance (privacy mandate).
- Simple single-object lookups keep using the (possibly cheaper) MCP tools.

## What (success criteria)

- [ ] `netbox_graphql` + `netbox_graphql_schema` registered alongside the MCP tools.
- [ ] Executes a real nested query against the live NetBox instance.
- [ ] Mutation/subscription/malformed documents are rejected **before any HTTP
      call**, returning a structured recoverable error string.
- [ ] The model cannot supply an arbitrary URL/method/headers; endpoint + auth
      are built internally from `NetBoxConfig`.
- [ ] Query-cost limits enforced (timeout, doc size, response size, depth).
- [ ] Token never appears in logs or returned errors.
- [ ] **Functions without the PRP-2 skill**, proven by (a) a direct tool-call
      integration test and (b) an interactive explicit-invocation run (incl.
      trace-`019f7bf4` reference query). Spontaneous routing is NOT tested here.
- [ ] Existing MCP/`FilterValidator` tests stay green; `ruff` + `mypy` + `pytest` pass.
- [ ] A dated `docs/development/` note records the decision.

---

## All Needed Context

### Live NetBox findings (verified 2026-07-20 against the configured instance)

These were confirmed by live `curl` against `NETBOX_URL` — treat as ground truth
and DO NOT re-derive from version guesses:

- **Endpoint:** `http://localhost:8000/graphql/` (build as `NetBoxConfig.url` +
  `/graphql/`; `.url` is already trailing-slash-normalized by its validator).
- **Auth scheme:** legacy 40-char hex token via `Authorization: Token <token>`
  (NOT `Bearer`, NOT an `nbt_` v2 token). Header value: `f"Token {config.token}"`.
- **Introspection: ENABLED.** `query { __schema { queryType { name } } }` →
  `{"data":{"__schema":{"queryType":{"name":"Query"}}}}`. Schema discovery can
  rely on live introspection.
- **Filter grammar (this is the 4.3/4.4 Strawberry line, NOT 4.5):**
  - ID/PK filters are **bare**: `device_list(filters: {id: 6})` → works.
  - `device_list(filters: {id: {exact: 6}})` → **FAILS** (`ID cannot represent a
    non-string and non-integer value`). So do NOT use the 4.5 `id: {exact: N}`
    form in examples.
  - String/other fields use **lookup objects**:
    `device_list(filters: {name: {exact: "dmi01-nashua-rtr01"}})` → works.
  - Verified nested traversal:
    `query { device_list(filters: {name: {exact: "dmi01-nashua-rtr01"}}) { name site { name region { name } } } }`
    → `{"data":{"device_list":[{"name":"dmi01-nashua-rtr01","site":{"name":"DM-Nashua","region":{"name":"New Hampshire"}}}]}}`
  - Root query fields are `<model>_list` (e.g. `device_list`, `site_list`,
    `ipaddress_list`, `vlan_list`, `cable_list`, `circuit_list`).
- Note: `/api/status/` returns HTTP 500 on this instance (a broken status
  endpoint, unrelated) — do NOT depend on it for a version string. The filter
  grammar above is what matters and is empirically fixed; the schema-discovery
  tool introspects the rest at runtime.

### Documentation

- NetBox GraphQL API: https://docs.netbox.dev/en/stable/integrations/graphql-api/
- NetBox GraphQL config: https://docs.netbox.dev/en/stable/configuration/graphql-api/
- 4.3 release notes (Strawberry rewrite): https://docs.netbox.dev/en/stable/release-notes/version-4.3/
- 4.5 release notes (`id: {exact:}` — for contrast; NOT this instance): https://docs.netbox.dev/en/stable/release-notes/version-4.5/
- graphql-core (AST parsing): https://github.com/graphql-python/graphql-core —
  `parse()` → `DocumentNode`; `OperationDefinitionNode.operation` is an
  `OperationType` enum (`QUERY`/`MUTATION`/`SUBSCRIPTION`); malformed docs raise
  `graphql.error.GraphQLSyntaxError`.
- httpx MockTransport (unit tests, no new dep): https://www.python-httpx.org/advanced/transports/

### Codebase patterns to mirror (real snippets)

**Tool construction — use `StructuredTool.from_function` with a coroutine**
(from `src/tools/netbox_tools.py:244`):
```python
return StructuredTool.from_function(
    coroutine=validated_func,          # async function
    name=tool.name,
    description=tool.description,
    args_schema=tool.args_schema,      # a pydantic model
)
```

**Structured errors are RETURNED as strings, never raised** (so langgraph
threads them back as a ToolMessage and the model can recover — see
`netbox_tools.py:193` and `:220`). Mirror this convention exactly:
```python
return (
    f"TOOL_VALIDATION_ERROR: {msg}\n"
    f"Suggestion: {suggestion}\n"
    f"Reissue this tool call with the corrected query."
)
# and for transport/HTTP/GraphQL-errors:
return f"TOOL_API_ERROR: {msg}\n..."
```
Use these SAME prefixes (`TOOL_VALIDATION_ERROR:` / `TOOL_API_ERROR:`) so the
model's already-trained recovery behaviour applies to GraphQL too.

**Config source** (`src/utils/config.py:62`): `NetBoxConfig` has `.url` (validated,
trailing-slash-stripped) and `.token`. Endpoint = `f"{cfg.url}/graphql/"`.

**Logging** (`src/utils/logging.py`): `logger = get_logger(__name__)`; structlog
style, `logger.warning("msg", key=value)`. NEVER log the token or auth header.

**Tool registration point** (`src/agents/netbox_agent.py:263` → `:309`):
```python
tools = await self.tool_wrapper.get_tools()          # line 263
# ADD HERE:  tools.extend(build_graphql_tools(self.netbox_config))
...
self.agent = create_deep_agent(model=model, tools=tools, ...)  # line 309
```
The GraphQL tools are **standalone** — NOT passed through `NetBoxToolWrapper`, so
they automatically bypass `FilterValidator` (whose Django→MCP suffix grammar is
irrelevant to GraphQL). No extra wiring needed to keep them separate.

### Dependencies (verified from pyproject.toml)

- **`httpx>=0.24.0` is ALREADY a direct dependency (line 20)** — use it; do not re-add.
- **`graphql-core` is NOT present — ADD it**: `"graphql-core>=3.2,<4"` in
  `[project].dependencies`.
- Test stack: `pytest`, `pytest-asyncio` in **`asyncio_mode = "auto"`** (async
  tests need no decorator), `unittest.mock`. Ruff line-length 100, py311, double
  quotes. mypy py311, `ignore_missing_imports=True`, untyped defs allowed.

### Known gotchas

- **Read-only is enforced by the SERVER already** (no mutation resolvers exist).
  Client-side mutation-rejection is defense-in-depth + clean errors, NOT the
  primary protection. The **primary safety surface is query cost** (depth /
  document size / response size / timeout) hitting self-hosted Postgres — weight
  the implementation accordingly.
- `parse()` on a malformed doc raises `GraphQLSyntaxError` — catch it and return
  `TOOL_VALIDATION_ERROR`, do not let it propagate.
- A document may contain multiple operations and/or fragments — inspect **every**
  `OperationDefinitionNode`; reject if ANY is `MUTATION`/`SUBSCRIPTION`.
- Do NOT use regex/substring to detect mutations (comments/strings/aliases fool
  it) — AST only.
- Do NOT add GraphQL routing to `NETBOX_SYSTEM_PROMPT` or `netbox-mcp-filters`
  (that is PRP 2). The system prompt at `netbox_agent.py:140` deliberately steers
  to the MCP skill; leave it. Under PRP 1 the agent will NOT spontaneously choose
  GraphQL — that is expected and NOT a defect.
- Do NOT add an unconditional `load_config()` anywhere in the agent build path
  (a past bug overwrote the eval harness's model choice — see the guard at
  `netbox_agent.py:242`).

---

## Implementation Blueprint

### Data model (args schema)

```python
from pydantic import BaseModel, Field

class NetBoxGraphQLInput(BaseModel):
    query: str = Field(..., description="A read-only GraphQL query document.")
    variables: dict | None = Field(default=None, description="Optional GraphQL variables.")

class NetBoxGraphQLSchemaInput(BaseModel):
    type_name: str | None = Field(
        default=None,
        description="A GraphQL type to describe (fields + types). Omit to list root query fields.",
    )
```

### Pseudocode — `netbox_graphql` execution

```
async def netbox_graphql(query, variables=None):
    # 1. size guard (pre-parse)
    if len(query) > MAX_QUERY_CHARS: return TOOL_VALIDATION_ERROR
    # 2. AST parse (catch GraphQLSyntaxError -> TOOL_VALIDATION_ERROR)
    doc = parse(query)
    # 3. read-only enforcement: every OperationDefinitionNode.operation must be QUERY
    for defn in doc.definitions:
        if isinstance(defn, OperationDefinitionNode) and defn.operation != OperationType.QUERY:
            return TOOL_VALIDATION_ERROR("only read-only 'query' operations are permitted")
    # 4. optional depth guard (walk selection sets; reject > MAX_DEPTH)
    # 5. POST via httpx.AsyncClient(timeout=TIMEOUT):
    #      url = f"{cfg.url}/graphql/", headers={"Authorization": f"Token {cfg.token}"}
    #      json = {"query": query, "variables": variables or {}}
    #    wrap transport/timeout/HTTP-status errors -> TOOL_API_ERROR (never leak token)
    # 6. response-size guard on raw body -> TOOL_API_ERROR if too big
    # 7. parse JSON; return {"data": ..., "errors": [...]} (pass GraphQL errors through)
```

### Pseudocode — `netbox_graphql_schema` (cached, bounded)

```
_schema_cache = None
async def netbox_graphql_schema(type_name=None):
    global _schema_cache
    if _schema_cache is None:
        introspect via graphql-core get_introspection_query(); POST; build_client_schema
        _schema_cache = built schema
    if type_name is None: return sorted root query field names (bounded)
    else: return that type's fields + field types (bounded); TOOL_VALIDATION_ERROR if unknown
```

### Factory

```python
def build_graphql_tools(cfg: NetBoxConfig) -> list[StructuredTool]:
    # close over cfg; return [execute_tool, schema_tool] built via
    # StructuredTool.from_function(coroutine=..., name=..., description=..., args_schema=...)
```

**Tool `description` (load-bearing — only in-context guidance pre-PRP-2):** state
read-only; use for nested/cross-model reads & 3+-hop joins (not simple lookups —
those stay on MCP tools); call `netbox_graphql_schema` first if unsure of
types/fields; note ID filters are bare (`id: 6`) and string filters use
`{exact: "..."}`.

### Config (only if needed)

Add optional limit fields to `NetBoxConfig` OR keep module-level constants in
`netbox_graphql.py` with `.env`-overridable defaults:
`NETBOX_GQL_TIMEOUT` (default 30s), `NETBOX_GQL_MAX_QUERY_CHARS` (default 8000),
`NETBOX_GQL_MAX_RESPONSE_CHARS` (default 200_000), `NETBOX_GQL_MAX_DEPTH`
(default 12). Non-secret → add to `.env.example`.

### Task order (implement in this sequence)

1. Add `graphql-core>=3.2,<4` to `pyproject.toml`; `uv sync` (or pip install -e).
2. Create `src/tools/netbox_graphql.py`: input models, constants, AST read-only
   validation, depth guard, async httpx client, `netbox_graphql` fn,
   `netbox_graphql_schema` fn (cached), `build_graphql_tools(cfg)` factory.
3. Wire into `src/agents/netbox_agent.py`: import + `tools.extend(build_graphql_tools(self.netbox_config))`
   immediately after line 263 (before `create_deep_agent`).
4. `.env.example`: add the non-secret GQL limit settings.
5. `tests/test_netbox_graphql.py`: unit tests using `httpx.MockTransport`
   (mock HTTP only — do NOT mock parsing/validation/limits).
6. Update `AGENTS.md`, `README.md`, `docs/development/README.md`; add a dated
   `docs/development/2026-07-20_netbox-graphql-read-tool.md` decision note.
7. Run validation loop (below) until green.
8. Manual: direct-call integration + interactive explicit-invocation (trace-019f7bf4).

---

## Validation Loop

### Gate 1 — syntax/style/types (must pass)
```bash
cd /home/ola/dev/netboxdev/ollamaDeepAgents
./venv/bin/ruff check --fix src/tools/netbox_graphql.py tests/test_netbox_graphql.py
./venv/bin/mypy src/tools/netbox_graphql.py
```

### Gate 2 — unit tests (mock HTTP via httpx.MockTransport; real parsing/validation)
```bash
./venv/bin/pytest tests/test_netbox_graphql.py -v
# regression: existing suites stay green
./venv/bin/pytest tests/test_filters.py tests/test_netbox_integration.py -v
```
Required cases: direct-call nested query returns parsed `data`; query-with-variables;
focused schema discovery; `Authorization: Token` header built correctly (with and
without trailing slash on url); **mutation rejected before any HTTP request**;
subscription rejected; mixed query+mutation rejected; malformed doc rejected
(`GraphQLSyntaxError`); timeout → `TOOL_API_ERROR`; HTTP 401/403/400 → safe
structured error; GraphQL `errors` passed through; invalid-JSON handled;
response-size limit enforced; **token never in logs/returned errors**.

### Gate 3 — manual, routing-independent (verifies standalone function)
```bash
# (a) direct integration call against LIVE NetBox (bypasses model choice entirely)
./venv/bin/python -c "import asyncio; from src.utils.config import load_netbox_config; \
from src.tools.netbox_graphql import build_graphql_tools; \
t={x.name:x for x in build_graphql_tools(load_netbox_config())}; \
print(asyncio.run(t['netbox_graphql'].arun({'query':'query { device_list(filters:{name:{exact:\"dmi01-nashua-rtr01\"}}){ name site { name region { name } } } }'})))"

# (b) interactive explicit invocation — re-run the trace-019f7bf4 question via GraphQL
./venv/bin/python -m src.main
#   > Use the netbox_graphql tool to answer: <trace-019f7bf4 question>.
#     Call netbox_graphql_schema first if you need the types.
```
Do NOT compare tool-count/wall-time here — that is PRP 2.

---

## Anti-patterns / Out of scope

Mutations · REST writes · bulk CRUD · custom-script execution · IP allocation ·
Branching · QuickJS/Code Mode · removing MCP tools · general HTTP-request tools ·
auto-generating N per-model tools · routing changes to system prompt/skill ·
ANY performance claim. Do NOT enforce read-only with regex. Do NOT log the token.

---

## Confidence: 9/10

High because: the live schema/auth/filter-grammar are empirically verified (not
assumed); the tool-construction, structured-error, config, and registration
patterns are copied from real code; `httpx` is already a dep and `graphql-core`
is a single well-understood add; the AST approach is standard. The −1: the exact
bounded shape of `netbox_graphql_schema` output and the depth-guard traversal are
the only genuinely new design surface, and introspection-payload size may need a
truncation pass — both are contained to one file and covered by unit tests.
