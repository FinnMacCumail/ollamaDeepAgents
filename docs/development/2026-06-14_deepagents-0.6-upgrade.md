# DeepAgents 0.5.6 → 0.6.10 Upgrade

**Date:** 2026-06-14
**Status:** Complete, merged to master
**Branch:** `deepagents-0.6-upgrade` (merged + deleted)
**Purpose:** Document the framework upgrade from DeepAgents 0.5.6 to 0.6.10, the removal of Workaround A (now fixed upstream), the addition of Workaround B (new regressions introduced by 0.6's default behaviour), and the empirical validation that quality matches the 0.5.6 baseline.

**Related:**
- `2026-06-03_langsmith-evaluation-research.md` §6 Tier 2 — flagged this upgrade as the first Tier 2 item; this doc executes it
- `2026-06-03_quickjs-code-interpreter-research.md` — was gated on this upgrade; now unblocked

---

## Why upgrade

Two motivations from the LangSmith research doc §6:

1. **Workaround A's underlying framework bug was fixed upstream.** Commit `3b65e0c` patched a `read_file(path=…)` vs `file_path` documentation mismatch in DeepAgents (issues #3185, #3188 — both Closed "Not planned" by maintainers, but the description-level fix shipped anyway on `main`). The workaround was load-bearing on 0.5.x but became dead weight once the upstream fix shipped.
2. **0.6 unlocks Tier 2 features** that 0.5.6 doesn't have — particularly the QuickJS Code Interpreter middleware researched in the parallel doc, plus `RubricMiddleware`, first-class `HarnessProfile` bundles, and built-in profiles for DeepSeek/Qwen/Kimi.

Cost estimate from the research doc was "1-3 days realistic". Actual execution took one focused session including a regression investigation.

---

## Versions before vs. after

| Package | Before | After |
|---|---|---|
| `deepagents` | 0.5.6 | 0.6.10 |
| `langchain` | 1.2.17 | 1.3.9 |
| `langgraph` | 1.1.10 | 1.2.5 |
| `langsmith` | 0.8.0 | 0.8.15 |
| `langchain-anthropic` | (was 1.x) | 1.4.6 |
| `langchain-google-genai` | 4.2.2 | 4.2.5 |

Single command: `pip install --upgrade "deepagents>=0.6.10,<0.7"`. No dependency-resolution conflicts. `pyproject.toml` pin updated from `deepagents>=0.5.6` to `>=0.6.10,<0.7`.

---

## What survived unchanged

`HarnessProfile`'s backward-compatible API. All fields used by Workaround A still exist on the 0.6 dataclass:

- `base_system_prompt: str | None = None` *(new in 0.6 — see Workaround B)*
- `system_prompt_suffix: str | None = None`
- `tool_description_overrides: Mapping[str, str]`
- `excluded_tools: frozenset[str]`
- `excluded_middleware: frozenset[type[AgentMiddleware] | str]` *(new in 0.6 — see Workaround B)*
- `extra_middleware: Sequence[AgentMiddleware] | Callable`
- `general_purpose_subagent: GeneralPurposeSubagentProfile | None`

`register_harness_profile()` signature unchanged. `create_deep_agent()` accepts every parameter our code uses (model, tools, system_prompt, middleware, skills, backend, checkpointer). Our middleware classes (`FilterErrorRecoveryMiddleware`, `MetricsMiddleware`, `QueryMetricsMiddleware`) and skill-loading via `FilesystemBackend` work unchanged.

---

## Workaround A — removed

### What it was (0.5.6 era)

`src/agents/netbox_agent.py:17-77` (commit `3b65e0c`). A two-pronged HarnessProfile that suppressed a framework bug where the `read_file` tool description used the wrong argument name (`path` instead of `file_path`) in 3 of 4 worked examples, causing skill-loading to silently fail.

Two prongs:
1. `tool_description_overrides={"read_file": _READ_FILE_CORRECTED}` — replaced the broken tool description with a corrected one
2. `system_prompt_suffix=_FILE_PATH_SUFFIX` — appended a final reminder at the end of the system prompt as a tiebreaker against any remaining bad examples

### Why it could be removed

Inspected the installed `deepagents/middleware/filesystem.py` in 0.6.10:

- 8 uses of `file_path=` in the `read_file` tool description
- 0 naked `path=` references in `read_file()`, `write_file()`, `edit_file()`, `glob()`, `grep()` examples
- The hardcoded SkillsMiddleware example at `skills.py:817` that prong 2 was specifically counteracting is also fixed

So both prongs of Workaround A address bugs that no longer exist. Removing them is safe.

### Validation

Re-ran the multi-aspect Dunder Mifflin query (the heaviest skill-loading workload) on 0.6.10 after removal. Skills loaded cleanly, no `read_file` validation errors, full skill body reached the model.

**Lines removed: ~50** from `netbox_agent.py:17-77`, replaced with a 6-line breadcrumb comment for historical context.

---

## Workaround B — added

Three pieces of 0.6's default behaviour actively regressed this agent's quality on negative-finding queries (e.g. "where is VLAN X deployed at tenant Y?" when the answer is "not deployed"). Diagnostic recorded in trace `019ec810-1793-78f0-b608-7fd76f5bce0f` and the chronological sub-run analysis.

### The regression — empirically observed

Three flash runs on `netbox-benchmark-v2`:

| Experiment | entity | complete | tools | latency |
|---|---|---|---|---|
| 0.5.6 baseline (`e13026da`) | 0.95 | 1.00 | 7.2 | 34.6s |
| 0.6.10 (no fixes) run 1 (`d88aea3c`) | 0.92 | 0.85 | 9.0 | 31.8s |
| 0.6.10 (no fixes) run 2 (`f6b65c03`) | 0.80 | 0.75 | 7.5 | 33.0s |

The aggregate regression was concentrated entirely on the VLAN 100 query (the negative-finding case):

| Query | 0.5.6 baseline | 0.6.10 run 1 | 0.6.10 run 2 |
|---|---|---|---|
| dmi01-nashua | 0.80/1.00/4 tools | 0.80/1.00/5 | 0.80/1.00/5 |
| Rack elevation | 1.00/1.00/6 | 0.88/0.90/6 | 1.00/1.00/4 |
| **VLAN 100** | **1.00/1.00/8 tools** | **1.00/0.50/18 tools** | **0.40/0.00/13 tools** |
| Dunder Mifflin | 1.00/1.00/11 | 1.00/1.00/7 | 1.00/1.00/8 |

### Root cause — 0.6 silently appends ~9.6K chars of new system-prompt content

Inspected `BASE_AGENT_PROMPT` (`deepagents/graph.py`), `TASK_SYSTEM_PROMPT` (`SubAgentMiddleware`), `WRITE_TODOS_SYSTEM_PROMPT` and `WRITE_TODOS_TOOL_DESCRIPTION` (`TodoListMiddleware`):

| Source | Bytes | Effect on this agent |
|---|---|---|
| `BASE_AGENT_PROMPT` | 2258 | "Iterate", "verify against what was asked, not your own output", "keep working until task is fully complete; only yield back when done or genuinely blocked" — designed for coding/research agents, causes hedging on negative findings |
| `TASK_SYSTEM_PROMPT` | 2144 | Sub-agent spawning instructions — adds prompt bloat, minor behavioural impact |
| `WRITE_TODOS_SYSTEM_PROMPT` | 1370 | **"When you finish all work, write your final answer in the message AFTER your last `write_todos` call"** — directly mandates a two-turn finish that displaces substantive answers with closing remarks |
| `WRITE_TODOS_TOOL_DESCRIPTION` | 3873 | Makes the `write_todos` tool callable — model elects to use it for "complex" tasks |

In aggregate: ~9,645 chars of extra prompt content appended to our `NETBOX_SYSTEM_PROMPT` that 0.5.6 did not add. Several pieces actively counteract the skill's explicit guidance (e.g. AVOID REDUNDANT SEARCHES).

### How the regression manifested

**On both VLAN 100 runs (regardless of whether `write_todos` engaged):** `BASE_AGENT_PROMPT`'s "iterate" and "keep working" instructions caused the model to hedge with search variants (`"Jimbob's"`, `"Jimbob"`, `"Banking"` — exactly the pattern the skill prohibits) and over-explore before concluding. Tool calls jumped 8 → 13-18.

**On run 2 specifically:** The model elected to use `write_todos` (4 invocations). The trace chronology shows:

1. Penultimate LLM call produced a comprehensive answer ("VLAN 100 is **not deployed** at any Jimbob's Banking & Trust site" + full breakdown table of sites and VLANs)
2. Model invoked `write_todos` to mark tasks complete
3. `WRITE_TODOS_SYSTEM_PROMPT`'s "write final answer AFTER last write_todos call" instruction kicked in
4. Final LLM call dutifully produced "All done. Let me know if you'd like me to look into anything else…"
5. **That meaningless closing remark became the agent's final output**, which is what the LLM judge scored — and what the user would have seen

The completeness score of 0.00 was the judge correctly evaluating the substandard final answer. The *substantive* answer was perfect — TodoListMiddleware destroyed it.

### The fix

Re-add a `HarnessProfile` registration to `netbox_agent.py` with two suppressions:

```python
from deepagents import HarnessProfile, register_harness_profile

_NETBOX_PROFILE = HarnessProfile(
    base_system_prompt="",                                # overrides BASE_AGENT_PROMPT entirely
    excluded_middleware=frozenset({"TodoListMiddleware"}), # removes write_todos + its prompt
)
for _provider in ("ollama", "openai"):
    register_harness_profile(_provider, _NETBOX_PROFILE)
```

Verified via `deepagents/profiles/harness/harness_profiles.py:778-796` that `base_system_prompt=""` (empty string, not None) **overrides** `BASE_AGENT_PROMPT` rather than appending to it. The `_apply_profile_prompt()` function checks `profile.base_system_prompt is not None`, so empty string suppresses the upstream prompt entirely.

### Validation

| Experiment | entity | complete | tools | latency |
|---|---|---|---|---|
| 0.5.6 baseline | 0.95 | 1.00 | 7.2 | 34.6s |
| 0.6.10 no-fixes (worst) | 0.80 | 0.75 | 7.5 | 33.0s |
| **0.6.10 + Workaround B** (`769504c1`) | **0.95** | **1.00** | 9.2 | 42.3s |

VLAN 100 specifically: entity coverage restored from 0.40 → **1.00**, completeness from 0.00 → **1.00**. The "All done" finale is gone; the comprehensive answer reaches the user.

---

## Known trade-off — residual latency

Post-fix aggregate latency is **42.3s vs. 34.6s baseline = 22% slower**. The increase is concentrated on the VLAN 100 query specifically:

- 0.5.6 baseline: 54.7s, 8 tool calls
- 0.6.10 + Workaround B: 93.2s, 21 tool calls

Even with `BASE_AGENT_PROMPT` suppressed, the model still uses more tool calls than baseline on the negative-finding case. Likely candidates for the residual hedging:

- `TASK_SYSTEM_PROMPT` from `SubAgentMiddleware` (still appended — not suppressed by Workaround B)
- `PatchToolCallsMiddleware` (new in 0.6, behaviour not deeply audited)
- Possibly natural variance for deepseek-v4-flash on negative findings without `BASE_AGENT_PROMPT`'s pressure to iterate

For interactive use the 22% increase is acceptable given quality is back to baseline. If latency becomes a constraint, the next investigation lever is suppressing `SubAgentMiddleware`'s prompt addition — but it's a smaller knob and risks losing future sub-agent functionality.

The QuickJS Code Interpreter middleware (researched in `2026-06-03_quickjs-code-interpreter-research.md`) is likely a better path for cutting VLAN-class latency — it folds multi-call NetBox workflows into single model turns, which would also bypass the residual hedging entirely. Now unblocked by this upgrade.

---

## What the runner now supports

`tests/eval/run_matrix.py` gained an `EVAL_FORCE_RERUN=1` env override during this upgrade. When set, the runner bypasses `_find_completed_experiment()` and re-runs models even if a completed experiment exists on the dataset. Used during this upgrade's regression-validation runs; useful for any future framework or middleware change where comparing pre/post against a known baseline is valuable.

---

## Files changed

| File | Lines | Change |
|---|---|---|
| `pyproject.toml` | 1 | `deepagents>=0.5.6` → `deepagents>=0.6.10,<0.7` |
| `src/agents/netbox_agent.py` | net ~-20 | Workaround A removed (~-50 lines), Workaround B added (~+35), breadcrumbs (+6) |
| `tests/eval/run_matrix.py` | +9 | `EVAL_FORCE_RERUN=1` env override |

No changes to:
- Skill content (`src/skills/netbox-mcp-filters/SKILL.md`)
- MCP server integration (`src/tools/netbox_tools.py`)
- Validator (`src/tools/netbox_tools.py:FilterValidator`)
- Custom middleware (`src/middleware/*.py`)
- Dataset (`tests/eval/dataset.py` — v2 still active)
- Evaluators (`tests/eval/evaluators.py`)

---

## Sources / references

- [deepagents 0.6.10 on PyPI](https://pypi.org/project/deepagents/) — release date 2026-06-13
- [DeepAgents GitHub releases](https://github.com/langchain-ai/deepagents/releases) — 0.6.x series shipping notes
- [Harness profiles docs](https://docs.langchain.com/oss/python/deepagents/harness) — `excluded_tools`, `register_harness_profile()` reference
- Trace `019ec810-1793-78f0-b608-7fd76f5bce0f` — the load-bearing diagnostic showing the penultimate LLM call had the comprehensive answer that was then overwritten by "All done" — on LangSmith under experiment `ollama-deepseek-v4-flash-cloud-f6b65c03`
- Comparison experiments on `netbox-benchmark-v2`:
  - `ollama-deepseek-v4-flash-cloud-e13026da` (0.5.6 baseline)
  - `ollama-deepseek-v4-flash-cloud-d88aea3c` (0.6.10 no-fixes run 1)
  - `ollama-deepseek-v4-flash-cloud-f6b65c03` (0.6.10 no-fixes run 2)
  - `ollama-deepseek-v4-flash-cloud-769504c1` (0.6.10 + Workaround B — validated baseline-matching)

---

## Next moves unlocked

| Item | Effort | Status |
|---|---|---|
| Full 10-model matrix re-run with Workaround B applied | ~30-60 min | Optional preflight before considering this upgrade fully validated across models |
| QuickJS Code Interpreter spike (per `2026-06-03_quickjs-code-interpreter-research.md`) | ~1-2 days for the 3 validation spikes | Unblocked — was gated on 0.6 |
| Investigate residual VLAN 100 latency | ~half day | Optional; SubAgentMiddleware suppression is the next lever |
| Context Hub adoption (per `2026-06-03_langsmith-evaluation-research.md` §6 Tier 2) | TBD | Independent of this upgrade |
| LangSmith Engine adoption | TBD | Now relevant given Tier 1 is solid and Tier 2 is half-done |
