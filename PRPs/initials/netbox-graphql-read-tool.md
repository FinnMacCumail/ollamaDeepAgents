# FEATURE

Add a **read-only** NetBox GraphQL tool to the existing NetBox DeepAgents Query
System.

The tool lets the agent retrieve related NetBox objects in **one server-side
GraphQL query** instead of making several REST/MCP calls and joining the results
itself (the multi-hop pattern the current agent and its `netbox-mcp-filters`
skill work around today).

This feature **supplements** the existing four NetBox MCP read tools. It does not
replace or modify them, and it does not change the existing MCP tool wrapper,
`FilterValidator`, or filter-recovery middleware.

The implementation must remain **entirely read-only**. No CRUD, mutation,
subscription, custom-script execution, or any other state-changing capability is
permitted — this is a hard project constraint, not a default.

> Scope note for whoever runs `generate-prp` on this file: this is **PRP 1 of 2**.
> PRP 1 builds and secures the mechanism (validated by unit tests). PRP 2
> (`PRPs/initials/netbox-graphql-routing-and-evaluation.md`) teaches the agent
> when to use it and measures whether it helps (validated by the existing
> `netbox-benchmark-v3` eval harness). **Make no performance claims in PRP 1** —
> that is PRP 2's job.

# USER VALUE

As a NetBox operator running a self-hosted instance under a strict data-privacy
mandate, I want the agent to answer cross-domain infrastructure questions with a
single GraphQL request so that:

- multi-hop queries need fewer model/tool round trips;
- the relationship-filtering limits of the current MCP server (no multi-hop
  filters; the `netbox-mcp-filters` skill exists precisely to route around them)
  are avoided for nested reads;
- infrastructure data stays on the self-hosted NetBox instance (no third-party
  processing);
- simple single-object lookups keep using the existing MCP tools, which may stay
  cheaper.

GraphQL is a **complementary read path**, not a wholesale replacement for the MCP
tools. It has its own version-dependent filter grammar and its own failure modes
(see VERSION CONSIDERATIONS).

# REQUIRED CAPABILITIES

## 1. GraphQL query execution

Expose one DeepAgents/LangChain tool named `netbox_graphql`.

Inputs:
- `query`: a GraphQL query document (string)
- `variables`: optional JSON-compatible dict

Output (JSON-compatible):
- `data` on success;
- GraphQL `errors` array if the server returns partial data + errors;
- structured, **recoverable** error messages for transport, auth, validation,
  timeout, and response-size failures — matching the project's existing
  `TOOL_API_ERROR` / `TOOL_VALIDATION_ERROR` structured-error convention so the
  model can recover instead of crashing the LangGraph run.

The tool POSTs to the self-hosted NetBox GraphQL endpoint, constructing the URL
and `Authorization: Bearer` header **internally** from the existing
`NetBoxConfig` (`NETBOX_URL` + `NETBOX_TOKEN`). It must NOT expose arbitrary
URLs, HTTP methods, or headers to the model.

**Tool `description` field (required, and load-bearing).** Because PRP 1 ships
NO routing skill (that is PRP 2), the tool's own `description` is the only
in-context guidance the model gets. Author it deliberately: state that the tool
is **read-only**, that it is for **nested / cross-model relationship reads and
3+-hop joins** (not simple single-object lookups — those stay on the MCP tools),
and that the model should **call `netbox_graphql_schema` first** when unsure of
types/fields. This is part of building the tool, not PRP 2 scope — it is what
makes the tool usable when explicitly invoked before any skill exists.

## 2. Safety limits — PRIMARY safety surface

NetBox's GraphQL endpoint is **read-only by design** (query-only; there are no
mutation resolvers server-side). Therefore the real risk is **not** data
mutation — it is **expensive queries hammering the self-hosted Postgres DB**.
Treat query-cost control as the primary safety requirement:

- request timeout (configurable);
- maximum query-document size;
- maximum response size (reject/truncate oversized responses with a structured
  error);
- optional maximum query depth / complexity;
- maximum returned records where enforceable (pagination).

If NetBox enforces its own depth/alias/complexity limits, surface the server's
GraphQL error in a concise recoverable form rather than masking it.

## 3. Read-only enforcement — SECONDARY (defense-in-depth + clean errors)

Because the endpoint cannot mutate anyway, this layer is hygiene and
future-proofing, not the primary protection — but still implement it so illegal
operations are rejected **before** any HTTP call, with a clear message:

- accept `query` operations only;
- reject `mutation`, `subscription`, mixed query+mutation documents, and
  malformed documents.

**Parse the document and inspect every `OperationDefinition` — do NOT use
substring/regex matching.** Use `graphql-core` AST parsing (regex mutation
detection is unsafe and brittle).

## 4. Schema discovery

Let the model learn the schema exposed by the installed NetBox version + plugins,
without dumping the whole introspection result into context. Prefer, in order:

1. a separate `netbox_graphql_schema` tool returning a **compact, bounded,
   focused-by-type/field** description;
2. a constrained introspection mode on `netbox_graphql`.

