---
name: trace-analysis
description: Analyze LangSmith traces from the netbox-deepagents-llamacpp project and save structured reports to docs/traces/. Load this skill whenever the user asks to inspect, summarize, compare, or debug a LangSmith trace.
version: 1.0.0
tags: [langsmith, tracing, analysis, debugging, performance]
priority: medium
---

# LangSmith Trace Analysis Skill

This skill provides a structured workflow for fetching, analyzing, and documenting LangSmith traces from the NetBox DeepAgents project. All analysis reports are automatically saved to `docs/traces/` for long-term reference.

## When to Use This Skill

Use this skill when you need to:
- Analyze a specific trace ID from LangSmith
- Compare multiple traces (before/after, different queries, etc.)
- Debug performance issues
- Document query execution patterns
- Track improvements over time

## Core Workflow

### 1. Fetch Trace Overview

Get basic trace information first:

```bash
LANGSMITH_API_KEY=<key> /home/ola/.local/bin/langsmith trace list \
  --project netbox-deepagents-llamacpp \
  --limit 10
```

Identify the trace ID you want to analyze.

### 2. Fetch LLM Call Details

For each LLM call in the trace, fetch full input/output:

```bash
# Get the first LLM call
LANGSMITH_API_KEY=<key> /home/ola/.local/bin/langsmith run get <run-id-1> \
  --project netbox-deepagents-llamacpp \
  --include-io

# Get the second LLM call
LANGSMITH_API_KEY=<key> /home/ola/.local/bin/langsmith run get <run-id-2> \
  --project netbox-deepagents-llamacpp \
  --include-io
```

**Note:** Get the API key from the .env file:
```bash
grep LANGCHAIN_API_KEY .env
# Use: LANGCHAIN_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxxxxxxxxxx_xxxxxxxxxx
```

### 3. Analyze the Trace Data

Extract and analyze:

- **Query:** User's original request
- **Duration:** Total execution time and breakdown by phase
- **Token Usage:** Input/output tokens, cache hits
- **LLM Calls:** What each call does (tool selection vs formatting)
- **Tool Calls:** What tools were invoked and their results
- **Performance:** Identify bottlenecks
- **Message Flow:** What messages were generated

### 4. Save Analysis Report

**CRITICAL:** Always save trace analysis reports to `docs/traces/` with this naming convention:

```
docs/traces/YYYY-MM-DD_<trace-id-short>_<description>.md
```

**Examples:**
```
docs/traces/2026-05-04_019df45c_list-sites-before-fix.md
docs/traces/2026-05-04_019df48b_list-sites-after-fix.md
docs/traces/2026-05-04_comparison_streaming-fix.md
```

### 5. Report Structure

Each trace analysis report should include:

```markdown
# Trace Analysis: <Description>

**Trace ID:** `<full-trace-id>`
**Query:** "<user-query>"
**Duration:** X.Xs
**Backend:** llama.cpp / Ollama
**Model:** <model-name>
**Date:** YYYY-MM-DD HH:MM:SS

---

## Overview

[Brief summary of what this trace shows]

## LLM Call #1: Tool Selection

**Duration:** X.Xs
**Input Tokens:** X (Y cached)
**Output Tokens:** X
**Total:** X tokens

**Decision:** [What tool was selected and why]

## Tool Execution

**Duration:** X.Xs
**Tool:** <tool-name>
**Arguments:** [Show tool arguments]
**Result:** [Summarize result size/content]

## LLM Call #2: Response Formatting

**Duration:** X.Xs
**Input Tokens:** X (Y cached)
**Output Tokens:** X
**Total:** X tokens

**Output:** [Show formatted response]

## Performance Breakdown

| Phase | Duration | Token Usage | Notes |
|-------|----------|-------------|-------|
| LLM Call 1 | Xs | X tokens | [notes] |
| Tool Call | Xs | - | [notes] |
| LLM Call 2 | Xs | X tokens | [notes] |
| **TOTAL** | **Xs** | **X tokens** | [notes] |

## Key Findings

- Finding 1
- Finding 2
- Finding 3

## Optimization Opportunities

- Opportunity 1
- Opportunity 2

---

**Analyzed:** YYYY-MM-DD
**Saved to:** docs/traces/
```

## Comparison Reports

When comparing multiple traces (e.g., before/after a fix), use this structure:

```markdown
# Trace Comparison: <Description>

## Overview

Comparing traces to verify [purpose of comparison]

| Metric | Trace A | Trace B | Change |
|--------|---------|---------|--------|
| Duration | Xs | Xs | ±X% |
| Tokens | X | X | ±X |
| LLM Calls | X | X | same |

[Continue with detailed comparison sections]
```

## Helper Scripts

The project includes helper scripts in the root directory:

- **fetch_run_details.py** - Fetch LLM call details via Python SDK
  ```bash
  LANGCHAIN_API_KEY=<key> python fetch_run_details.py <run-id>
  ```

## Environment Variables

Always source the .env file or use the API key directly:

```bash
# Option 1: Source .env (may not work in all contexts)
source .env

# Option 2: Use API key directly (recommended)
LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxxxxxxxxxxxxxx_xxxxxxxxxx
```

## Quick Command Reference

```bash
# List recent traces
LANGSMITH_API_KEY=<key> /home/ola/.local/bin/langsmith trace list \
  --project netbox-deepagents-llamacpp --limit 5

# Get trace overview
LANGSMITH_API_KEY=<key> /home/ola/.local/bin/langsmith trace get <trace-id>

# Get run with full I/O
LANGSMITH_API_KEY=<key> /home/ola/.local/bin/langsmith run get <run-id> \
  --project netbox-deepagents-llamacpp --include-io
```

## File Organization

```
docs/traces/
├── 2026-05-04_019df45c_list-sites-before-fix.md
├── 2026-05-04_019df48b_list-sites-after-fix.md
├── 2026-05-04_comparison_streaming-fix.md
└── README.md  (index of all trace analyses)
```

## Best Practices

1. **Always save reports** - Don't just analyze in-session, save for future reference
2. **Use descriptive filenames** - Include date, trace ID prefix, and description
3. **Include full trace ID** - In the report metadata for easy lookup
4. **Compare before/after** - When testing fixes or optimizations
5. **Track token usage** - Monitor prompt caching effectiveness
6. **Document findings** - Include optimization opportunities
7. **Update the index** - Keep docs/traces/README.md updated with new analyses

## Remember

- **Project:** netbox-deepagents-llamacpp
- **Reports location:** docs/traces/
- **API key location:** .env (LANGCHAIN_API_KEY)
- **CLI location:** /home/ola/.local/bin/langsmith
- **Helper script:** fetch_run_details.py

This skill ensures consistent, well-documented trace analysis that builds a knowledge base of performance patterns and optimizations over time.
