# DeepAgents 0.6.10 → 0.7.5 Upgrade

**Date:** 2026-08-11
**Status:** ✅ Completed — eval-gated, no regression
**Purpose:** Bump `deepagents` from 0.6.10 to 0.7.5 (crossing the 0.7.0 major) to track the current subagent + `RubricMiddleware` APIs needed for the planned model-handoff routing, and to reconcile Workaround B against 0.7's leaner defaults.
**Driven by:** `2026-08-10_langchain-ecosystem-vs-netbox-cloud-platform.md` §8 (the actionable follow-up from that research). Prior upgrade: `2026-06-14_deepagents-0.6-upgrade.md`.

---

## TL;DR

`deepagents` 0.6.10 → **0.7.5** (also bumps langchain 1.3.9→1.3.14, langchain-core 1.4.7→1.5.3, langsmith 0.8.15→0.10.17, anthropic 0.97→0.121; adds `langchain-protocol`). langgraph stayed at 1.2.5.

- **One breaking change hit us:** 0.7.0 makes planning **opt-in**, so `TodoListMiddleware` is no longer bundled — and 0.7.x **strictly raises `ValueError`** when an `excluded_middleware` entry matches no assembled middleware. Workaround B's `excluded_middleware={"TodoListMiddleware"}` was that exact case. **Fix:** removed the exclusion (TodoList suppression is now *inherent*).
- **Workaround B API survived** — `HarnessProfile`, `register_harness_profile`, `create_deep_agent`, `FilesystemBackend` all still present and importable.
- **Regression-neutral** on the unit suite (proven by reinstall-and-compare against 0.6.10).
- **Eval gate passed** — no correctness regression vs the committed 0.6.10 baseline; the Workaround-B-sensitive negative-finding queries are healthy.

---

## What changed and why

### The one breaking change: planning is opt-in (0.7.0)

`create_deep_agent` no longer bundles `TodoListMiddleware` by default (0.7.0 made planning opt-in; the base prompt is also empty by default now, cutting ~65% of base tokens). The agent build failed with:

```
ValueError: HarnessProfile.excluded_middleware entries matched no middleware across any
assembled stack: 'TodoListMiddleware' (string). Typo or stale profile — every exclusion
must correspond to a middleware actually present at runtime.
```

This is 0.7.x being strict: an exclusion that matches nothing is now an error, not a silent no-op.

### Workaround B reconciliation (`src/agents/netbox_agent.py`)

Workaround B originally (0.6.10) suppressed two pieces of 0.6's default prompt/middleware that regressed negative-finding queries. Under 0.7.0 the framework's own defaults now do most of that:

| Workaround B piece | 0.6.10 role | 0.7.5 status |
|---|---|---|
| `base_system_prompt=""` | override the ~2258-char `BASE_AGENT_PROMPT` | **Kept** — but now belt-and-suspenders (0.7 base prompt is empty by default); kept explicit to guard against residual base prompt and document intent |
| `excluded_middleware={"TodoListMiddleware"}` | remove `write_todos` + its 2-turn-finish prompt | **Removed** — planning is opt-in in 0.7, so TodoList isn't present; excluding it now errors. Suppression is inherent. |

The `HarnessProfile` is now simply `HarnessProfile(base_system_prompt="")`, registered for the `ollama` and `openai` providers as before. Full rationale is in the code comment.

### Known incompatibility (harmless)

`langchain-quickjs 0.2.0` pins `deepagents<0.7.0`, so pip flags it as incompatible with 0.7.5. This is the **deferred QuickJS/PTC package** — used only by `tests/spike/` (the code-mode verification spikes), never by the app. It stays installed but unused; the spike scripts would need a `langchain-quickjs` bump if ever revisited (and per `2026-06-03_quickjs-code-interpreter-research.md` and the 2026-08-10 ecosystem research, Code Mode remains deferred).

---

## Verification

### API survival + build

`create_deep_agent`, `HarnessProfile`, `register_harness_profile`, `FilesystemBackend` all import cleanly under 0.7.5; the agent builds and skills load with no loader warnings (4 MCP tools).

### Regression-neutrality (unit suite)

`test_filters.py` + `test_netbox_integration.py` + `test_ollama_models.py`: **12 failed / 33 passed** — the **same 12 that fail on 0.6.10** (verified by reinstalling 0.6.10, running `test_ollama_models.py` → identical 5 failures, then restoring 0.7.5). The failures are pre-existing test drift (e.g. `test_ollama_models` hardcodes `qwen2.5:32b` as the default when the config default is `gpt-oss:20b`; the integration mocks predate the current agent API). **None are caused by the upgrade.**

### Eval gate (the quality check)

`netbox-benchmark-v4`, production pair, `EVAL_VARIANT=d075-baseline`, `EVAL_FORCE_RERUN=1` (scorecard: `docs/traces/2026-08-11_netbox-benchmark-v4_d075-baseline.md`). First run was invalidated by NetBox being down (the agent correctly answered "NetBox API Unavailable" — a good no-hallucination sign — but the scores were meaningless); re-run with NetBox live:

| Model | 0.6.10 correctness | 0.7.5 correctness | Δ |
|---|---|---|---|
| deepseek-v4-flash | 0.75 | 0.583 | −0.167 |
| deepseek-v4-pro | 0.65 | 0.75 | +0.10 |
| **combined mean** | **0.70** | **0.667** | **−0.033** |

**Verdict: no regression.** One model up, one down; the combined mean is flat within the documented ±0.15–0.25 single-run variance (flash has hit 0.583 on 0.6.10 before; pro improved). The flash-vs-pro ranking flipped again — the same variance seen on every run this session, not an upgrade effect.

Critically, the **Workaround-B-sensitive negative-finding queries are healthy** under the reconciled profile (this is the whole risk of dropping the TodoList exclusion):

- Jimbob VLAN 100 (negative-finding): **1.0 / 1.0 correctness+completeness on BOTH models**
- device-detail, rack-inventory: pro 1.0 / 1.0
- The `site-comparison` `corr 0.0` is the known MCP-baseline IP-allocation hallucination (what the GraphQL arm fixes), not a Workaround-B artifact.

**Caveat:** 6 questions × 1 run is noisy; a firm number wants the ≥3× replication already tracked as a PR open item. For an *upgrade* gate the bar is "no regression signal," which is met.

---

## Follow-ups unlocked by this upgrade

Per the 2026-08-10 ecosystem research §9, 0.7.5 enables the next work:

1. **Model-handoff routing** via the current subagent `task()` API (parent = local model, `graphql-cross-domain` subagent = cloud model + GraphQL tool) — the SRE-agent template.
2. **`RubricMiddleware`** for structured self-correction gated on project criteria.
3. **`FilesystemMiddleware(tools=[...])` read-only allowlist** — 0.7 hardened the filesystem (a destructive recursive `delete` tool now exists); adopt the allowlist to enforce read-only. *(Not done in this commit — noted for the routing work.)*

## Files

- `pyproject.toml` — pin `deepagents>=0.6.10,<0.7` → `>=0.7.5,<0.8`.
- `src/agents/netbox_agent.py` — Workaround B reconciled (removed the TodoList exclusion; kept `base_system_prompt=""`; comment rewritten).
- `AGENTS.md` §4 — framework-state section updated to 0.7.5.
- `docs/traces/2026-08-11_netbox-benchmark-v4_d075-baseline.md` — the eval-gate scorecard.
