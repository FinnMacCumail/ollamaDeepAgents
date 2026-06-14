# LangSmith Evaluation Infrastructure Research

**Date:** 2026-06-03
**Status:** Research complete, recommendations pending implementation
**Author:** Research session via three parallel LangChain documentation deep-dives
**Purpose:** Map the May–June 2026 LangChain product announcements (Interrupt 2026 cohort) to a concrete plan for evaluating and observing this project's NetBox AI agent across multiple model variants

---

## Context

This project currently evaluates the NetBox AI agent's behaviour by:

1. Running benchmark queries interactively (`python -m src.main`)
2. Fetching the resulting LangSmith traces via the `langsmith` CLI
3. Reading the JSON by hand
4. Writing trace report markdown files in `docs/traces/`

For comparison against the `claude-agentic-sdk` reference app, the same process — fetch each side's trace, eyeball the differences, write a markdown comparison. Trace report `2026-05-26_019e63e1_two-queries-baseline-floor.md` and its postscript captured both the pattern and its limitations: comparisons turned out to be apples-to-oranges (the Claude SDK web UI's "new conversation" button doesn't reset its backend agent's accumulated 180K-210K-token conversation history), and "did this skill edit cause a regression?" was answered by drift in wall times rather than a clean pass/fail signal.

In late May 2026 LangChain announced a substantial cluster of evaluation and runtime products at their Interrupt 2026 conference. This document captures the research conducted on those products and the recommendations that emerged.

### Use case refinement during the research

Initially the comparison shape was framed as "framework A vs framework B" (DeepAgents 0.5.6 with deepseek-v4-pro:cloud vs Claude SDK with Anthropic models). After the research synthesis the requirement was sharpened to:

> Ultimately I want to compare the use of different local Ollama models (both online cloud and smaller offline ones), with occasional comparison against the Claude SDK (Anthropic) reference.

That shifts the primary axis from "two frameworks" to **"model matrix within one framework, with the other framework as occasional reference."** The implications for the recommended architecture are significant and are captured in section 5 below.

---

## 1. Offerings researched

Eight LangChain offerings were investigated across three parallel research streams:

| Offering | Category | Status (June 2026) |
|---|---|---|
| LangSmith Engine | Autonomous agent for surfacing failure patterns and proposing fixes | Public beta |
| SmithDB | Storage layer rewrite under LangSmith | GA on US Cloud |
| LangSmith Sandboxes | Hardware-virtualised microVMs for agent code execution | GA |
| Agent Development Lifecycle (ADLC) | Conceptual framework, four stages + two cross-cutting concerns | N/A (framework, not product) |
| Deep Agents 0.6 | Major version of the harness this project is built on | GA |
| Managed Deep Agents | Hosted, opinionated runtime for Deep Agents | Private beta (waitlist) |
| LangSmith Context Hub | Versioned store for non-code agent context (prompts, skills, policies) | GA |
| LangSmith web UI evaluation surface | Datasets, experiments, evaluators, comparison view | GA (long-standing, extended at Interrupt) |

---

## 2. Per-offering findings

### 2.1 LangSmith Engine

Engine is positioned as "an agent for improving agents." It attaches to a tracing project and watches incoming traces for failures (explicit errors, online-evaluator failures, latency or step-count anomalies, user feedback). It clusters these failures into named **Issues** (e.g. `agent_looping`, `incorrect_tool_args`, `pii_leak`) and produces three concrete artifact types:

- **Issues** surfaced in an Issues tab on the tracing project, with evidence traces and severity tags
- **Custom online evaluators** — code-based for structural failures or LLM-as-judge for semantic ones; Engine calls a `test_evaluator` tool before surfacing one
- **Dataset examples** — failing traces promoted into offline-eval datasets as regression entries with assertions

Issues tagged `needs_fix` are passed to a separate fix agent that drafts pull requests against a connected GitHub repo. Engine maintains a persistent `Agent Overview` memory file describing the agent's expected shape and known failure modes, learning from user accept/reject actions.

