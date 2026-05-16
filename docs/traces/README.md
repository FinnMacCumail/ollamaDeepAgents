# LangSmith Trace Analysis Reports

This directory contains detailed analysis reports of LangSmith traces from the NetBox DeepAgents project.

## Purpose

- Document query execution patterns
- Track performance optimizations
- Debug issues
- Compare different approaches (backends, models, configurations)
- Build institutional knowledge about agent behavior

## Naming Convention

```
YYYY-MM-DD_<trace-id-short>_<description>.md
YYYY-MM-DD_comparison_<description>.md
```

## Available Reports

### 2026-05-14

| File | Trace ID | Query | Duration | Description |
|------|----------|-------|----------|-------------|
| [2026-05-14_019e1c9f_skills-loaded-multi-aspect.md](2026-05-14_019e1c9f_skills-loaded-multi-aspect.md) | `019e1c9f-64de-77e1-98e1-9668a00a8cfa` | Multi-aspect tenant query (re-run with skills loaded) | **22s** | Breakthrough: first trace with `skills_metadata` populated. Skill steered model toward parent-object count fields → zero tool calls, 10× speedup vs same query without skills |

### 2026-05-12

| File | Trace ID | Query | Duration | Description |
|------|----------|-------|----------|-------------|
| [2026-05-12_019e1c4e_multi-aspect-deepseek-cloud.md](2026-05-12_019e1c4e_multi-aspect-deepseek-cloud.md) | `019e1c4e-87c7-7b53-88fa-f87a5275e142` | Multi-aspect tenant query (Dunder-Mifflin sites + devices + racks + prefixes) | 227s | Query that twice defeated the local 14B now completes; 3-way parallel tool batch; filter-semantics gotcha (`tenant_id` vs `site_id`) undercounts patch-panel devices |
| [2026-05-12_019e1c19_rack-elevation-deepseek-cloud.md](2026-05-12_019e1c19_rack-elevation-deepseek-cloud.md) | `019e1c19-f6c5-7480-8e1b-28c03578de33` | Rack elevation | 244s | First run on `deepseek-v4-pro:cloud` after backend switch — 3-way comparison vs local 14B and Claude SDK |

### 2026-05-05

| File | Trace ID | Query | Duration | Description |
|------|----------|-------|----------|-------------|
| [2026-05-05_019df7bd_rack-elevation-comparison.md](2026-05-05_019df7bd_rack-elevation-comparison.md) | `019df7bd-ed28-78f0-91f9-7692f8ab13cb` | Rack elevation | 67.1s | DeepAgents vs Claude SDK comparison |

### 2026-05-04

| File | Trace ID | Query | Duration | Description |
|------|----------|-------|----------|-------------|
| [2026-05-04_019df45c_list-sites-before-fix.md](2026-05-04_019df45c_list-sites-before-fix.md) | `019df45c-c873-7720-8dad-4fb15b8fc132` | "list all sites" | 39.8s | Baseline trace showing messy output issue |
| [2026-05-04_comparison_streaming-fix.md](2026-05-04_comparison_streaming-fix.md) | Multiple | Various | - | Before/after comparison of streaming filter fix |

## Key Findings Summary

### Skills loaded — multi-aspect query (2026-05-14)
**Query:** Same multi-aspect query as 2026-05-12 baseline, re-run after the FilesystemBackend skill-loader fix
- **Outcome:** First trace in project history with `skills_metadata` populated — both `netbox-mcp-filters` and `trace-analysis` skills active
- **Performance:** 22s wall time (vs 227s for the same query without skills) — 10× speedup driven by the skill steering toward NetBox's per-site count fields (`device_count`, `rack_count`, etc.), eliminating the need for additional tool calls
- **Tool calls:** Zero this turn (memory-enabled session — prior turns cached the data; this turn was pure decode)
- **Device count:** 52 (read from canonical `device_count` field) — likely the most accurate; supersedes prior 39 (tenant_id undercount) and Claude SDK's 42
- **Skill influence confirmed:** earlier failed attempts in the same window used `site_id=[1,…,14]` filter form and `limit=200` — both patterns appear nowhere outside the skill content
- **File:** `2026-05-14_019e1c9f_skills-loaded-multi-aspect.md`

