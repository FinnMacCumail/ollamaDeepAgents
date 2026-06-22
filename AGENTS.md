# AGENTS.md — Engineering Conventions & Gotchas

Companion to [CLAUDE.md](CLAUDE.md). CLAUDE.md is the high-level project context; this file is
the engineering reference an agent (human or AI) needs before touching the code. When in doubt,
**verify against the code** — docs drift; the source is ground truth.

---

## 1. Repository map (what actually lives where)

| Path | Responsibility |
|---|---|
| `src/main.py` | CLI entry point. `python -m src.main` (interactive), `--batch`, `--model`, `--no-metrics`, `--skills-path`. |
| `src/agents/netbox_agent.py` | `NetBoxDeepAgent` factory, `NETBOX_SYSTEM_PROMPT`, the Workaround-B `HarnessProfile`, middleware assembly, skill loading. |
| `src/agents/ollama_config.py` | `create_ollama_model()` — `ChatOllama`, detects `:cloud` suffix (skips warm-up probe, disables local fallback). |
| `src/agents/llamacpp_config.py` | `create_llamacpp_model()` — OpenAI-compatible client for the llama.cpp backend. |
| `src/middleware/filter_recovery.py` | `FilterErrorRecoveryMiddleware`, `MetricsMiddleware`. |
| `src/middleware/metrics.py` | `QueryMetricsMiddleware`. |
| `src/tools/netbox_tools.py` | MCP client (`create_netbox_mcp_client`), `NetBoxToolWrapper`, `FilterValidator`, `VALID_SUFFIXES`. |
| `src/utils/config.py` | `OllamaConfig`, `NetBoxConfig`, `QueryMetrics`, `load_config()`, `load_netbox_config()`. |
| `src/skills/netbox-mcp-filters/` | `SKILL.md` (runtime, progressive disclosure) + `examples.md`. |
| `tests/eval/` | Model-matrix evaluation harness (dataset, evaluators, runner). |
| `tests/spike/` | QuickJS PTC verification spikes (reproducible). |
| `docs/development/` | Dated decision history + running index README. |