**Applicability to this project:** medium-high, but specifically for the *failure-spotting* and *evaluator-authoring* halves of the manual workflow — not for the side-by-side benchmark comparison itself. Engine attaches to a single tracing project; cross-project comparison still happens via the LangSmith evaluation harness. Adopt after the eval harness is in place, since Engine's outputs (dataset entries, evaluators) feed into the harness rather than replacing it.

**Cost / availability:** Public beta as of 2026-05-13. No pricing disclosed.

### 2.2 SmithDB

SmithDB is a Rust-based distributed database (built on Apache DataFusion and the Vortex file toolkit) that has replaced the underlying trace storage for LangSmith. It exists because modern agent traces (deeply nested spans, multimodal payloads, hour-long spans) outgrew the original store. Reported latencies: trace tree loads 92 ms P50, full-text search 400 ms P50, 12-15× faster than the previous layer.

**Applicability to this project:** none directly. SmithDB is infrastructure already serving US Cloud LangSmith traffic — this project benefits passively. The faster full-text search across large NetBox response payloads (which can be 10-50 KB JSON) is the most relevant downstream effect.

**Cost / availability:** GA on US Cloud, no separate pricing. Self-hosted rollout announced but not dated.

### 2.3 LangSmith Sandboxes

Hardware-virtualised microVMs (kernel-isolated, not just container-isolated) where agents can write code, install packages, run a shell, and persist state across long sessions. Each sandbox has its own filesystem, package manager, and network boundary; outbound credentials are injected by an Auth Proxy. Snapshots and copy-on-write forks allow cheap parallel exploration. P50 startup ~0.98 s with prewarming; can spin up hundreds in parallel via a single SDK call.

**Applicability to this project:** low directly. This project's agent doesn't currently generate-and-execute code — it calls NetBox MCP tools. Sandboxes become more relevant if:

- The QuickJS code interpreter middleware from Deep Agents 0.6 (see 2.5) is adopted and starts generating computation steps
- LangSmith Engine is adopted (Engine itself runs in Sandboxes, transparently to the user)
- Snapshot-pinned reproducible benchmark runs become desirable

**Cost / availability:** GA. Pricing not explicitly disclosed but copy-on-write semantics suggest usage-based billing.

### 2.4 Agent Development Lifecycle (ADLC)

A conceptual framework rather than a product. Four core stages plus two cross-cutting concerns:

1. **Build** — pick the altitude (framework, runtime, or harness)
2. **Test** — build representative datasets, run experiments, multi-turn evals
3. **Deploy** — durable execution, checkpointing, HITL, sandboxing
4. **Monitor** — traces, LLM-as-judge evaluators, dashboards
5. **Iterate** — move fast, don't wait for perfection
6. **Govern** (cross-cutting) — cost budgets, tool-access controls, discoverability

**Where this project sits on the lifecycle:**

| Stage | Status | Gap |
|---|---|---|
| Build | Done — DeepAgents 0.5.6 + `src/skills/` + custom HarnessProfile | None |
| Test | **Gap** — six weeks of skill tuning with hand-tested wall-time benchmarks (29.5-58.6s baselines) but no LangSmith dataset, no experiment registry, no automated regression detection | Promoting benchmark queries into a dataset is the highest-leverage gap |
| Deploy | **Gap** — `python -m src.main` is process-local, `InMemorySaver` is per-process. No durable execution, no HITL. | Adopt `PostgresSaver` checkpointer when persistence across restarts is wanted |
| Monitor | Partial — LangSmith tracing works | No LLM-as-judge layer, no latency/cost dashboards, no alerts on the wall-time tail |
| Govern | **Gap** — no tool-access policies, NetBox MCP gives broad read/write surface | Worth considering before any external user gets access |

### 2.5 Deep Agents 0.6

Major version bump of the harness this project is built on. Significant new features:

- **Code Interpreter middleware** (`deepagents[quickjs]` / `@langchain/quickjs`) — a lightweight QuickJS runtime where the agent writes JS to compose tool calls and chain sub-agents without round-tripping every intermediate result through the model. The blog claims this folds multi-call workflows into single model turns.
- **Harness Profiles as first-class abstraction** — can be diff'd, versioned, and swapped alongside the model. Built-in profiles ship for major model families including DeepSeek, Qwen, Kimi. The blog cites a 52.8% → 66.5% Terminal-Bench 2.0 score improvement from harness tuning alone on gpt-5.2-codex.
- **Streaming v3 / Agent Streaming Protocol** — unified typed event streams across messages, reasoning blocks, tool calls, subagents
- **Delta Channels** — differential checkpoint storage; 200-turn coding session compressed 5.27 GB → 129 MB
- **ContextHub backend** — versioned LangSmith-backed filesystem for skills/policies/memory
- **0.6.4–0.6.7 point releases** added `state_schema` parameter, `RubricMiddleware` for self-evaluated iteration, stable `HumanMessage` IDs across resumed threads, `read_file` pagination fix
- **Framework integrations** — `@langchain/{react,vue,svelte,angular}` v1 hooks (relevant for the future frontend UI mentioned in earlier work)

