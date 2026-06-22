# CLAUDE.md — NetBox DeepAgents Query System

> **IMPORTANT:** Review [AGENTS.md](AGENTS.md) before beginning any work — it carries the
> deeper technical conventions, gotchas, and the current middleware/HarnessProfile state.
> This file is the high-level project context; AGENTS.md is the engineering companion.

## Project Purpose

An intelligent NetBox infrastructure query system built on the **DeepAgents** framework. It
answers natural-language questions against NetBox data while working around the NetBox MCP
server's strict filter constraints that cause failures in naive implementations.

Inference runs through one of two interchangeable backends (one-line `.env` switch):
- **Ollama** — local models *and* Ollama Cloud frontier models (`:cloud` suffix). The current
  production default is `deepseek-v4-flash:cloud`.
- **llama.cpp** — OpenAI-compatible server, used for the privacy-critical / fully-local path.

Privacy note: the default cloud path sends queries and tool results to `ollama.com`. The
llama.cpp backend (see `docs/setup/llamacpp.md`) is the data-never-leaves-the-box option.

## Before Starting Any Task

1. **Read the docs:** this file, [AGENTS.md](AGENTS.md), `README.md`, and the relevant
   `docs/` subtree (`docs/development/` has the most current decision history).
2. **Understand the problem domain (the core constraint):**
   - The NetBox MCP server rejects multi-hop filters like `device__site_id`.
   - It rejects unsupported Django lookup suffixes. The validator's allow-list of suffixes is:
     `n, ic, nic, isw, nisw, iew, niew, ie, nie, empty, regex, iregex, lt, lte, gt, gte, in`.
   - Relationship filters take a **numeric ID or lowercase slug**, never a display name.
   - GenericForeignKey fields (`assigned_object_id`, `scope_id`, `object_id`) are scalar-only.
3. **Check status:** `TODO.md`, recent `git log`, and `docs/development/README.md` (the
   running changelog of architectural decisions).

## Architecture Overview

```
ollamaDeepAgents/
├── src/
│   ├── main.py                       # CLI entry point (python -m src.main)
│   ├── agents/
│   │   ├── netbox_agent.py           # Core agent factory + HarnessProfile (Workaround B)
│   │   ├── ollama_config.py          # ChatOllama setup (local + :cloud)
│   │   └── llamacpp_config.py        # llama.cpp OpenAI-compatible backend
│   ├── middleware/
│   │   ├── filter_recovery.py        # FilterErrorRecoveryMiddleware + MetricsMiddleware
│   │   └── metrics.py                # QueryMetricsMiddleware
│   ├── tools/
│   │   └── netbox_tools.py           # MCP client + NetBoxToolWrapper + FilterValidator
│   ├── skills/
│   │   └── netbox-mcp-filters/
│   │       ├── SKILL.md              # Runtime skill (progressive disclosure)
│   │       └── examples.md
│   └── utils/
│       ├── config.py                 # OllamaConfig/NetBoxConfig, load_config, load_netbox_config
│       └── logging.py
├── tests/
│   ├── test_filters.py               # Validator tests
│   ├── test_netbox_integration.py    # Agent init + query tests
│   ├── test_ollama_models.py
│   ├── eval/                         # Model-matrix evaluation harness (LangSmith)
│   │   ├── dataset.py                # netbox-benchmark-v2 dataset
│   │   ├── evaluators.py             # entity_coverage, completeness_judge, tool_call_efficiency
│   │   └── run_matrix.py             # per-model runner (EVAL_MODELS, EVAL_FORCE_RERUN)
│   ├── spike/                        # QuickJS PTC verification spikes (1, 2, 3)
│   ├── manual/                       # Manual test scripts
│   └── data/
├── docs/                            # development/, setup/, guides/, reference/, traces/, posts/
└── examples/                        # basic_usage.py, failed_query_recovery.py
```

### Technology Stack
- **Framework:** DeepAgents 0.6.10 (LangChain 1.3.x + LangGraph 1.2.x)
- **Inference:** Ollama (local + Cloud) or llama.cpp, selected via `LLM_BACKEND`
- **Default model:** `deepseek-v4-flash:cloud` (`.env`); code fallback `gpt-oss:20b`
- **MCP server:** NetBox MCP (stdio transport, 4 tools)
- **Observability:** LangSmith tracing + the `tests/eval/` matrix harness
- **Python:** 3.11+

## The MCP Filter Constraint (the central design problem)

This is the knowledge the `netbox-mcp-filters` skill exists to inject. It remains the most
important domain fact for any work on this agent.

**NEVER:**
- Multi-hop / relationship-traversal filters: `device__site_id`, `termination_a__device_id`
- Display names where an ID/slug is required: `{"site": "DM-Akron"}` (use `site_id` or slug)
- Invented IDs — only use IDs returned by a prior tool call in the same conversation.

**ALWAYS:**
- Direct ID filters: `{"device_id": 123}`, `{"site_id": 5}`
- Two-step queries for relationships — resolve the name to an ID first, then filter by ID.
- `netbox_search_objects(query="pattern")` for partial / fuzzy matching.

The `FilterValidator` in `src/tools/netbox_tools.py` enforces this with an **allow-list** that
mirrors the MCP server's accepted suffixes exactly, and converts violations into structured
`TOOL_VALIDATION_ERROR` messages the model can recover from (rather than opaque 400s).

