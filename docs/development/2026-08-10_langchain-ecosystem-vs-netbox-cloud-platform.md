# LangChain Ecosystem vs. the NetBox Cloud Platform MCP — What's Reproducible Self-Hosted

**Date:** 2026-08-10
**Status:** ✅ Research complete — recommendations + one actionable upgrade task (§8)
**Purpose:** Survey the current (Aug 2026) LangChain / LangGraph / DeepAgents / LangSmith ecosystem and map it against the capabilities of NetBox Labs' **Cloud-only "Platform MCP Server"** — to decide which of those query-processing advantages can be reproduced on this self-hosted, read-only stack, and how.
**Related:** `2026-06-03_langsmith-evaluation-research.md` (prior ecosystem survey), `2026-06-03_quickjs-code-interpreter-research.md` (Code Mode / PTC — this doc reconfirms that deferral), `2026-07-20_netbox-graphql-read-tool.md` (the GraphQL read path this doc validates as the right lever), `PRPs/initials/netbox-graphql-routing-and-evaluation.md` (the model-handoff routing this doc informs).
**Method:** five parallel deep-research agents (Code Mode, large-tool-set management, routing/handoff, DeepAgents-current + blog, NL→structured-query), each primary-source-cited. This doc synthesises them.

---

## TL;DR

The NetBox Cloud Platform MCP's edge comes almost entirely from **tool breadth (~100 tools) + "Code Mode"** — and both only pay off *at that breadth*. This read-only, single-source, 4-tool stack does not need to reproduce Code Mode: **the read-only GraphQL tool already shipped (2026-07-20) is the correct, cheaper answer to the actual round-trip problem.** The pieces genuinely worth borrowing are all **open-source and self-hostable**:

- **Subagents** — for tool scoping *and* the planned local→cloud **model-handoff routing** (the Aug-5 LangChain "SRE agent" blog is almost the exact architecture).
- **DeepAgents Skills** — the knowledge layer; already in use (`netbox-mcp-filters`, `netbox-graphql`).
- **`RubricMiddleware`** — the open-source equivalent of the Cloud's "structured self-correction."
- **Server-side tool generation** from NetBox's OpenAPI/GraphQL — the only way to reproduce "dynamic model discovery" (LangChain can't add/remove tools mid-run).

Every *convenience* product — **Managed Deep Agents, LLM Gateway, Context Hub, hosted LangSmith** — is cloud-only and fails the project's strict data-privacy mandate. Self-hosted eval/observability parity comes from the MIT `openevals` / `agentevals` packages + OpenTelemetry export.

**One actionable task falls out of this research: upgrade `deepagents` 0.6.10 → 0.7.5 (§8).**

---

## Context