**Critical for this project:** the `read_file(path=…)` vs `file_path` bug (GitHub issues #3185 and #3188) that drove the `HarnessProfile.tool_description_overrides` workaround in commit `3b65e0c` (Workaround A) is **fixed on main**. All three examples in `READ_FILE_TOOL_DESCRIPTION` now consistently use `file_path="…"`. On upgrade to 0.6.x, that workaround becomes redundant — ~30 lines of code in `netbox_agent.py` can be removed.

**Migration risk:** medium. The 0.6 release notes are marketing-flavoured rather than a formal CHANGELOG. Branch first, regression-test against the existing benchmark suite, look at deprecation warnings, merge.

**Migration cost:** 1-3 days realistic. Skill files, MCP config, and model choice are unaffected. The bulk of work is translating the existing `HarnessProfile.tool_description_overrides` into the new first-class HarnessProfile bundle API. Note: the workaround can be deleted entirely rather than translated, since the underlying bug is fixed.

### 2.6 Managed Deep Agents

A hosted, opinionated runtime for Deep Agents, positioned by LangChain as the open alternative to Anthropic's Claude Managed Agents. Endpoints under `/v1/deepagents`. Reads agent configuration from a repo (`AGENTS.md`, `skills/`, `subagents/`, `tools.json`). Provides hosted durable execution, threads, checkpointing, managed Context Hub, managed sandbox, tool config via `tools.json` with optional human-approval gates. LangSmith Engine optionally reviews traces for improvements between runs.

**Applicability to this project:** low to none today.

Specific compatibility concerns flagged by the research:

| Question | Answer | Confidence |
|---|---|---|
| Supports custom MCP servers like netbox-mcp-server? | OSS Deep Agents Deploy explicitly accepts `mcp.json`; Managed announcement doesn't confirm. Likely yes for HTTP/SSE MCP, uncertain for stdio-only servers like this project uses. | Medium |
| Supports custom HarnessProfile / skills config? | "Keep the agent definition in your repo" suggests skills carry. HarnessProfile not explicitly mentioned. | Low |
| Supports Ollama Cloud / DeepSeek model? | OSS Deep Agents supports Ollama explicitly. Managed runtime doesn't enumerate providers. | Low |
| Pricing? | Not disclosed publicly. Private beta. | Low |

**Recommendation:** skip for now. Revisit when (a) multi-user access becomes a requirement, (b) the sibling `claude-agentic-sdk` app needs to call the NetBox agent as a remote tool, or (c) LangChain publishes pricing and a stdio-MCP/Ollama-Cloud compatibility statement.

A related-but-different offering, **OSS Deep Agents Deploy** (`deepagents deploy` CLI), is sensible if remote access becomes a need without taking on the vendor-locked Managed product. Postgres-backed memory you own; exposes MCP/A2A/Agent Protocol endpoints automatically. MIT-licensed.

### 2.7 LangSmith Context Hub

A centralised store for the **non-code context** that shapes agent behaviour — `AGENTS.md`, `SKILL.md` skill bundles, policy files, example libraries. Versioning, environment tags (`dev`/`staging`/`prod`), comment threads, rollback. Deliberately mirrors a GitHub-style workflow but outside GitHub so non-engineers (PMs, support, compliance) can contribute.

Two integration surfaces:

- **CLI push** for any bundle: `langsmith hub push <name> --type skill --dir ./skills/<name>`
- **Programmatic backend for DeepAgents** via `ContextHubBackend`:
  ```python
  from deepagents.backends import ContextHubBackend, CompositeBackend
  backend = CompositeBackend(
      routes={"/skills/": ContextHubBackend("netbox-mcp-filters")}
  )
  ```

For Claude Code / Claude SDK, the consumption pattern is via the LangSmith CLI + the `langsmith-skills` repo: `npx skills add <name> --agent claude-code --skill <skill> --yes`.

**Applicability to this project:** medium. If both the DeepAgents app and the `claude-agentic-sdk` reference app read the same canonical `netbox-mcp-filters` skill from Context Hub, the two stacks can't drift apart. Especially relevant now that model-matrix testing means many model variants run against the same skill — version `staging` → benchmark → promote to `prod` becomes a clean workflow.

**Uncertainty flag:** Claude SDK consumption is via `npx skills add` at bootstrap, not live runtime API. DeepAgents gets live re-reads via `ContextHubBackend`; Claude SDK gets a snapshot per deployment. Asymmetric but workable.

### 2.8 LangSmith web UI evaluation surface

The smith.langchain.com UI extends beyond trace viewing into a full evaluation platform. Confirmed features:

- **Datasets** — collections of `{inputs, reference_outputs, metadata}` examples, not bound to any specific tracing project
- **Experiments** — every run of a target against a dataset; captures per-example outputs, evaluator scores, traces, latency, token, cost
- **Comparison view** — side-by-side diff of experiments on the same dataset, row-by-row
- **Evaluators (four types)** — LLM-as-judge, code/heuristic, pairwise, human-in-the-loop via annotation queues
- **Reusable evaluator templates** — define once, attach to many projects
- **Online evaluators** — run continuously against live traces, scores stream into dashboards
- **Dashboards & alerts** — custom dashboards over traces with P50/P99 latency, error rate, token use, cost, feedback score; alerts via webhook or PagerDuty
- **Annotation queues** — structured human review with rubrics, multi-reviewer, progress tracking
- **Automation rules** — webhook/rule engine to act on traces (e.g., auto-add failures to a dataset)

This is the core surface this project should be using and currently isn't.

---

## 3. Key discoveries

Four things uncovered during the research that change the picture meaningfully:

### 3.1 The DeepAgents framework bug we worked around is fixed in 0.6

The `read_file(path=…)` vs `file_path` framework bug documented in trace report `2026-05-21_019e493c_skill-body-loaded.md` and worked around in commit `3b65e0c` (`HarnessProfile.tool_description_overrides`) is patched on main. GitHub issues #3185 and #3188 were closed "not planned" by maintainers, but the description-level fix appears to have shipped anyway. On 0.6 upgrade, the workaround becomes redundant and ~30 lines can be removed from `netbox_agent.py`.

### 3.2 The QuickJS code interpreter middleware could materially cut wall time

The multi-call NetBox query class (most visible example: the VLAN 100 query at 70.6s) involves multiple sequential MCP calls that the model orchestrates by round-tripping intermediate results through the LLM. A code interpreter middleware that lets the model write JS to compose those calls in one turn directly addresses this. Worth A/B testing once 0.6 is adopted.

### 3.3 `evaluate_comparative` is the official mechanism for this project's manual diff workflow

Every comparison written by hand in `docs/traces/*.md` was a one-off implementation of what `evaluate_comparative` does natively:

```python
from langsmith import evaluate
evaluate(
    (experiment_a.experiment_name, experiment_b.experiment_name),
    evaluators=[ranked_preference],
    randomize_order=True,
)
```

Set up once, run forever. Per-example pairwise judge scores. Side-by-side comparison view auto-generated.

### 3.4 Context Hub eliminates the drift risk between dual stacks (or now, between the matrix's many model variants)

Today the `netbox-mcp-filters` skill is a file in this repo. Any change to it requires that the change actually land in every model variant's run environment. With Context Hub as the source of truth, every run reads the same versioned skill — and version `staging` allows pre-merge testing.

---

## 4. Use case refinement during the research

The research initially assumed a static two-app comparison (DeepAgents vs Claude SDK). During the synthesis the requirement was sharpened to **model-matrix testing within DeepAgents, with Claude SDK as an occasional reference baseline**. Specifically:

- **Primary axis:** OLLAMA_MODEL varies across cloud frontier models (`deepseek-v4-pro:cloud`, `gpt-oss:120b-cloud`, `qwen3-coder:480b-cloud`), smaller cloud models (`gpt-oss:20b-cloud`), and local models (Ollama-served Qwen3-14B, Qwen2.5-32B, etc.)
- **Held constant:** DeepAgents 0.5.6 framework, `src/skills/` content, NetBox MCP server, validator, middleware
- **Occasional reference:** Claude SDK with Anthropic models, invoked weekly or after major changes

This refinement changes the architecture meaningfully:

| Before (framework comparison) | Now (model matrix) |
|---|---|
| 2 experiments per benchmark | N experiments per benchmark, one per model variant |
| Pairwise A-vs-B view as centerpiece | Sorted leaderboard as centerpiece, with pairwise drill-down |
| Comparison story: "which framework wins?" | Comparison story: "where's the capability/cost knee on this query class?" |
| Cross-framework trajectory eval is a real gap | Mostly disappears — same framework, comparable trace shapes |
| Trace-shape asymmetry between two stacks is a complication | Gone — all matrix runs produce identical DeepAgents-shaped traces |

The trajectory-eval gap that was flagged as the biggest research limitation **disappears for the sharpened use case**. All N variants produce uniform traces; evaluators that look at `tool_calls`, `tool_message` counts, retry cycles, etc. work across the entire matrix. "Which model planned better?" becomes a quantifiable question rather than a manual judgement.

---

## 5. Recommended architecture

### 5.1 Eval harness shape

```
Dataset (fixed: benchmark queries)
   ×
Target wrappers (one per OLLAMA_MODEL):
  - deepseek-v4-pro:cloud         (cloud, frontier)
  - gpt-oss:120b-cloud            (cloud, smaller frontier)
  - qwen3-coder:480b-cloud        (cloud, alt frontier)
  - gpt-oss:20b-cloud             (cloud, small)
  - qwen3:14b                     (local Ollama, mid)
  - qwen2.5:32b-instruct-q4_K_M   (local Ollama, larger)
  - claude-sdk-reference          (occasional, weekly cadence)
   ×
Evaluators (uniform across the matrix):
  - correctness vs ground truth (code-based)
  - completeness + reasoning (LLM-as-judge)
  - latency, token usage (auto-captured)
  - tool-call efficiency (trajectory evaluator over `tool_calls` count and shape)
```

N model × M queries × shared evaluators → one experiment per model variant, all aggregated in the LangSmith comparison view. A typical run is 5-7 models × 4-6 queries = 20-40 trials, ~30-60 minutes wall time.

### 5.2 Mechanics — model swapping

The two viable approaches:

**Option A — separate process per model run (simpler isolation):**

```python
# tests/eval/run_matrix.py
import subprocess, os

MODELS = [
    ("ollama", "deepseek-v4-pro:cloud"),
    ("ollama", "gpt-oss:120b-cloud"),
    ("ollama", "qwen3:14b"),
    ("llamacpp", "Qwen_Qwen3-14B-Q5_K_M.gguf"),
]

for backend, model in MODELS:
    env = {**os.environ, "LLM_BACKEND": backend, "OLLAMA_MODEL": model}
    subprocess.run(
        ["python", "-m", "tests.eval.run_one",
         "--experiment-prefix", f"{backend}-{model}"],
        env=env,
    )
```

Cleanest isolation; matches the current "exit and restart between queries" mental model.

**Option B — single process, N agents pre-built:**

```python
def make_target(backend: str, model_name: str):
    agent = build_netbox_agent(backend=backend, model_name=model_name)
    def target(inputs):
        return {"answer": run_query(agent, inputs["question"])}
    return target

for backend, model in MODELS:
    target = make_target(backend, model)
    client.evaluate(
        target,
        data="netbox-benchmark-v1",
        experiment_prefix=f"{backend}-{model}",
        evaluators=[correctness_judge, completeness_judge, trajectory_efficiency],
    )
```

Faster (no process startup overhead per run), but requires `build_netbox_agent()` to accept `backend` + `model_name` as authoritative parameters rather than reading env at startup.

### 5.3 The unblocking refactor

`src/agents/netbox_agent.py:NetBoxDeepAgent.initialize()` currently calls `load_config()` which reads `OLLAMA_MODEL` from env and assigns it to `self.model_name`, overriding whatever was passed to `__init__`. This blocks programmatic model swapping in a single process.

The refactor:

```python
# src/agents/netbox_agent.py
class NetBoxDeepAgent:
    def __init__(
        self,
        netbox_config=None,
        model_name=None,     # already exists but gets clobbered
        backend=None,        # already exists, reads env if None
        skills_path="src/skills",
        enable_metrics=True,
    ):
        # CHANGE: only call load_config() if the explicit params weren't supplied.
        # Today this happens unconditionally and overrides explicit args.
        ...
```

Small refactor (~30 lines). Enables Option B above. Worth doing regardless because the env coupling has caused confusion before (e.g. the previous trace report where `model=deepseek-v4-pro:cloud` was logged even though `backend=llamacpp` was active).

### 5.4 Local model practical constraints

| Path | Setup per model | Friendly for matrix testing? |
|---|---|---|
| **Local Ollama** (`ollama pull <model>`) | One-time `pull`. Daemon swaps models into VRAM on demand. | ✅ Yes — change `OLLAMA_MODEL`, daemon handles the rest |
| **Local llama.cpp** | One model per server. Multiple servers on different ports, or stop/restart with different `-m` flags. | ❌ No — matrix testing requires server orchestration |

For matrix testing, local Ollama is significantly friendlier. The current llama.cpp setup makes sense for privacy-mode production but should not be the primary local path for eval harness work.

### 5.5 Claude SDK as occasional reference

Two important constraints:

1. **Invoke via the backend Python entry, NOT the web UI.** This sidesteps the 180-210K accumulated-context confound documented in the postscript of `2026-05-26_019e63e1_two-queries-baseline-floor.md`. Every run becomes a true cold start.

2. **Run less frequently than the model matrix.** Weekly cadence, or after a model upgrade lands, or after a significant skill content change. The Claude SDK reference exists to answer "is my local Qwen catching up?" not "what's my best model today?"

```python
def target_claude_sdk(inputs):
    from claude_agentic_sdk.backend.agent import ChatAgent
    agent = ChatAgent(config)  # fresh instance per call — bypasses web UI accumulated context
    return {"answer": run_one_shot(agent, inputs["question"])}

# Run alongside model-matrix, but tagged distinctly:
client.evaluate(
    target_claude_sdk,
    data="netbox-benchmark-v1",
    experiment_prefix="claude-sdk-reference",
    evaluators=[correctness_judge, completeness_judge],
)
```

---

## 6. Tiered adoption plan

### Tier 1 — adopt immediately (highest leverage)

**Cross-stack evaluation harness via `evaluate_comparative` + dataset + per-model target wrappers.** ~1 day of work. Specifically:

1. Refactor `NetBoxDeepAgent.__init__` to make `backend` and `model_name` parameters authoritative (the unblock in 5.3)
2. Author `tests/eval/dataset.py` containing the benchmark queries already in use (multi-aspect tenant, device detail, cross-relationship, NC State racks)
3. Author `tests/eval/run_matrix.py` containing the model list and per-model `evaluate()` calls
4. Add two evaluators: one code-based correctness check, one LLM-as-judge completeness check
5. Run the matrix, review the leaderboard view in LangSmith

This replaces ~90% of the current manual workflow (fetch JSON, eyeball, write trace report). Trace reports continue to make sense for individually significant runs (breakthrough moments, regressions) but the per-run-comparison overhead drops to near zero.

### Tier 2 — adopt over next 2-4 weeks (medium leverage)

**DeepAgents 0.6 upgrade.** Removes the Workaround A from `netbox_agent.py` since the underlying framework bug is fixed. Adds QuickJS code interpreter (potential measurable wall-time reduction on multi-call queries). Adds built-in DeepSeek/Qwen HarnessProfile bundles worth A/B testing against the hand-tuned profile. Adds `RubricMiddleware` for self-evaluated iteration. Branch, regression-test against the Tier 1 eval harness, merge.

**Context Hub for skill content.** Extract `netbox-mcp-filters` skill into Context Hub, swap DeepAgents to read via `ContextHubBackend`, swap Claude SDK reference to read via `npx skills add` at bootstrap. Eliminates skill-content drift across model-matrix runs and across the dual stacks.

**LangSmith Engine on both projects.** Auto-cluster failure patterns into named issues, propose evaluators that feed back into the Tier 1 harness. Adopt after Tier 1 because Engine generates inputs to the harness rather than replacing it.

### Tier 3 — defer or skip

| Offering | Disposition | Reason |
|---|---|---|
| Managed Deep Agents | Skip until pricing + stdio-MCP + Ollama-Cloud compatibility are confirmed | Vendor lock + unknown cost + uncertain compatibility |
| Deep Agents Deploy (OSS) | Adopt only if remote access becomes a need | Single-developer interactive CLI doesn't need it yet |
| Sandboxes | Defer | NetBox MCP-based agent doesn't generate-and-execute code. Revisit if QuickJS code interpreter from 0.6 changes that pattern. |
| SmithDB | No action | Already benefiting passively on US Cloud |

---

## 7. Open questions worth answering before commit

- **Does DeepAgents 0.6 upgrade preserve our existing `HarnessProfile` shape, or does the new first-class HarnessProfile API change the constructor surface?** The release notes are marketing-flavoured; a branch test is the answer.
- **Does the QuickJS code interpreter in 0.6 have access to the NetBox MCP tools?** Almost certainly yes (it's a middleware tool with access to the agent's tool registry) but worth verifying before counting on it for wall-time reduction.
- **Does the built-in DeepSeek HarnessProfile in 0.6 beat the hand-tuned profile?** A/B test, easy once Tier 1 is in place.
- **Does Context Hub cost extra?** Not in the announcement. May be bundled with LangSmith Plus seats; may be separate.
- **Does Managed Deep Agents support stdio MCP servers like `netbox-mcp-server`?** Announcement implies HTTP/SSE only. Confirmation needed before any migration consideration.

---

## 8. Sources

LangSmith Engine, SmithDB, Sandboxes:
- [Introducing LangSmith Engine](https://www.langchain.com/blog/introducing-langsmith-engine)
- [How we built LangSmith Engine](https://www.langchain.com/blog/how-we-built-langsmith-engine-our-agent-for-improving-agents)
- [We built SmithDB, the data layer for agent observability](https://www.langchain.com/blog/introducing-smithdb)
- [LangSmith Sandboxes are Generally Available](https://www.langchain.com/blog/langsmith-sandboxes-generally-available)
- [Introducing LangSmith Sandboxes: Secure Code Execution for Agents](https://www.langchain.com/blog/introducing-langsmith-sandboxes-secure-code-execution-for-agents)
- [Sandboxes overview docs](https://docs.langchain.com/langsmith/sandboxes)
- [Everything we shipped at Interrupt 2026](https://www.langchain.com/blog/interrupt-2026-overview)

ADLC, Deep Agents 0.6, Managed Deep Agents:
- [The Agent Development Lifecycle](https://www.langchain.com/blog/the-agent-development-lifecycle)
- [Deep Agents 0.6 release notes](https://www.langchain.com/blog/deep-agents-0-6)
- [Introducing Managed Deep Agents](https://www.langchain.com/blog/introducing-managed-deep-agents)
- [Deep Agents Deploy: an open alternative to Claude Managed Agents](https://www.langchain.com/blog/deep-agents-deploy-an-open-alternative-to-claude-managed-agents)
- [The Runtime Behind Production Deep Agents](https://www.langchain.com/conceptual-guides/runtime-behind-production-deep-agents)
- [Harness capabilities docs](https://docs.langchain.com/oss/python/deepagents/harness)
- [Skills docs](https://docs.langchain.com/oss/python/deepagents/skills)
- [deepagents GitHub releases](https://github.com/langchain-ai/deepagents/releases)
- [Issue #3185 — read_file kwarg mismatch (closed but description fixed on main)](https://github.com/langchain-ai/deepagents/issues/3185)
- [LangSmith pricing](https://www.langchain.com/pricing)

Context Hub, LangSmith UI, cross-stack eval:
- [Introducing LangSmith Context Hub](https://www.langchain.com/blog/introducing-context-hub)
- [LangSmith CLI & Skills](https://www.langchain.com/blog/langsmith-cli-skills)
- [langsmith-skills GitHub repo](https://github.com/langchain-ai/langsmith-skills)
- [DeepAgents Python reference](https://reference.langchain.com/python/deepagents)
- [LangSmith Evaluation product page](https://www.langchain.com/langsmith/evaluation)
- [LangSmith Evaluation concepts (docs)](https://docs.langchain.com/langsmith/evaluation-concepts)
- [LangSmith Observability docs](https://docs.langchain.com/langsmith/observability)
- [How to run a pairwise evaluation](https://docs.langchain.com/langsmith/evaluate-pairwise)
- [evaluate_comparative SDK reference](https://reference.langchain.com/python/langsmith/observability/sdk/evaluation/)
- [Define a target function](https://docs.langchain.com/langsmith/define-target-function)
- [Easier evaluations with LangSmith SDK v0.2](https://www.langchain.com/blog/easier-evaluations-with-langsmith-sdk-v0-2)
- [Reusable Evaluators and Evaluator Templates](https://www.langchain.com/blog/reusable-langsmith-evaluator-templates)
- [langsmith-cookbook: comparing-qa.ipynb](https://github.com/langchain-ai/langsmith-cookbook/blob/main/testing-examples/comparing-runs/comparing-qa.ipynb)
- [Evaluating Deep Agents using LangSmith on AWS](https://aws.amazon.com/blogs/machine-learning/evaluating-deep-agents-using-langsmith-on-aws/)
- [Tracing Claude Code with LangSmith](https://technologuy.medium.com/tracing-claude-code-with-langsmith-full-observability-for-your-ai-coding-agent-claude-code-f175b2c5f40d)

---

## 9. Recommended next concrete step

Stand up Tier 1 — the model-matrix evaluation harness — as the first move. Specifically:

1. Refactor `NetBoxDeepAgent.__init__` parameter authority (~30 lines)
2. Create `tests/eval/dataset.py` with the existing benchmark queries (~50 lines)
3. Create `tests/eval/run_matrix.py` with the model list and evaluator wiring (~80 lines)
4. Run the matrix against an initial 3-4 model set
5. Review the LangSmith comparison view, set the baseline

Subsequent work (DeepAgents 0.6 upgrade, Context Hub adoption, Engine onboarding) becomes incremental against that baseline.

**Estimated effort to land Tier 1:** one focused day.
