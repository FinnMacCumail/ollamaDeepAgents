# Development Notes

Development decisions, session summaries, and implementation notes.

## Purpose

This directory contains:
- Development session summaries
- Implementation decisions and rationale
- Bug fixes and their analysis
- Planning documents
- Chronological development history

## Available Documents

### [2026-09-16: v5 Question Authoring Plan](2026-09-16_v5-question-authoring-plan.md)
**Plan (authoring not started):** how to author the ~90 v5 questions so they score *validly* under the four existing evaluators, and so difficulty measures reasoning rather than topic.
**Key points:**
- **Found a bug in the existing v4 set:** 4 of 6 examples have `expected_entities` their own `reference_answer` cannot match (site-comparison self-scores **0.500**), so a perfect answer cannot score 1.0 and some quoted v4 coverage numbers are depressed by an authoring bug.
- **Verified harness semantics:** `entity_coverage` strips punctuation but keeps spaces (`0%`→`0`, matching any zero; `10.112.129.0/24`→`10112129024`); `correctness_judge` scores **contradiction, not completeness**; `tool_calls` is a raw count.
- **Authoring rules:** pin scope in the question (our live cases differ 3-vs-4 and 68-vs-69 by scope); reference template = ANSWER / ACCEPTABLE VARIANTS / CONTRADICTIONS; entities 1–5, never appearing in the question, no bare integers or percentages; absence items twinned with positives; no relative time phrasing.
- **Composition:** 90 = 30 per tier × (count 7 / list 7 / value 6 / boolean 4 / explanation 3 / absence 3). Difficulty defined by *mechanism* (hops, filters, aggregation), and every tenant/domain must appear in all three tiers or the routing evaluation measures topic.
- **Two mandatory harness fixes first:** `_fetch_feedback` returns at 3 evaluators but there are 4 (can drop `correctness`); `ensure_dataset_*` is create-only so editing examples silently has no effect.
- **Statistics:** 30/tier → ±9pp SE, so only ~15–20pp effects are detectable; use paired analysis for routing comparisons.

### [2026-09-15: NetBox Data Enrichment for v5 — Research](2026-09-15_netbox-v5-data-enrichment-research.md)
**Research (live audit + 2 online threads; no data changed):** what today's NetBox data can support for v5, and what must be enriched, how, and safely.
**Key points:**
- **Unmodified v4.3 demo dump.** Rich inventory, but the relationships advanced queries need are empty: **0/72 devices with a primary IP, 0/180 IPs on interfaces, 62/69 active prefixes empty, 0 VLAN assignments, 0/180 VMs with resources, 0 change-log rows, 100% `active`**.
- **Archetype score:** ADVANCED tier only **3/10 answerable** (5 degenerate, 2 impossible). SIMPLE/MEDIUM are mostly fine.
- **Strategy: additive new tenant** ("Halvorsen Logistics": ~6 sites / ~74 devices / ~200 IPs / ~250 cables / 14 circuits / 30 VMs) in 10.60.0.0/16, with a **17-item planted-defect answer key**. Keeps v4 valid; avoid VID 100 and patch one global "180 IPs" sentence in the v4 reference.
- **Toolchain:** idempotent **pynetbox 7.5.0** REST seed (the only reproducible path that writes the change log); `trace_paths` + `reindex`; pin to a **`pg_dump -Fc` snapshot**; gold answers computed by script with a read-only token.
- **Prerequisites found:** job-queue Valkey AOF corrupt (worker down, `/api/status/` returns 500); `CHANGELOG_RETENTION` unset (90-day pruning); **agent token is a write-enabled superuser** (should be view-only + `write_enabled=false`); a demo reload wipes tokens.
- **4.3 gotchas:** no API backdating; `changelog_message` is 4.4+; containers count only same-VRF children; rack utilization counts reservations.
- **Does the additive tenant satisfy v5? (§5.1)** Yes, conditionally — coverage and volume are met (~45–60 ADVANCED candidates vs a 30–50 target). Binding condition: **tiers must cross both data islands** (some SIMPLE questions on HVL, some MEDIUM/ADVANCED on demo data), or the tenant name becomes a proxy for difficulty and routing can be gamed. Plus: cap near-duplicates, include the P3 domains for full coverage, scope audits to the tenant.

