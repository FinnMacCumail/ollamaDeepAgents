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

### [2026-06-14: DeepAgents 0.5.6 → 0.6.10 Upgrade](2026-06-14_deepagents-0.6-upgrade.md)
**Execution:** First Tier 2 item from the LangSmith eval research executed. Upgrades `deepagents` from 0.5.6 → 0.6.10 (also bumps langchain 1.2.17→1.3.9, langgraph 1.1.10→1.2.5, langsmith 0.8.0→0.8.15).
**Key findings:**
- Workaround A (the `read_file(path=…)` framework bug from issues #3185/#3188) removed — upstream fix shipped; ~50 lines deleted from `netbox_agent.py`
- Workaround B added — 0.6 silently appends ~9.6K chars of new system-prompt content (`BASE_AGENT_PROMPT` + `TASK_SYSTEM_PROMPT` + `WRITE_TODOS_SYSTEM_PROMPT`) that actively regress quality on negative-finding queries
- Empirical regression on `netbox-benchmark-v2` VLAN 100 query: entity 1.00→0.40, completeness 1.00→0.00. Root cause traced via sub-run chronology — penultimate LLM call had perfect answer; TodoListMiddleware's "answer-after-last-write_todos" instruction forced an extra finishing turn that produced "All done. Let me know..." overwriting it.
- Fix: `HarnessProfile(base_system_prompt="", excluded_middleware=frozenset({"TodoListMiddleware"}))` registered for ollama and openai providers. Quality restored to 0.5.6 baseline (entity 0.95 / completeness 1.00).
**Trade-offs:** Aggregate latency +22% (34.6s → 42.3s) concentrated on VLAN 100. Likely candidates for the residual hedging: `SubAgentMiddleware`'s prompt addition or `PatchToolCallsMiddleware`. (Update 2026-06-15: QuickJS spikes confirmed PTC is NOT the fix for this — the model won't use `eval` on this workload. See `2026-06-03_quickjs-code-interpreter-research.md` §16 for the actual recommended levers, starting with suppressing `SubAgentMiddleware`'s `TASK_SYSTEM_PROMPT`.)
**Bonus:** `tests/eval/run_matrix.py` gained `EVAL_FORCE_RERUN=1` env override during this work — useful for future regression validation.

### [2026-06-08: Self-Hosting Frontier LLMs — Open Weights & GPU Rental Research](2026-06-08_self-hosting-gpu-rental-research.md)
**Research:** Open-weights audit and self-host feasibility for the 5 top models from the `netbox-benchmark-v2` 10-model cloud sweep, plus current (June 2026) GPU rental pricing and inference-stack recommendations.
**Key findings:**
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
| 2026-06-15 | QuickJS PTC spikes — decision: defer | [2026-06-03_quickjs-code-interpreter-research.md](2026-06-03_quickjs-code-interpreter-research.md) |
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
**Last Updated:** 2026-06-15