## Current Framework State (DeepAgents 0.6.10)

Two project-specific framework adaptations live in `src/agents/netbox_agent.py`:

- **Workaround A — REMOVED.** The old `read_file(path=)` vs `file_path` tool-description
  override (issues #3185/#3188) is gone; the upstream bug was fixed in 0.6.
- **Workaround B — ACTIVE.** A `HarnessProfile` registered for the `ollama` and `openai`
  providers with `base_system_prompt=""` and `excluded_middleware={"TodoListMiddleware"}`.
  0.6 silently appends ~9.6K chars of default system-prompt content that regresses quality on
  negative-finding queries; Workaround B suppresses the two harmful pieces. Full rationale:
  `docs/development/2026-06-14_deepagents-0.6-upgrade.md`.

**Middleware stack** (custom, in order): `FilterErrorRecoveryMiddleware`, `MetricsMiddleware`,
`QueryMetricsMiddleware`, plus DeepAgents' built-in `SummarizationMiddleware`.
`TokenOptimizationMiddleware` was **removed** (commit `01df4e9`) — it head-truncated tool
results and skill bodies.

## Configuration (`.env`)

```bash
# Backend selection
LLM_BACKEND=ollama                       # ollama | llamacpp

# NetBox
NETBOX_URL=http://localhost:8000
NETBOX_TOKEN=your-netbox-api-token
MCP_SERVER_PATH=/path/to/netbox-mcp-server

# Ollama (local + cloud)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=deepseek-v4-flash:cloud     # default; gpt-oss:20b if unset
OLLAMA_TEMPERATURE=0.0

# llama.cpp backend (when LLM_BACKEND=llamacpp)
LLAMACPP_BASE_URL=http://localhost:8080/v1
LLAMACPP_MODEL=Qwen_Qwen3-14B-Q5_K_M.gguf
LLAMACPP_API_KEY=sk-no-key-required

# LangSmith tracing (never commit a real key)
LANGCHAIN_API_KEY=lsv2_pt_xxxxxxxx
LANGCHAIN_PROJECT=netbox-deepagents-ollama
LANGCHAIN_TRACING_V2=true

# Dev
DEBUG=false                              # DEBUG=true bypasses the model-prefix validator
```

`config.py` exposes two loaders: `load_config()` (validates `OLLAMA_MODEL` against an
allow-list of prefixes) and `load_netbox_config()` (NetBox creds only — used by the eval
harness so it can test arbitrary models without tripping the validator).

## Running the System

```bash
# Interactive agent
./venv/bin/python -m src.main

# Batch mode
./venv/bin/python -m src.main --batch "query 1" "query 2"

# Override model without editing .env
./venv/bin/python -m src.main --model deepseek-v4-flash:cloud

# Model-matrix evaluation (LangSmith)
./venv/bin/python -m tests.eval.run_matrix
EVAL_MODELS="ollama:glm-5:cloud,ollama:kimi-k2.6:cloud" ./venv/bin/python -m tests.eval.run_matrix

# Tests
./venv/bin/python -m pytest tests/test_netbox_integration.py
```

## Development Workflow

- Branch off `master` for non-trivial work; the recent pattern is feature branch → `--no-ff`
  merge → delete branch (see `git log`).
- After any framework, middleware, skill, or prompt change, re-run the eval harness against at
  least `deepseek-v4-flash:cloud` (`EVAL_FORCE_RERUN=1` bypasses skip-completed) and compare
  against the `netbox-benchmark-v2` baseline before merging.
- Record non-obvious architectural decisions in a dated `docs/development/` note and add a line
  to `docs/development/README.md`.

## AI Assistant Behavior Rules

**DO:**
- Verify file paths and current code state before acting — this doc and the audits can drift.
- Prefer two-step (resolve-name-to-ID) queries for any relationship traversal.
- Use the skills system for NetBox domain knowledge rather than inlining it.
- Validate filter patterns against the allow-list before assuming they work.
- Surface real errors (auth, quota, 400s) rather than masking them.

**DON'T:**
- Assume multi-hop filters or display-name filters will work — they won't.
- Invent NetBox IDs; only use IDs returned by prior tool calls.
- Hardcode model names in code (model identity flows through config/params).
- Commit real credentials (NetBox tokens, LangSmith keys).

## Resources

### Internal
- [AGENTS.md](AGENTS.md) — engineering conventions and gotchas
- `docs/development/` — dated decision history + the running index README
- `docs/reference/architecture.md`, `docs/reference/mcp-constraints.md`,
  `docs/reference/model-compatibility.md`
- `docs/setup/` — ollama-cloud.md, llamacpp.md, langsmith.md
- `src/skills/README.md` — skills development guide

### External
- [DeepAgents Documentation](https://docs.langchain.com/oss/python/deepagents)
- [Ollama Cloud](https://ollama.com/cloud) · [Model Library](https://ollama.com/library)
- [NetBox API](https://docs.netbox.dev/en/stable/rest-api/) · [MCP](https://modelcontextprotocol.io/)

---

*Update this file as the project evolves. When framework/middleware/model defaults change,
update both this file and AGENTS.md, and add a dated note under `docs/development/`.*