### [2026-09-15: netbox-benchmark-v5 Dataset Expansion Design](2026-09-15_netbox-benchmark-v5-expansion-design.md)
**Design (spec, not yet built):** how far to expand the eval dataset (currently 6 examples) and on what basis — for trustworthy A/B numbers AND to serve the upcoming model-handoff routing (which needs difficulty-graded examples).
**Key points:**
- **6 is too small** on three grounds: statistical (n=6 → 95% CI ±0.32–0.40), coverage (whole NetBox domains untested), stratification (1 example/category = no per-tier routing signal).
- **Target: ~90–150 examples, stratified 30–50 per difficulty tier** (simple/medium/advanced), from a ~22-archetype coverage checklist. Two free power levers: **paired test** (same questions across arms) + **breadth-over-replication** (more questions beats more runs).
- **Difficulty taxonomy = the routing decision**; objective discriminator = NetBox's no-multi-hop-filter rule. Negative-finding + capacity-math queries are where cheap models fail → weight for escalation tests.
- **Data-enrichment prerequisite:** demo data too thin for the advanced tier — expansion + enrichment go together.
- **Measured cost (timing probe):** 6-q pair = 12m44s / ~1.86M tokens; **90-q pair run ≈ 3.2 hrs / ~28M tokens** (≈$0 on flat-rate Pro). Expanding lets replication drop from 3× → 1–2×.

### [2026-08-11: DeepAgents 0.6.10 → 0.7.5 Upgrade](2026-08-11_deepagents-0.7.5-upgrade.md)
**Execution:** Crosses the 0.7.0 major (also bumps langchain 1.3.9→1.3.14, langchain-core 1.4.7→1.5.3, langsmith 0.8.15→0.10.17). Tracks the current subagent + `RubricMiddleware` APIs for the planned model-handoff routing.
**Key points:**
- **One breaking change:** 0.7.0 makes planning opt-in, so `TodoListMiddleware` isn't bundled — and 0.7.x strictly errors when `excluded_middleware` matches nothing. **Workaround B reconciled:** removed the TodoList exclusion (suppression is now inherent), kept `base_system_prompt=""` as belt-and-suspenders.
- Workaround B API (`HarnessProfile`/`register_harness_profile`) survived; agent builds, skills load.
- **Regression-neutral** (12 unit failures all pre-exist on 0.6.10, proven by reinstall-and-compare).
- **Eval gate passed:** no correctness regression vs the 0.6.10 baseline (combined mean 0.70→0.667, flat within variance; flash −0.167, pro +0.10). Negative-finding queries healthy (Jimbob VLAN 100 = 1.0/1.0 both models).
- `langchain-quickjs 0.2.0` now pins `<0.7` — harmless (deferred package, only used by `tests/spike/`).