The [Platform MCP Server](https://netboxlabs.com/docs/cloud/platform-mcp-server/) (NetBox Cloud only; self-hosted Enterprise support "planned for later this year") advertises: ~100 tools (reads/writes/bulk/IPAM/cable-trace/GraphQL/config-render/scripts), a sandboxed **Code Mode** ("75%+ fewer tool round-trips", "85% less context"), **dynamic model discovery** (indexes every object type incl. plugins at startup), **tier-enforced tool registration**, an **Agent Skills** knowledge layer, and **structured self-correcting errors**.

This stack is the community counterpart: DeepAgents 0.6.10, a self-hosted NetBox MCP server with **4 read tools** (`netbox_get_objects`, `netbox_get_object_by_id`, `netbox_search_objects`, `netbox_get_changelogs`), a new **read-only GraphQL tool** + `netbox_graphql_schema` introspection, a routing skill, and a model-matrix eval with a reference-grounded correctness judge. Question: which Cloud advantages are reproducible here, and with what?

---

## 1. Capability-by-capability mapping

| Cloud Platform feature | Closest self-hostable LangChain reproduction | Verdict |
|---|---|---|
| **Code Mode** (sandboxed executor) | `langchain-quickjs` 0.3.5 `CodeInterpreterMiddleware` + PTC allowlist | **Skip** — see §2 |
| The round-trip problem Code Mode solves | **Read-only GraphQL tool (already shipped)** | **Done** — GraphQL is a server-side join |
| **~100 tools without context bloat** | `LLMToolSelectorMiddleware` · DeepAgents **subagent partitioning** · `langgraph-bigtool` (tool-RAG, 500+) | Available, native — §3 |
| **Dynamic model discovery** (all object types + plugins) | Generate MCP tools from NetBox **OpenAPI/GraphQL at server startup** (`openapi2tools`, `OpenAPIToolkit`, `BaseGraphQLTool`) | **Server-side only** — LangChain can't add/remove tools mid-run (open issue #33808) — §3 |
| **Tier-enforced tool registration** | Filter the tool list per role **at agent-build time**; rebuild per session | Static-per-session idiom — §3 |
| **Structured self-correcting errors** | **`RubricMiddleware`** (OSS) · structured errors emitted by *our* MCP server, relayed via `ToolMessage(status="error")` · `ToolArgValidationMiddleware` · `ToolRetryMiddleware` | High value — §4 |
| **Agent Skills knowledge layer** | **DeepAgents Skills** (OSS, `agentskills.io` spec) — already in use | Already have it — §4 |
| **NL → correct structured query** (the core value) | **Curated parameterized GraphQL operations** · self-query *filter compiler* · schema-RAG · tool-arg validation | Highest correctness leverage — §5 |
| **Model routing / handoff** (our next step) | **DeepAgents subagent `task()`** — the Aug-5 SRE-agent template | Validated; LLM Gateway is the *wrong* layer — §6 |

---

## 2. Code Mode — reconfirmed "skip" (reinforces the 2026-06-03 QuickJS deferral)

`langchain-quickjs` is now **0.3.5** (2026-07-29, up from 0.2.0 in June) but the tradeoff has **not** shifted:

- Still **QuickJS/JavaScript only** — no Python-sandbox middleware variant; generating JS to orchestrate a Python/GraphQL NetBox stack is added impedance.
- **No first-class MCP→code bridge.** MCP `BaseTool` instances *can* be added to the `ptc=[...]` allowlist (as our earlier spike confirmed), but a native "MCP tools as importable typed functions" utility is an unshipped feature request (langchain #34130).
- **Anthropic's own τ²-bench** (1–2 sequential calls/turn — our exact workload shape) shows PTC "left scores unchanged and cost roughly 8% more. Sequential single-call workflows do not benefit." This matches our June spike (+13.7% latency, model never chose `eval`).
- The Cloud's **75%/85%** figures are for its **~100-tool catalog + batch tasks**; savings begin only at ~10–49 tool definitions and with parallel fan-out or large filterable results — none of which a 4-tool dependency-chained read workload has.

**Conclusion:** the round-trip problem is real but the fix is the **GraphQL tool** (already shipped), not code execution. NetBox's GraphQL API is explicitly "a special-purpose read-only API" that "offload[s] to the server the work of stitching together various related objects" — a single nested query collapses tenant→sites→VLANs→prefixes at the API layer with no sandbox, latency tax, or JS-generation risk. If *context* (not round-trips) ever becomes the constraint, the LangChain-native lever is **progressive tool disclosure middleware**, still not code mode. (`langchain-sandbox` is deprecated/archived; the E2B/Modal/Runloop partner sandboxes are for *acting on an OS*, off-purpose for read-only querying.)

---

## 3. Tool breadth & "dynamic discovery"

If the tool surface ever grows toward the Cloud's ~100:

- **`LLMToolSelectorMiddleware`** (v1 core, native to DeepAgents) — a cheap LLM pre-selects the relevant tools per turn: `LLMToolSelectorMiddleware(max_tools=…, always_include=[…])`. Guard against the known hallucinated-tool-name bug (langchain #33651) with `max_tools` + validation.
- **DeepAgents subagent partitioning** — split tools into domain subagents (`dcim`, `ipam`, `circuits`); each `SubAgent`'s `tools=[...]` **overrides inherited tools entirely**, so the main agent only ever sees the `task()` tool + subagent descriptions. This is context quarantine, and the most idiomatic fit for this stack.
- **`langgraph-bigtool`** — embeddings-based tool-RAG over a `Store` (InMemory/Postgres); reserve for 500+ tools (it ships its *own* graph, not a DeepAgents middleware).

**Reproducing "dynamic model discovery":** LangChain **cannot add/remove tools after agent creation** (open issue #33808 — middleware can only *filter* pre-registered tools). So discovery must happen **server-side at MCP startup** — introspect the NetBox OpenAPI spec / GraphQL schema (incl. plugins) and register per-object read tools (`openapi2tools`, `langchain_community` `OpenAPIToolkit`, `BaseGraphQLTool`). Apply per-role/tier filtering *there* to reproduce "tier-enforced registration," and rebuild the agent per session/role. This is the key architectural difference vs. the Cloud product, which does it server-side and continuously.

---

## 4. Self-correction & the knowledge layer

**Structured self-correction is not something LangChain synthesises for you** — it relays whatever the tool returns. Reproduce the Cloud's claim with:

- **`RubricMiddleware`** (OSS, Jun 2026; `docs/.../deepagents/rubric`) — define a rubric ("cites device IDs; no writes attempted; answer grounded in returned objects; IP figures verified against prefix membership"); a grader subagent's per-criterion feedback is injected back and the agent re-runs until it passes. **This is the free equivalent of "structured self-correction"** and directly attacks the hallucination class the correctness judge catches (e.g. the 7.7%-vs-0% IP-utilisation error).
- **Structured errors emitted by our MCP server** (valid field names / allowed filters / the offending value), relayed via `ToolMessage(status="error")`. The existing `FilterValidator`/`TOOL_VALIDATION_ERROR`/`TOOL_API_ERROR` pattern already does exactly this — it's the right shape.
- **`ToolArgValidationMiddleware`** (feature request langchain #36700 — verify merged before relying) validates LLM-generated tool args against the Pydantic/JSON-Schema `args_schema` *before* execution and re-invokes on failure. Pairs with tightening tool arg schemas (§5).
- **`ToolRetryMiddleware`** for transient API failures (keep `max_retries` modest so the *model* corrects, not the loop).

**Knowledge layer:** DeepAgents **Skills** (OSS, open `agentskills.io` spec shared with Anthropic's format) is exactly the Cloud's "Agent Skills," and already in use here (`src/skills/netbox-mcp-filters`, `src/skills/netbox-graphql`). Keep skills versioned in this git repo and loaded via `skills=[...]`; **skip the hosted Context Hub** (privacy).

---

## 5. NL → correct structured query (the Cloud's core value — highest correctness leverage)

- **Curated parameterized GraphQL operations** — Apollo's finding ("the graph does the API orchestration, not the LLM") is directly on point: raw introspection scales badly for a 100+-type schema. Encode the common cross-domain paths (tenant→sites→VLANs→prefixes) as parameterised operations (exposed as tools and/or retrieved few-shot exemplars); keep the raw GraphQL tool for the long tail. **This is the single highest-leverage change for join correctness** and slots straight into the existing `netbox-graphql` skill.
- **Filter compiler** — reuse LangChain's `load_query_constructor_runnable` + `AttributeInfo` (now in `langchain-classic`) to compile NL into a validated filter AST (`eq/lt/in/and/or`), then a **custom `Visitor`** emits NetBox REST params / GraphQL `filter:` args. Deterministic per object type; does *not* solve joins (that's what GraphQL is for).
- **Schema-RAG** — index GraphQL introspection *per type/field* (name, description, filter grammar, relationships) and retrieve only the fragments named in the question. Mirrors the existing `netbox_graphql_schema` tool; the DeepAgents `search_documentation`→`/retrieved/` pattern is the closest native scaffolding.
- **Tighter tool-arg schemas** — enum object types, constrained filter fields, typed IDs → malformed filters self-correct (§4) instead of returning a NetBox 400.

---

## 6. Model-handoff routing — the SRE-agent template (feeds the PRP-2 continuation)

The near-term goal (a fast **local** model fielding simple queries, handing off to a heavier model + the GraphQL skill only for genuine multi-hop) has a validated, idiomatic shape on this stack: **DeepAgents subagents**, not a router/gateway.

- The parent delegates via the auto-registered **`task()`** tool; the subagent runs in an **isolated context** and returns only its final result. The subagent's **`description`** is the routing signal, and its **`tools=[...]`** scope it.
- **Blueprint: LangChain's "autonomous SRE agent for Kubernetes"** (blog, 2026-08-05; sample repo `langchain-samples/sre-agent`) — built on `create_deep_agent()` with **tiered models by complexity** (strong model for orchestration, cheap model for read-only subagents) and **tool-scoping** ("write tools exist only inside the change-executor subagent… the orchestrator literally can't access a write tool"). It also notes a trivial query → single cheap call → *skip the agent loop* optimisation (95–99% cost cut per check).
- **Mapping:** parent = fast **local llama.cpp** answering simple single-object queries with the existing NetBox tools; register one **`graphql-cross-domain` subagent** (`model` = Ollama Cloud frontier, `tools=[netbox_graphql]` only), invoked only when the parent judges the query multi-hop. Copy the SRE blog's tool-scoping (GraphQL tool lives *only* on the subagent) and its "skip the loop for trivial queries" pattern.
- **LangSmith LLM Gateway is the wrong layer** for the local-vs-cloud decision — it has **no local/Ollama provider** and does no complexity routing. It could optionally sit in front of the *Ollama Cloud* calls for spend caps / rate limits / PII redaction, but it's hosted (Plus/Enterprise) — skip under the privacy mandate.
- Lighter alternative if subagents prove heavy: a plain **LangGraph router node** (cheap classifier or embedding-based `semantic-router`) + `add_conditional_edges` → `local_model` node vs `strong_model+graphql` node, backends pointed via `init_chat_model` / custom `base_url`.

> Caveat to verify against the installed version: the `SubAgent` field name is `system_prompt` in current docs (older deepagents used `prompt`/`instructions`); and for local llama.cpp / Ollama pass a `BaseChatModel` object (OpenAI-compatible `base_url`) rather than a `"provider:model"` string.

---

## 7. The privacy cut — OSS vs hosted

| Self-hostable (adopt) | Hosted / cloud-only (skip under the privacy mandate) |
|---|---|
| `deepagents` harness, subagents, Skills, `RubricMiddleware`, middleware | **Managed Deep Agents** (US-cloud only, no on-prem at beta) |
| `langchain-mcp-adapters`, `LLMToolSelectorMiddleware`, `langgraph-bigtool` | **LLM Gateway** (hosted; no local provider) |
| **`openevals` / `agentevals`** (MIT) + OpenTelemetry export | **Context Hub** (hosted; use own git repo instead) |
| `openapi2tools`, `OpenAPIToolkit`, `BaseGraphQLTool` | Hosted **LangSmith** eval/observability |

Self-hosted eval/observability parity: `openevals` (LLM-as-judge + structured-output evaluators) and `agentevals` (trajectory evaluators) run standalone — a natural home for the existing `tests/eval/` correctness judge if a LangSmith-free path is ever wanted. LangSmith itself added `evaluator create-llm` CLI, composite evaluators, and "assertions read from reference output" (Jul 2026) — all relevant to the reference-grounded correctness judge, but hosted.

---

## 8. ACTIONABLE TASK — upgrade `deepagents` 0.6.10 → 0.7.5

**Status:** Not started — noted here as the concrete follow-up from this research (do when returning to the model-handoff routing).
**Current pin:** `pyproject.toml` → `deepagents>=0.6.10,<0.7`. Target: **0.7.5** (released 2026-08-06). This crosses the **0.7.0 major** (2026-07-29), which has breaking changes.

**Why upgrade:**
- **`RubricMiddleware`** and the current **subagent** API (needed for §4 and the §6 routing) track the 0.7.x line.
- 0.7.0's **empty base prompt** cuts base input tokens ~65% — helpful as the tool surface grows, and it partly *supersedes* our Workaround B.
- New **`FilesystemMiddleware(tools=[...])` allowlist** lets us *enforce* read-only (expose only `ls`/`read_file`/`grep`/`glob`; exclude write/`delete`/execute) — a clean fit for a read-only agent.
- Middleware **override-by-name** (custom middleware whose `.name` matches a default replaces it in place) — cleaner than `excluded_middleware`.

**Breaking changes to budget for (0.7.0):**
1. **Planning is opt-in.** `create_deep_agent` no longer bundles `TodoListMiddleware` (no `write_todos`/`todos`/planning prompt by default). *This stack already suppresses TodoList via Workaround B, so this is a simplification — verify Workaround B still applies cleanly / can be retired.*
2. **Lean prompts.** Base prompt now empty; `BASE_AGENT_PROMPT` deprecated (removed in 0.9.0). Re-verify the `HarnessProfile` Workaround B (`base_system_prompt=""`) is still needed or now redundant.
3. **Filesystem hardened.** `FilesystemBackend`/`LocalShellBackend` default to `virtual_mode=True`; paths outside `root_dir` raise `ValueError`; a destructive recursive `delete` tool exists (a write) — adopt the `FilesystemMiddleware` allowlist to keep read-only.

**Upgrade steps (proposed):**
1. Bump the pin to `deepagents>=0.7.5,<0.8`; `uv sync` / reinstall.
2. Re-run the full test suite + a `netbox-benchmark-v4` **baseline** experiment (`EVAL_FORCE_RERUN=1`, production pair) and compare correctness/completeness/tool-calls to the committed baseline — this is a framework change, so it goes through the eval gate exactly like the 0.6 upgrade did.
3. Reconcile Workaround B against 0.7's empty base prompt (likely simplifiable); confirm `SubAgentMiddleware`/skills still load; verify the GraphQL tools still register standalone.
4. Add the `FilesystemMiddleware` read-only allowlist.
5. Record results in a dated `docs/development/` upgrade note (mirror `2026-06-14_deepagents-0.6-upgrade.md`).

**Effort:** ~½–1 day (a controlled framework bump behind the eval gate). **Risk:** medium — a major version with real prompt/planning/filesystem breaks; the eval baseline is the safety net.

---

## 9. Recommendations (prioritised, all self-hostable)

1. **Build the model-handoff routing as a DeepAgents subagent** (§6) — parent = local model, `graphql-cross-domain` subagent = cloud model + GraphQL tool, tool-scoped, using the SRE-agent template. This is the PRP-2 continuation.
2. **Upgrade to `deepagents` 0.7.5** (§8) — track it as a task; do it *before or alongside* the routing work since the subagent/rubric APIs live on 0.7.x.
3. **Add `RubricMiddleware`** (§4) for structured self-correction gated on project criteria.
4. **Strengthen NL→query** (§5): curated cross-domain GraphQL operations + tighter tool-arg schemas — highest correctness leverage.
5. **Defer** tool-breadth machinery (`LLMToolSelectorMiddleware` / subagent partitioning / server-side `openapi2tools`) until/unless the tool surface actually grows toward ~100.
6. **Skip** all hosted products; if a LangSmith-free eval path is wanted, `openevals`/`agentevals` + OTel.

---

## 10. Sources (primary)

- NetBox Cloud Platform MCP: https://netboxlabs.com/docs/cloud/platform-mcp-server/ · https://netboxlabs.com/blog/your-infrastructure-is-now-agent-native/
- Code Mode / PTC: https://platform.claude.com/docs/en/agents-and-tools/tool-use/programmatic-tool-calling · https://www.anthropic.com/engineering/code-execution-with-mcp · https://docs.langchain.com/oss/python/deepagents/interpreters · https://pypi.org/project/langchain-quickjs/
- Tool sets: https://reference.langchain.com/python/langchain/agents/middleware/tool_selection/LLMToolSelectorMiddleware · https://github.com/langchain-ai/langgraph-bigtool · dynamic-tools limitation https://github.com/langchain-ai/langchain/issues/33808 · https://pypi.org/project/openapi2tools
- Routing/handoff: https://docs.langchain.com/oss/python/deepagents/subagents · https://www.langchain.com/blog/how-we-build-an-autonomous-sre-agent-for-kubernetes-deployments · https://docs.langchain.com/oss/python/langchain/multi-agent/handoffs · LLM Gateway https://docs.langchain.com/langsmith/llm-gateway
- DeepAgents current: https://pypi.org/project/deepagents/ · https://www.langchain.com/blog/deep-agents-v0-7 · https://www.langchain.com/blog/deep-agents-vs-langchain-vs-langgraph · https://docs.langchain.com/oss/python/deepagents/skills · RubricMiddleware https://www.langchain.com/blog/introducing-rubrics-for-deepagents · Managed Deep Agents https://www.langchain.com/blog/managed-deep-agents-is-now-in-public-beta
- NL→query: https://www.langchain.com/blog/query-construction · https://docs.langchain.com/oss/python/langchain/structured-output · https://www.apollographql.com/blog/building-mcp-tools-with-graphql-a-better-way-to-connect-llms-to-your-api · https://reference.langchain.com/python/langchain-community/tools/graphql/tool/BaseGraphQLTool
- Self-hosted eval: `openevals` / `agentevals` (MIT, langchain-ai GitHub)