Files that do **not** exist (mentioned in old docs — don't reference them): `src/utils/metrics.py`,
`src/middleware/token_optimizer.py`, `src/skills/.../constraints.md`, `tests/results/`,
`verify_langsmith.py`, `test_connection.py`, `test_tool_direct.py`.

---

## 2. The NetBox MCP filter constraint (the load-bearing domain fact)

The NetBox MCP server accepts a **narrow** filter grammar. The `FilterValidator` in
`src/tools/netbox_tools.py` enforces it locally so the model gets a structured, recoverable
error instead of an opaque HTTP 400.

`VALID_SUFFIXES` (must stay in sync with the MCP server's whitelist):
```
n, ic, nic, isw, nisw, iew, niew, ie, nie, empty, regex, iregex, lt, lte, gt, gte, in
```

Rules:
- **Relationship filters take a numeric ID or lowercase slug, never a display name.**
  `{"site_id": 5}` ✓ · `{"site": "dm-akron"}` ✓ (slug) · `{"site": "DM-Akron"}` ✗ (400).
- **No multi-hop traversal:** `device__site_id` ✗. Resolve in two steps instead.
- **No invented IDs:** only use IDs returned by a prior tool call in the same conversation.
- **GenericForeignKey fields are scalar-only:** `assigned_object_id`, `scope_id`, `object_id`
  cannot take Django-style relational suffixes.

The canonical recovery pattern (taught by the skill):
```python
# Step 1 — resolve name → id
site = netbox_get_objects("dcim.site", filters={"name": "DM-Akron"}, fields=["id", "slug"])
# Step 2 — filter by id
racks = netbox_get_objects("dcim.rack", filters={"site_id": site_id_from_step_1})
```

---

## 3. Error-recovery architecture

`NetBoxToolWrapper.validated_func` (`netbox_tools.py`) wraps every MCP tool's async call and
converts two failure classes into structured tool messages the model can act on:

| Source | Becomes | Meaning |
|---|---|---|
| `ValueError` from `FilterValidator` | `TOOL_VALIDATION_ERROR: ...` | The filter was malformed before hitting NetBox. |
| `ToolException` (NetBox 4xx/5xx) | `TOOL_API_ERROR: ...` | NetBox rejected the otherwise-valid call. |

Both strings carry a suggestion + a pointer to the `netbox-mcp-filters` skill, and the agent
loop continues rather than crashing.

**Important (verified by the QuickJS spikes):** because the recovery wraps the tool's `_arun()`,
it is **transparent to PTC** — tool calls made from inside a QuickJS `eval` block also surface
these structured errors. See `docs/development/2026-06-03_quickjs-code-interpreter-research.md` §14.

---

## 4. DeepAgents 0.6.10 framework state

- **Workaround A:** REMOVED on the 0.6 upgrade. The `read_file(path=)` bug is fixed upstream.
- **Workaround B:** ACTIVE. In `netbox_agent.py`, a `HarnessProfile` is registered for the
  `ollama` and `openai` providers:
  ```python
  HarnessProfile(
      base_system_prompt="",                                  # suppress 0.6 BASE_AGENT_PROMPT
      excluded_middleware=frozenset({"TodoListMiddleware"}),  # remove write_todos + its prompt
  )
  ```
  Why: 0.6 silently appends ~9.6K chars of default prompt content (`BASE_AGENT_PROMPT` +
  `TASK_SYSTEM_PROMPT` + `WRITE_TODOS_SYSTEM_PROMPT`). The "iterate / keep working until done"
  framing causes search-hedging on negative-finding queries, and the TodoList
  "answer-after-last-write_todos" instruction overwrote a comprehensive answer with an "All
  done" filler. Full diagnostic: `docs/development/2026-06-14_deepagents-0.6-upgrade.md`.

- **Custom middleware order:** `FilterErrorRecoveryMiddleware` → `MetricsMiddleware` →
  `QueryMetricsMiddleware`, plus the built-in `SummarizationMiddleware`.
- **Skill loading:** `SkillsMiddleware` reads `src/skills/` via a `FilesystemBackend`
  (`root_dir=PROJECT_ROOT, virtual_mode=True`). Skill frontmatter requires `name:` (not `title:`).
- **Residual known issue:** the VLAN-100-class negative-finding query is still slower than its
  0.5.6 baseline. The QuickJS spikes proved PTC is *not* the fix; the open lever is suppressing
  `SubAgentMiddleware`'s `TASK_SYSTEM_PROMPT`. See the QuickJS doc §16.

---

## 5. Config loading — two entry points

`src/utils/config.py`:
- `load_config()` → `(OllamaConfig, NetBoxConfig)`. `OllamaConfig` validates `OLLAMA_MODEL`
  against `allowed_prefixes`. Used by `src/main.py`.
- `load_netbox_config()` → `NetBoxConfig` only. **Bypasses the model-prefix validator** so the
  eval harness can test arbitrary models. Used by `tests/eval/` and `tests/spike/`.

`NetBoxDeepAgent.__init__` treats `backend` and `model_name` as **authoritative** when passed —
it only falls back to env when they're absent. This is what lets the matrix harness vary
`(backend, model_name)` in one process. Don't reintroduce an unconditional `load_config()` in
the constructor; it would clobber explicit params.

To run a model whose prefix isn't allow-listed: add the prefix to `allowed_prefixes` in
`config.py`, or set `DEBUG=true` to bypass validation.

---

## 6. Evaluation harness (`tests/eval/`)

The primary quality gate. Replaces the old "fetch trace, eyeball JSON, write a markdown report"
loop.

- `dataset.py` — `netbox-benchmark-v2`, 4 benchmark queries with `expected_entities` ground
  truth pulled from real traces. `ensure_dataset()` is idempotent.
- `evaluators.py` — three evaluators: `entity_coverage` (code-based substring match),
  `completeness_judge` (LLM-as-judge, default judge `gpt-oss:20b`, override `EVAL_JUDGE_MODEL`),
  `tool_call_efficiency` (trajectory count).
- `run_matrix.py` — one `aevaluate()` per model. Env knobs:
  - `EVAL_MODELS="ollama:model-a,ollama:model-b"` — override the default model list.
  - `EVAL_FORCE_RERUN=1` — bypass skip-completed (for regression tests against a baseline).
  - `EVAL_MAX_CONCURRENCY=1` — per-example concurrency (keep at 1; NetBox MCP is stdio).
  - Built-in skip-completed + fail-fast-on-429 (Ollama Cloud quota) logic.

**Convention:** after any change that could affect agent behaviour (framework, middleware,
skill, prompt, validator), re-run at least `deepseek-v4-flash:cloud` with `EVAL_FORCE_RERUN=1`
and confirm entity/completeness hold vs the baseline experiment before merging.

Cost note: a full 10-model cloud sweep can exhaust the Ollama Cloud Pro **session** window
(429s). The runner fails fast on quota; re-run later and skip-completed picks up the remainder.

---

## 7. Conventions

- **Python env:** use `./venv/bin/python` (the repo venv). Avoid `source venv/bin/activate` in
  docs/commands — the explicit interpreter path is more reliable.
- **Imports:** relative within `src/` (`from ..tools.netbox_tools import ...`).
- **Secrets:** never commit real NetBox tokens or LangSmith keys. `.env` is the only home for
  them; docs use `xxxx` placeholders.
- **Git:** branch off `master` for non-trivial work; feature branch → `--no-ff` merge → delete.
  Don't commit/push unless asked.
- **Decision records:** non-obvious architectural choices get a dated `docs/development/` note +
  a one-line entry in `docs/development/README.md`.
- **Skill edits:** the runtime skill is `src/skills/netbox-mcp-filters/SKILL.md`. Frontmatter
  needs `name:`. Keep `VALID_SUFFIXES` in `netbox_tools.py` and the skill's suffix guidance in sync.

---

## 8. Testing

```bash
./venv/bin/python -m pytest tests/test_netbox_integration.py   # agent init + query
./venv/bin/python -m pytest tests/test_filters.py              # validator
./venv/bin/python -m tests.eval.run_matrix                     # model-matrix eval (LangSmith)
./venv/bin/python -m tests.spike.spike1_mcp_ptc_bridge         # PTC bridge (needs MCP up)
```

Fixtures live in `tests/conftest.py` (`mock_netbox_config`, `mock_ollama_config`,
`mock_netbox_response`, `failed_queries`, `invalid_filters`, …). The eval and spike suites need
the real NetBox MCP server reachable at `localhost:8000` and the relevant env set.

---

## 9. Pointers

- Current decision history & roadmap: `docs/development/README.md`
- Why the middleware looks the way it does: `docs/development/2026-06-14_deepagents-0.6-upgrade.md`
- Why PTC isn't adopted (yet) + re-trigger conditions: `docs/development/2026-06-03_quickjs-code-interpreter-research.md`
- Model-matrix plan & tiered roadmap: `docs/development/2026-06-03_langsmith-evaluation-research.md`