Cache schema discovery **in-process**; allow focused lookup by type or field. Do
not repeatedly return the full introspection schema.

The PRP-generation research MUST verify whether the live instance permits
introspection (NetBox `GRAPHQL_ENABLED` / Strawberry introspection setting).

## 5. Secrets hygiene

- never log `NETBOX_TOKEN` or the `Authorization` header;
- never include the token in tool output or exception text.

## 6. Backwards compatibility

The existing MCP tools, `FilterValidator`, `FilterErrorRecoveryMiddleware`, the
`NetBoxToolWrapper`, and the agent query interface must keep working unchanged.

The `netbox_graphql` tool is a **standalone** LangChain tool appended to the
tool list alongside the wrapped MCP tools — it is NOT routed through
`NetBoxToolWrapper`, so it **automatically bypasses** `FilterValidator` (whose
Django→MCP suffix grammar does not apply to GraphQL). No special wiring is needed
to keep GraphQL out of `FilterValidator`; the standalone design achieves it.

# STANDALONE TESTABILITY (must function WITHOUT the PRP 2 routing skill)

PRP 1 must be independently verifiable before PRP 2 exists. In this app, tool
registration and skills are **separate systems**: tools are appended to the list
passed to `create_deep_agent(tools=..., ...)` in `netbox_agent.py` (~line 263+309),
while skills load via `SkillsMiddleware` from `src/skills/`. Registering
`netbox_graphql` therefore makes it **callable immediately**, with no skill.

Be aware of an existing bias that PRP 1 must NOT try to fix (that is PRP 2's job):
the system prompt at `netbox_agent.py:140` says *"ALWAYS check the
netbox-mcp-filters skill for filter guidance,"* and the tool-error message
(~line 396) points back to that MCP skill. So the agent will **not spontaneously
route** a natural-language query to GraphQL under PRP 1 — and that is expected,
not a defect. Do not add GraphQL routing to the system prompt or the
`netbox-mcp-filters` skill in PRP 1.

Because of that, PRP 1 is validated by **exercising the tool directly**, two ways:

1. **Direct integration call** — call the tool function (or its coroutine)
   directly against the live 4.4 instance, bypassing model tool-selection
   entirely. Proves transport/auth/read-only/schema-discovery/nested-query work.
2. **Interactive explicit invocation** — in `python -m src.main`, force the path,
   e.g. *"Use the netbox_graphql tool to answer: &lt;question&gt;. Call
   netbox_graphql_schema first if you need the types."* Confirms the model can
   drive the tool end-to-end when told to.

Reference query for the interactive check: re-run the real query captured in
trace `019f7bf4-4ad3-7ba1-8281-37d2ed6e0114` (previously answered via the MCP
path) through explicit GraphQL invocation, and eyeball correctness + the tool
trace. Do NOT compare tool-call count / wall time here — that apples-to-apples,
routing-driven comparison is PRP 2 on `netbox-benchmark-v3`.

# NETBOX VERSION CONSIDERATIONS

**This project's instance is NetBox 4.4** (the local demo data at `NETBOX_URL`,
typically `http://localhost:8000`). Confirm the exact running version as task 1,
but the expected implications are:

- GraphQL is read-only, served under `/graphql/` (build the endpoint from
  `NETBOX_URL`).
- NetBox 4.3 re-implemented GraphQL on **Strawberry Django** with a new advanced
  filtering syntax — **this applies to your 4.4 instance**.
- NetBox 4.5 changed ID/enum filters to lookup objects, e.g. `id: {exact: 123}`
  — **this does NOT apply to 4.4 yet**; do not adopt 4.5-only syntax in examples.
- Plugin-installed models can extend the schema.

Do not hardcode version assumptions where runtime introspection can answer them.

# EXISTING CODEBASE CONTEXT (read before implementing — all paths verified)

- `README.md`, `CLAUDE.md`, `AGENTS.md`
- `src/tools/netbox_tools.py` — `FilterValidator` (class, line ~32; Django→MCP
  suffix mapping), `NetBoxToolWrapper` (~128; wraps MCP tools with validation),
  `create_netbox_mcp_client()` (~252; builds `MultiServerMCPClient`),
  `NetBoxQueryHelper` (~342)
- `src/agents/netbox_agent.py` — how tools are assembled: MCP client →
  `NetBoxToolWrapper(...).get_tools()` → tools list handed to the agent. Note the
  `HarnessProfile` "Workaround B" (`base_system_prompt=""`,
  `excluded_middleware={"TodoListMiddleware"}`) — do not disturb it.
- `src/utils/config.py` — `NetBoxConfig` (class ~62), `load_netbox_config()`
  (~131). Source of URL + token. Add GraphQL-limit fields here ONLY if config is
  needed.
- `src/middleware/filter_recovery.py` — `FilterErrorRecoveryMiddleware` (the
  structured-error / recovery path GraphQL errors should be consistent with, but
  not routed through)
- `tests/conftest.py`, `tests/test_netbox_integration.py`, `tests/test_filters.py`
  (existing `FilterValidator` tests — must stay green)
