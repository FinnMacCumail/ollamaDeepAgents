# Multi-Repo Update Plan — rtf-research × deepagents × ollamaDeepAgents

**Date:** 2026-06-22
**Status:** Plan approved; execution in progress (Stage 0/1 underway)
**Purpose:** Coordinate updates across three related repositories so that the
`ollamaDeepAgents` work (DeepAgents 0.6 production build, dual local/cloud models,
LangSmith model-matrix evaluation, observability) is properly published and narrated as the
next chapter of the RTF AI research programme.

**Scope:** three GitHub repos under `FinnMacCumail`. This doc is the single coordinating
artifact; per-repo execution details live in their own commits.

---

## 1. The three repos and how they relate

```
   deepagents  ───────(superseded by)───────►  ollamaDeepAgents
   (OLD: NetBox agent on                        (NEW: NetBox agent on
    vendored DeepAgents 0.0.5,                   packaged DeepAgents 0.6.10,
    Anthropic-cloud-only)                        dual Ollama/llama.cpp + cloud,
        ▲                                        LangSmith eval harness)
        │                                              ▲
        │  Phase 4 link (historical)                   │  Phase 5 link (new)
        └────────────────────┬─────────────────────────┘
                       rtf-research
                  (MkDocs portfolio / research hub —
                   narrates the evolution)
```

| Repo | Local path | GitHub | Role |
|---|---|---|---|
| `rtf-research` | `/home/ola/dev/rnd/ai-research-2025` | `FinnMacCumail/rtf-research` | Portfolio hub (MkDocs → Pages). Links to both implementation repos. |
| `deepagents` | `/home/ola/dev/rnd/deepagents` | `FinnMacCumail/deepagents` | The **old** NetBox agent. Direct ancestor of ollamaDeepAgents. Cited by rtf-research Phase 4. |
| `ollamaDeepAgents` | `/home/ola/dev/netboxdev/ollamaDeepAgents` | `FinnMacCumail/ollamaDeepAgents` (created 2026-06-22) | The **new** production evolution. This repo. |

**Decision:** three public repos with the evolution narrated. The old `deepagents` repo is
NOT rebuilt in place (it would mean recreating ollamaDeepAgents) — instead it gets a
forward-pointer + asset harvest, and rtf-research documents the progression as a new phase.

---

## 2. Current state (from deep appraisals, 2026-06-22)

### rtf-research
- MkDocs Material research portfolio; ~57 md files / ~54k words. Thesis: *systematic
  anti-hallucination in domain-specific LLM apps*.
- Four completed phases + three planned. **Current frontier: Phase 4 — DeepAgents vs Claude
  SDK framework comparison.**
- **Gaps relevant to our work:**
  - **LangSmith: entirely absent** (0 files).
  - **Model-matrix benchmarking: absent.**
  - **Local vs cloud: only a documented FAILURE** — ADR-0027 records a reverted Ollama/LiteLLM
    + Claude-SDK experiment ("6 hours, reverted to Anthropic-only").
  - **Observability: conceptual only** — DIY Prometheus/OTel in `production-considerations.md`;
    no managed LLM-tracing platform named.
- **Pre-existing bugs to fix while here:** (a) `gh-pages.yml` deploys on `main` but the repo's
  branch is `master`; (b) 11 ADRs (0003–0012, 0027) exist on disk but are missing from the
  mkdocs ADR nav; (c) `RESEARCH_LOG.md` is stale since 2025-09-22.

### deepagents
- Vendored fork of `langchain-ai/deepagents` (0.0.5-era) repurposed into a NetBox chatbot.
  **Direct lineal ancestor of ollamaDeepAgents.**
- Anthropic-cloud-only, hardcoded `claude-sonnet-4-*`, no eval harness.
- **Stale flags:** deprecated model names; obsolete `USE_V1_CORE` env flag; CLAUDE.md/AGENTS.md
  reference files that no longer exist (`sub_agent.py`, `create_react_agent`, `_create_task_tool()`);
  brittle monkeypatched caching; hardcoded absolute paths. `.env` is gitignored/untracked (safe).
- **Unique assets worth preserving** (harvest list in §4).

### ollamaDeepAgents (this repo)
- DeepAgents 0.6.10, dual Ollama/llama.cpp + Ollama Cloud frontier models, LangSmith
  model-matrix eval harness (`tests/eval/`), custom filter-recovery middleware, skills system.
- History is key-safe (LangSmith key scrubbed from all commits via `git filter-repo`, 2026-06-22).
- Docs freshly audited and current (CLAUDE.md, AGENTS.md, full docs/ sweep).

---

## 3. The evolution narrative (the research spine)

ollamaDeepAgents specifically advances/refutes prior rtf-research findings — this is what makes
it a research result, not just an engineering update:

| Prior finding (rtf-research) | What ollamaDeepAgents demonstrates |
|---|---|
| **ADR-0027:** local models via LiteLLM+Claude-SDK failed; reverted to Anthropic-only | Local **and** cloud models work cleanly via Ollama's **native** backend (no proxy). `deepseek-v4-flash:cloud` matches Claude quality at ~36% lower latency. **Negative result → positive methodology.** |
| **Phase 4:** "framework choice is context-dependent" | A production DeepAgents build on 0.6.10, with the framework-evolution maintenance saga (0.6 upgrade regressions; Workaround A removed; Workaround B added) as a real case study. |
| **Total gap:** no LangSmith, no model-matrix benchmarking, observability only conceptual | A full LangSmith model-matrix eval harness, 10-model cloud sweep, automated scoring, and trace-driven regression diagnosis (the TodoListMiddleware "All done" corruption found via sub-run analysis). |