### Multi-aspect tenant query on deepseek-v4-pro:cloud (2026-05-12)
**Query:** Show all Dunder Mifflin sites with device counts, rack allocations, and IP prefix assignments
- **Outcome:** Query that twice defeated the local 14B (empty answer + 400 crash) now completes cleanly with a 14-site table
- **Decomposition:** Two-step tenant lookup, then a 3-way parallel tool batch (devices + racks + prefixes) — capability not seen on the 14B
- **Correctness gap:** Reports 39 devices vs Claude SDK's 42; `tenant_id` filter quietly drops patch panels that lack explicit tenant assignment but inherit it via rack
- **Cost:** 227s wall time, 5 LLM calls, 6 tool calls (one redundant `ipam.prefix` re-fetch wasted ~40s)
- **Open issue:** `skills_metadata: []` again — netbox-mcp-filters skill (which would have steered toward the correct filter path) still not loading
- **File:** `2026-05-12_019e1c4e_multi-aspect-deepseek-cloud.md`

### deepseek-v4-pro:cloud first run (2026-05-12)
**Query:** Rack elevation display (same as 2026-05-05 baseline)
- **Quality:** Cloud frontier model is the only run of three to render a true rack elevation; correctly handles the multi-U patch panel (Claude SDK got it wrong)
- **Performance:** ~244s wall time — slower than both local 14B (~32s) and Claude SDK (~10s); 96s spent on the final formatting call alone
- **Tool calling:** Two parallel tool batches (2-way and 4-way) — capability not exhibited by the local 14B
- **Architectural validation:** Two-step pattern, field projection, memory all carry over unchanged from local stack
- **Open issue:** `skills_metadata` still empty despite the `title:` → `name:` fix in commit `63f1fb3`
- **File:** `2026-05-12_019e1c19_rack-elevation-deepseek-cloud.md`

### DeepAgents vs Claude SDK (2026-05-05)
**Query:** Rack elevation display
- **Performance:** Claude SDK is 6-7x faster (10s vs 67s)
- **Quality:** Claude SDK has superior formatting and ASCII visualization
- **Trade-offs:**
  - DeepAgents: 100% local, $0 cost, full privacy
  - Claude SDK: Fast, excellent UX, cloud-based
- **Recommendation:** Use case dependent - privacy vs speed
- **File:** `2026-05-05_019df7bd_rack-elevation-comparison.md`

### Streaming Output Fix (2026-05-04)
- **Problem:** `stream_mode="values"` yielded 7+ chunks including raw JSON
- **Solution:** Filter to only yield final AI messages with content
- **Result:** 1 clean chunk, 11% faster (35.6s vs 39.8s)
- **Files:**
  - Before: `2026-05-04_019df45c_list-sites-before-fix.md`
  - Comparison: `2026-05-04_comparison_streaming-fix.md`

## Performance Baselines

### llama.cpp Backend (Qwen3-14B-Q5_K_M)
- **Simple "list sites" query:** ~35-40s
- **Token usage:** ~23K tokens (88-99% cached)
- **LLM calls:** 2 (tool selection + formatting)
- **Cache effectiveness:** Excellent (saves ~20K tokens)

## How to Add New Reports

1. Fetch trace data using LangSmith CLI or helper scripts
2. Analyze following the structure in `.claude/skills/trace-analysis/SKILL.md`
3. Save to this directory using naming convention
4. Update this README with new entry
5. Include key findings in summary sections

## Related Documentation

- **Skill (developer-only):** [.claude/skills/trace-analysis/SKILL.md](../../.claude/skills/trace-analysis/SKILL.md) — loaded by Claude Code sessions in this repo, NOT by the runtime agent
- **Helper Scripts:**
  - [fetch_run_details.py](../../scripts/fetch_run_details.py)
  - [test_clean_output.py](../../tests/manual/test_clean_output.py)
- **Setup Guides:**
  - [LangSmith Setup](../setup/langsmith.md)
  - [LangSmith Skills Installation](../setup/langsmith-skills.md)

## Quick Commands

```bash
# List recent traces
LANGSMITH_API_KEY=$(grep LANGCHAIN_API_KEY .env | cut -d'=' -f2) \
  /home/ola/.local/bin/langsmith trace list \
  --project netbox-deepagents-llamacpp --limit 10

# Get trace details
LANGSMITH_API_KEY=$(grep LANGCHAIN_API_KEY .env | cut -d'=' -f2) \
  /home/ola/.local/bin/langsmith run get <run-id> \
  --project netbox-deepagents-llamacpp --include-io
```

---

**Project:** ollamaDeepAgents (NetBox DeepAgents)
**LangSmith Project:** netbox-deepagents-llamacpp
**Backend:** llama.cpp (default)
**Model:** Qwen_Qwen3-14B-Q5_K_M.gguf