- `src/skills/netbox-mcp-filters/SKILL.md` — the skill this tool complements
- `docs/development/2026-06-03_quickjs-code-interpreter-research.md` (why we are
  NOT doing Code Mode/PTC here) and `2026-06-14_deepagents-0.6-upgrade.md`

# EXISTING PATTERNS TO PRESERVE

- Async I/O throughout the tool layer.
- Structured tool errors returned to the model (not exceptions that crash the run).
- Relative imports within `src/`.
- `NetBoxConfig` / `load_netbox_config()` as the source of URL + token.
- Existing logging conventions (`src/utils/logging.py`).
- Explicit `./venv/bin/python` in docs/commands.
- No real credentials in tests, logs, or docs.
- Do NOT add an unconditional `load_config()` in `NetBoxDeepAgent` that would
  overwrite the model selection made by the eval harness (a known past bug).

# LIKELY FILE CHANGES

Create:
- `src/tools/netbox_graphql.py`
- `tests/test_netbox_graphql.py`

Modify:
- `src/agents/netbox_agent.py` (append the standalone tool to the tools list)
- `src/utils/config.py` (only if GraphQL-limit config is needed)
- `pyproject.toml` (add `graphql-core`; confirm the async HTTP client — the
  generate step must check whether `httpx` is already a direct dependency or only
  transitive via `langchain-mcp-adapters`, and add it explicitly if needed)
- `.env.example` (non-secret GraphQL safety settings only)
- `AGENTS.md`, `README.md`, `docs/development/README.md`

Do NOT put GraphQL validation into `FilterValidator`.

# WHAT THE GENERATED PRP SHOULD DECIDE (by inspecting the code)

- Confirm live NetBox version (expected 4.4), endpoint, and introspection state.
- Whether to use `graphql-core` for AST parsing (expected: yes).
- Exact tool-registration pattern in `netbox_agent.py` (standalone tool appended
  to `NetBoxToolWrapper.get_tools()` output; `StructuredTool.from_function()` vs
  `@tool` — mirror whatever the project already does for non-MCP tools).
- Whether schema discovery is a separate tool (recommended: yes).
- The exact async HTTP client to use (verify from `pyproject.toml`).
- Which concrete example queries actually work against the live 4.4 schema.

# EXAMPLES TO VALIDATE (derive from the LIVE 4.4 schema, not assumed)

1. Device → site → region.
2. Device → interfaces → connected cable/termination.
3. Circuit → provider → terminations.
4. IP address → assigned interface → device.
5. A filtered list with pagination.
6. A zero-result query.
7. A query returning partial data + GraphQL `errors`.

# TEST REQUIREMENTS (mock HTTP transport; do NOT mock parsing/validation/limits)

- **direct-call test:** invoke the tool function directly (mocked transport) and
  assert a nested query returns parsed `data` — proving the tool works with NO
  skill and NO model routing involved;
- successful query with variables;
- successful focused schema discovery;
- `Authorization` header constructed correctly, with and without trailing slash
  on `NETBOX_URL`;
- query accepted; mutation rejected **before any HTTP request**; subscription
  rejected; mixed query+mutation rejected; malformed document rejected;
- timeout → structured error; HTTP 401/403 → safe structured error; HTTP 400
  handled; GraphQL `errors` in response handled; invalid JSON handled;
  response-size limit enforced;
- token never appears in logs or returned errors;
- existing `FilterValidator` / MCP tool tests remain green.

# ACCEPTANCE CRITERIA

- `netbox_graphql` (and the schema-discovery tool) registered alongside the
  existing MCP tools.
- **Functions without the PRP 2 skill:** proven by (a) the direct integration
  call and (b) an interactive explicit-invocation run in `python -m src.main`
  (including the trace-`019f7bf4` reference query). Spontaneous routing is NOT
  required and NOT tested here.
- Executes a real nested query against the configured 4.4 instance.
- Mutation/subscription documents cannot reach NetBox.
- The model cannot choose an arbitrary URL or attach arbitrary headers.
- Query-cost limits (timeout/size/depth) enforced.
- Existing REST/MCP queries behave exactly as before.
- Unit tests cover the safety and error paths; lint + existing suite pass.
- A dated `docs/development/` note records the architectural decision.
- **No performance/latency claim is made** — deferred to PRP 2.

# DOCUMENTATION

- https://docs.netbox.dev/en/stable/integrations/graphql-api/
- https://docs.netbox.dev/en/stable/configuration/graphql-api/
- https://netboxlabs.com/docs/netbox/integrations/graphql-api/
- https://docs.netbox.dev/en/stable/release-notes/version-4.3/
- https://docs.netbox.dev/en/stable/release-notes/version-4.5/
- graphql-core: https://github.com/graphql-python/graphql-core

# OUT OF SCOPE

GraphQL mutations · REST writes · bulk CRUD · custom-script execution · IP
allocation · NetBox Branching · CodeInterpreterMiddleware/QuickJS adoption ·
removal of existing MCP tools · general-purpose HTTP-request tools · auto-
generating N model-specific tools · any performance claim (PRP 2).