### [2026-08-10: LangChain Ecosystem vs. the NetBox Cloud Platform MCP](2026-08-10_langchain-ecosystem-vs-netbox-cloud-platform.md)
**Research (5 parallel agents):** maps the current (Aug 2026) LangChain/LangGraph/DeepAgents/LangSmith ecosystem against NetBox Labs' Cloud-only "Platform MCP Server" to decide what's reproducible on this self-hosted, read-only stack.
**Key points:**
- Cloud's edge = tool breadth (~100 tools) + Code Mode, both of which only pay off at that breadth. **Code Mode reconfirmed "skip"** (Anthropic τ²-bench: sequential single-call workloads gain nothing, ~8% more cost) — the **already-shipped GraphQL tool is the right lever** for round-trips.
- Reproducible & self-hostable: **subagents** (scoping + the planned model-handoff routing — the Aug-5 LangChain "SRE agent" blog is the blueprint), **Skills** (already in use), **`RubricMiddleware`** (structured self-correction), server-side tool generation from NetBox OpenAPI/GraphQL (LangChain can't add tools mid-run, #33808).
- **Skip** all hosted products (Managed Deep Agents, LLM Gateway, Context Hub, hosted LangSmith) under the privacy mandate; use `openevals`/`agentevals` (MIT) + OTel for on-prem eval parity.
**Actionable task (§8):** upgrade `deepagents` 0.6.10 → **0.7.5** (crosses the 0.7.0 major: planning opt-in, empty base prompt ~65% token cut, `FilesystemMiddleware` read-only allowlist) — behind the eval gate. ~½–1 day.

### [2026-07-20: NetBox GraphQL Read Tool (PRP 1)](2026-07-20_netbox-graphql-read-tool.md)
**Execution:** First PRP-driven feature since the harvested PRP workflow was added. Adds two standalone **read-only** GraphQL tools (`netbox_graphql`, `netbox_graphql_schema`) so the agent can retrieve nested/cross-model data in one server-side request instead of multi-hop MCP decomposition.
**Key points:**
- Standalone tools appended in `netbox_agent.py` — NOT wrapped by `NetBoxToolWrapper`, so they bypass `FilterValidator` by design (GraphQL has its own grammar).
- Read-only via `graphql-core` AST inspection (mutations/subscriptions/malformed rejected before any HTTP); but the *primary* safety surface is query-cost limits (depth/size/timeout), since the endpoint is read-only server-side anyway.
- Live-verified: introspection enabled; legacy `Authorization: Token` auth; 4.3/4.4 Strawberry filter grammar (bare `id: 6`, string `{exact:}`, `<model>_list` roots).
- 23/23 new unit tests pass; regression-neutral (same 7 pre-existing integration failures with/without the change).
**Not done (PRP 2):** routing skill + GraphQL-vs-MCP A/B on `netbox-benchmark-v3`. No performance claim yet.

### [2026-06-14: DeepAgents 0.5.6 → 0.6.10 Upgrade](2026-06-14_deepagents-0.6-upgrade.md)
**Execution:** First Tier 2 item from the LangSmith eval research executed. Upgrades `deepagents` from 0.5.6 → 0.6.10 (also bumps langchain 1.2.17→1.3.9, langgraph 1.1.10→1.2.5, langsmith 0.8.0→0.8.15).
**Key findings:**
- Workaround A (the `read_file(path=…)` framework bug from issues #3185/#3188) removed — upstream fix shipped; ~50 lines deleted from `netbox_agent.py`
- Workaround B added — 0.6 silently appends ~9.6K chars of new system-prompt content (`BASE_AGENT_PROMPT` + `TASK_SYSTEM_PROMPT` + `WRITE_TODOS_SYSTEM_PROMPT`) that actively regress quality on negative-finding queries
- Empirical regression on `netbox-benchmark-v2` VLAN 100 query: entity 1.00→0.40, completeness 1.00→0.00. Root cause traced via sub-run chronology — penultimate LLM call had perfect answer; TodoListMiddleware's "answer-after-last-write_todos" instruction forced an extra finishing turn that produced "All done. Let me know..." overwriting it.
- Fix: `HarnessProfile(base_system_prompt="", excluded_middleware=frozenset({"TodoListMiddleware"}))` registered for ollama and openai providers. Quality restored to 0.5.6 baseline (entity 0.95 / completeness 1.00).
**Trade-offs:** Aggregate latency +22% (34.6s → 42.3s) concentrated on VLAN 100. Likely candidates for the residual hedging: `SubAgentMiddleware`'s prompt addition or `PatchToolCallsMiddleware`. (Update 2026-06-15: QuickJS spikes confirmed PTC is NOT the fix for this — the model won't use `eval` on this workload. See `2026-06-03_quickjs-code-interpreter-research.md` §16 for the actual recommended levers, starting with suppressing `SubAgentMiddleware`'s `TASK_SYSTEM_PROMPT`.)
**Bonus:** `tests/eval/run_matrix.py` gained `EVAL_FORCE_RERUN=1` env override during this work — useful for future regression validation.

### [2026-06-08: Self-Hosting Frontier LLMs — Open Weights & GPU Rental Research](2026-06-08_self-hosting-gpu-rental-research.md)  ·  *Updated 2026-06-30 (strict-privacy addendum)*
**Research:** Open-weights audit and self-host feasibility for the 5 top models from the `netbox-benchmark-v2` 10-model cloud sweep, plus current (June 2026) GPU rental pricing and inference-stack recommendations.
**⚠️ 2026-06-30 addendum (operative):** the project now has a **strict data-privacy mandate**, which *reverses* the original "self-hosting is irrational on cost" conclusion. Key points: rented cloud GPU is still third-party hardware (may fail a strict residency mandate — decision tiers in the addendum); DeepSeek-V4-Flash's 160 GB load tax forces **always-on** for interactive use (~$600/mo budget 5090-offload, ~$1,020/mo RTX Pro 6000 INT4, ~$3,460/mo 2× H200); for true on-prem residency the standout is an **owned Mac Studio M3 Ultra 512GB (~$10–15k, ~20 tok/s, breaks even vs rental in 3–18 months)** or a ~$5–6k RTX 5090 workstation.
**Confidentiality vs residency (§A.5):** "strict" splits into *confidentiality* (no third party may read our data) vs *residency* (bytes physically stay with us) — different correct answers. The deciding factor for hired GPU is **where the GPU is** (that's where the data is processed), not who owns the VM. For confidentiality there's a real rented-GPU answer — **Confidential Computing** (CC-mode GPU + CPU TEE + attestation, host can't read VRAM) — but Hopper CC is **single-GPU only** (no NVLink encryption), so full-precision DeepSeek-V4-Flash can't run confidentially today; feasible config is **INT4 on a single confidential H200** (Phala ~$2,340–3,500/mo). For residency, only owned hardware qualifies. Open item: confirm which privacy tier/flavour applies before purchase.
**Key findings (original, 2026-06-08):**
- 4 of 5 leaderboard winners have open weights (DeepSeek-V4-Flash MIT, DeepSeek-V4-Pro MIT, Nemotron-3-Ultra OpenMDW, GLM-5 MIT); MiniMax-M3 weights expected ~2026-06-11
- Correction: Nemotron-3-Ultra is 550B/55B MoE hybrid Mamba-Transformer, NOT a 340B dense model as earlier speculated
- DeepSeek-V4-Flash is the standout self-host candidate — 158-160 GB FP4+FP8 native, runs on 2× H200 at 266 tok/s, or 1× RTX 5090 + 256GB DDR5 via KTransformers at 20+ tok/s
- Cheapest credible H100 rental: Thunder Compute $1.38/hr; cheapest H200: Hyperbolic $2.15/hr
- VRAM math now anchored to 64K context (peak observed in v2 benchmark = 55,264 tokens on the multi-aspect Dunder Mifflin query); GPU tier recommendations don't shift vs. earlier 32K assumption because DeepSeek/GLM/Nemotron all use compressed attention architectures (CSA+HCA / DSA / hybrid Mamba)
- For single-user NetBox workload (~50-200 queries/mo), self-hosting is financially irrational vs. Ollama Cloud Pro ($30/mo) unless privacy, quota frustration, or specific model curiosity applies
**Recommendations:** "Easiest credible spike" = 1× RTX 5090 + KTransformers (~$10 half-day cost). "Production-grade spike" = 2× H200 SGLang FP4+FP8 (~$20 half-day cost). Don't replace Ollama Cloud daily on cost grounds alone.

### [2026-06-03: QuickJS Code Interpreter Middleware Research + Spikes](2026-06-03_quickjs-code-interpreter-research.md)
**Research + 3 verification spikes (executed 2026-06-15).** Deep-dive on DeepAgents 0.6's `CodeInterpreterMiddleware` (`langchain-quickjs`) PTC, followed by empirical spikes against the real NetBox MCP server on `deepseek-v4-flash:cloud`. Spike scripts in `tests/spike/`.
**DECISION: defer adoption** — mechanism works, but no benefit for the current single-source sequential NetBox workload.
**Spike outcomes:**
- **Spike 1 (MCP→PTC bridge): ✅ works.** MCP tools auto-bridge as `tools.netboxGetObjects(...)` (camelCase), real round-trip, counts as one outer tool call. No adapter needed.
- **Spike 2 (error recovery): ✅ works — prediction was wrong.** `FilterErrorRecoveryMiddleware` DOES see PTC errors (it wraps `_arun()`, which PTC calls). Bad filters surface as recoverable `TOOL_VALIDATION_ERROR` strings. No skill `try/catch` rewrite needed.
- **Spike 3 (wall-time): ❌ no benefit.** The model **never invoked `eval`** on the VLAN 100 query (0 eval, 21 direct calls); the with-PTC variant was **+13.7% slower** purely from prompt-bloat tax. Confirms Anthropic's τ²-bench finding that sequential single-call workflows don't benefit. The original "70s → 20-30s" projection is invalidated.
**Re-trigger conditions (§15):** re-investigate (~½ day, Spikes 1+2 don't need re-running) when the app gains ≥10 tools, ≥2 independent data sources queryable in parallel (most likely for a multi-source app), cross-source joins composed in code, or large result sets needing pre-filtering. Any future adoption must *steer* the model to `eval` via skill/prompt content — it won't use PTC on its own.
**Residual VLAN-100 latency (§16):** PTC is not the fix. Better levers: suppress `SubAgentMiddleware`'s `TASK_SYSTEM_PROMPT` (~½ day), an MCP-server-side composite query, or teaching parallel native tool calls in the skill.
**Notes:** `langchain-quickjs` 0.2.0 (2026-06-12) dropped `skills_backend`, added `subagents: bool = True` default `task` bridge. Open issue #3926 (PTC + `{field: undefined}` Pydantic failure) is a latent MCP risk for future adoption.

### [2026-06-03: LangSmith Evaluation Infrastructure Research](2026-06-03_langsmith-evaluation-research.md)
**Research:** Eight LangChain offerings from Interrupt 2026 (Engine, SmithDB, Sandboxes, ADLC, Deep Agents 0.6, Managed Deep Agents, Context Hub, LangSmith UI evaluation surface) mapped to a concrete model-matrix evaluation plan for this project.
**Key findings:**
- DeepAgents 0.6 fixes the framework bug Workaround A (commit `3b65e0c`) was patching — upgrade lets us delete ~30 lines
- QuickJS code interpreter middleware in 0.6 could materially shrink wall time on multi-call queries (the 70.6s VLAN-class slow case) — drilled into separately in `2026-06-03_quickjs-code-interpreter-research.md`
- `evaluate_comparative` is the official mechanism for the cross-stack/cross-model diff workflow currently done by hand
- Context Hub eliminates skill-content drift across model-matrix runs and across dual stacks
**Use case refined:** primary axis is now "model matrix within DeepAgents" rather than "framework A vs framework B" — Claude SDK becomes an occasional reference baseline
**Recommendations:** Tier 1 (this week): stand up the model-matrix evaluation harness. Tier 2: Deep Agents 0.6 upgrade, Context Hub, Engine. Tier 3: skip Managed Deep Agents and Sandboxes for now.

### [2026-05-05: Claude SDK Comparison](2026-05-05_claude-sdk-comparison.md)
**Analysis:** Comparing Claude SDK implementation with DeepAgents
**Key findings:**
- Claude SDK has more comprehensive system prompt with field optimization
- Better output formatting guidelines (tables, ASCII art)
- Evidence suggests netbox-mcp-filters skill not yet triggered in traces
**Recommendations:** Adopt Claude SDK's system prompt patterns

### [2026-05-04: Streaming Fix](2026-05-04_streaming-fix.md)
**Problem:** Messy output with 7+ chunks for simple queries
**Solution:** Filter streaming to only yield final AI responses
**Impact:** Clean single-chunk output, 11% faster performance

Key insights:
- `stream_mode="values"` yields all message types
- Filter logic: only AI messages with content, no tool_calls
- Full tracing still preserved in LangSmith

### [2026-02-09: Session Summary](2026-02-09_session-summary.md)
**Problem:** Tool wrapper signature errors, model compatibility
**Solutions:**
- Fixed wrapper to accept positional arguments
- Identified model compatibility issues
- Tested multiple Ollama models

Key insights:
- LangChain invokes tools with positional args
- Some models require specific prompting patterns
- Validation middleware catches filter errors early

### [Initial Planning](initial-planning.md)
Original feature specification and architecture planning:
- Requirements and goals
- DeepAgents framework selection
- Skills system design
- MCP integration approach

## Development Timeline

| Date | Topic | Document |
|------|-------|----------|
| 2026-08-10 | LangChain ecosystem vs NetBox Cloud Platform MCP | [2026-08-10_langchain-ecosystem-vs-netbox-cloud-platform.md](2026-08-10_langchain-ecosystem-vs-netbox-cloud-platform.md) |
| 2026-07-20 | NetBox GraphQL read tool (PRP 1) | [2026-07-20_netbox-graphql-read-tool.md](2026-07-20_netbox-graphql-read-tool.md) |
| 2026-06-15 | QuickJS PTC spikes — decision: defer | [2026-06-03_quickjs-code-interpreter-research.md](2026-06-03_quickjs-code-interpreter-research.md) |
| 2026-09-15 | NetBox data enrichment for v5 — research | [2026-09-15_netbox-v5-data-enrichment-research.md](2026-09-15_netbox-v5-data-enrichment-research.md) |
| 2026-09-15 | netbox-benchmark-v5 dataset expansion design | [2026-09-15_netbox-benchmark-v5-expansion-design.md](2026-09-15_netbox-benchmark-v5-expansion-design.md) |
| 2026-08-11 | DeepAgents 0.6.10 → 0.7.5 upgrade | [2026-08-11_deepagents-0.7.5-upgrade.md](2026-08-11_deepagents-0.7.5-upgrade.md) |
| 2026-06-14 | DeepAgents 0.5.6 → 0.6.10 upgrade | [2026-06-14_deepagents-0.6-upgrade.md](2026-06-14_deepagents-0.6-upgrade.md) |
| 2026-06-08 | Self-hosting GPU rental research | [2026-06-08_self-hosting-gpu-rental-research.md](2026-06-08_self-hosting-gpu-rental-research.md) |
| 2026-06-03 | QuickJS code interpreter middleware research | [2026-06-03_quickjs-code-interpreter-research.md](2026-06-03_quickjs-code-interpreter-research.md) |
| 2026-06-03 | LangSmith eval research & model-matrix plan | [2026-06-03_langsmith-evaluation-research.md](2026-06-03_langsmith-evaluation-research.md) |
| 2026-05-05 | Claude SDK comparison | [2026-05-05_claude-sdk-comparison.md](2026-05-05_claude-sdk-comparison.md) |
| 2026-05-04 | Streaming output fix | [2026-05-04_streaming-fix.md](2026-05-04_streaming-fix.md) |
| 2026-02-09 | Tool wrapper & model testing | [2026-02-09_session-summary.md](2026-02-09_session-summary.md) |
| Initial | Project planning | [initial-planning.md](initial-planning.md) |

## Key Learnings

### Framework Integration

**DeepAgents 0.5.6 vs 0.3.12:**
- Significant improvements in summarization
- Better async support
- More reliable streaming
- Worth upgrading

**llama.cpp vs Ollama:**
- llama.cpp: Better for production (more control)
- Ollama: Easier for development (simpler setup)
- Both work well with OpenAI-compatible API

### Performance Patterns

**Typical Query Flow:**
1. LLM Call 1: Tool selection (~20s)
2. Tool Execution: NetBox MCP (~1-2s)
3. LLM Call 2: Response formatting (~13-20s)

**Optimization Opportunities:**
- Prompt caching saves ~20K tokens per query
- Smaller models for simple queries
- GPU acceleration for faster inference

### Common Issues

**Filter Constraints:**
- Django ORM patterns don't work
- Multi-hop relationships require two-step queries
- Skills system provides automatic recovery

**Streaming:**
- `stream_mode="values"` shows all internal state
- Filter message types before yielding to users
- Preserves full tracing in LangSmith

**Model Selection:**
- 7B models: Fast but lower quality
- 14B models: Best balance
- 32B+ models: Best quality, slower

## Contributing

When adding development notes:

### File Naming
Use format: `YYYY-MM-DD_<topic>.md`

Examples:
- `2026-05-04_streaming-fix.md`
- `2026-05-10_gpu-optimization.md`
- `2026-06-01_new-middleware.md`

### Document Structure
```markdown
# Title: Brief Description

**Date:** YYYY-MM-DD
**Status:** ✅ Completed / 🚧 In Progress / ❌ Failed

## Problem

[Clear description of the issue]

## Investigation

[What was explored and discovered]

## Solution

[What was implemented]

## Impact

[Results and metrics]

## Lessons Learned

[Key takeaways]
```

### What to Document

**Do document:**
- Non-obvious solutions
- Performance improvements
- Bug fixes with analysis
- Architecture decisions
- Failed approaches (what NOT to do)

**Don't document:**
- Routine updates
- Trivial bug fixes
- Changes already in git commits

## Cross-References

Development notes often reference:
- [Trace Analysis](../traces/) - Performance data
- [Reference](../reference/) - Technical specs
- [Guides](../guides/) - Implementation details
- [Setup](../setup/) - Configuration changes

## Archive Policy

Documents are moved to [Archive](../archive/) when:
- No longer relevant to current implementation
- Superseded by newer approaches
- Historical interest only

Currently active documents stay here for easy reference.

---

**Maintained by:** Development team
**Last Updated:** 2026-06-30