---

## 4. Staged execution plan

### Stage 0 — ollamaDeepAgents → public *(prerequisite; user-triggered)*
- Repo created: `https://github.com/FinnMacCumail/ollamaDeepAgents`.
- History already key-safe. Wire `origin`, push. **Output: the canonical URL the other two repos link to.**
- The actual `git push` is confirmed with the user before running (irreversible public action).

### Stage 1 — deepagents: harvest & supersede *(~½–1 day; most URL-independent)*

**Harvest mapping** (deepagents → ollamaDeepAgents, with provenance notes):

| Source (in `deepagents`) | Destination (in `ollamaDeepAgents`) | Why keep |
|---|---|---|
| `docs/guides/context-engineering-report.md` | `docs/reference/context-engineering.md` | Citation-backed synthesis (Offload/Reduce/Retrieve/Isolate/Cache) |
| `examples/netbox/docs/netbox/reports/NO_SUBAGENTS_RATIONALE.md` | `docs/reference/no-subagents-rationale.md` | Empirical justification for subagents-off design |
| `examples/netbox/docs/netbox/analysis/TOOL_REMOVAL_RESULTS.md`, `VALIDATION_RESULTS_SUMMARY.md` | `docs/reference/` (harvested-findings) | Empirical findings that justify current design |
| `PRPs/templates/prp_base.md` + `.claude/commands/{generate,execute}-prp.md` | `.claude/commands/` + `docs/development/` | Reusable PRP planning methodology |
| `examples/netbox/analysis_tools/*.py` (7 trace scripts) | `tests/manual/legacy-trace-tools/` | Precursors to the eval harness; provenance for the observability story |

**Supersede + hygiene** *(URL-dependent bits after Stage 0):*
- README "⚠️ Superseded by → ollamaDeepAgents" banner with link.
- Fix deprecated model names, drop obsolete `USE_V1_CORE` flag, fix CLAUDE.md/AGENTS.md refs to deleted files.
- (Optional) prune stale experiment branches + checked-out `venv/` bloat.

### Stage 2 — rtf-research: new Phase 5 + methods + ADRs *(HIGH effort, main body)*

**New phase** `docs/phases/phase-5-production-deepagents/`:
- `overview.md` — production build thesis: local+cloud frontier models on DeepAgents 0.6 with observability.
- `multi-model-evaluation.md` — the 10-model cloud matrix; deepseek-flash-vs-pro; local-models-too-weak; **explicitly reconciles ADR-0027**.
- `observability-and-monitoring.md` — LangSmith eval harness, model-matrix scoring, the trace-driven regression diagnosis case study.
- `lessons-learned.md` — 0.6 upgrade saga, Workaround B, the QuickJS/PTC investigation (mechanism works, deferred — a "negative result done right").

**New methods** (the thin `methods/` section):
- `methods/observability.md` — LangSmith tracing + eval methodology.
- `methods/benchmarking.md` — model-matrix benchmarking (entity-coverage / LLM-judge / trajectory evaluators).

**New ADRs (0028+):** native-Ollama local+cloud (supersedes ADR-0027) · LangSmith as observability
platform · model-matrix eval harness adoption · DeepAgents 0.6 upgrade + Workaround B · QuickJS PTC deferral.

**Housekeeping:** mkdocs nav (add new sections + fix 11 unlinked ADRs) · fix `gh-pages.yml`
`main`→`master` · append `RESEARCH_LOG.md` + `CHANGELOG.md [Unreleased]` · refresh README phase
list + `index.md` Mermaid timeline. Phase 5 links finalized after Stage 0.

---

## 5. Sequencing dependencies

- **Stage 0 gates the URL-dependent links** in Stage 1 (supersede banner) and Stage 2 (Phase 5 link).
- Stage 1 **harvest** and Stage 2 **content authoring** are URL-independent — can proceed before the push.
- Order of execution: plan doc → Stage 1 harvest → (user creates repo ✓) → push → finalize banner + Phase 5 links → Stage 2 body.

---

## 6. Effort summary

| Stage | Effort | Notes |
|---|---|---|
| 0 — publish ollamaDeepAgents | Low | one push; history already safe |
| 1 — deepagents harvest & supersede | ½–1 day | mostly file moves + a banner + hygiene |
| 2 — rtf-research Phase 5 | HIGH (multi-session) | ~6–9 new doc files, 4–5 ADRs, housekeeping; grows corpus ~12–15% |

---

## 7. Status tracker

- [x] Deep appraisal of both target repos
- [x] Topology + approach decided (3 public repos, evolution narrated, harvest-and-supersede)
- [x] ollamaDeepAgents GitHub repo created (`FinnMacCumail/ollamaDeepAgents`)
- [x] This plan doc written
- [x] Stage 1 harvest — `docs/lineage/` (4 docs + README), `tests/manual/legacy-trace-tools/`
      (7 scripts + README), `.claude/commands/` (PRP slash-commands), `PRPs/` (template + README)
- [ ] ollamaDeepAgents pushed public ← *next; needs user go-ahead on the push*
- [ ] Stage 1 supersede banner + hygiene (URL-dependent bits)
- [ ] Stage 2 rtf-research Phase 5 + methods + ADRs + housekeeping
