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

### 2026-05-04

| File | Trace ID | Query | Duration | Description |
|------|----------|-------|----------|-------------|
| [2026-05-04_019df45c_list-sites-before-fix.md](2026-05-04_019df45c_list-sites-before-fix.md) | `019df45c-c873-7720-8dad-4fb15b8fc132` | "list all sites" | 39.8s | Baseline trace showing messy output issue |
| [2026-05-04_comparison_streaming-fix.md](2026-05-04_comparison_streaming-fix.md) | Multiple | Various | - | Before/after comparison of streaming filter fix |

## Key Findings Summary

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
2. Analyze following the structure in `src/skills/trace-analysis/SKILL.md`
3. Save to this directory using naming convention
4. Update this README with new entry
5. Include key findings in summary sections

## Related Documentation

- **Skill:** [src/skills/trace-analysis/SKILL.md](../../src/skills/trace-analysis/SKILL.md)
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
