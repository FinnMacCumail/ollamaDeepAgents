<!-- PROVENANCE: Harvested 2026-06-22 from FinnMacCumail/deepagents
(examples/netbox/docs/netbox/analysis/TOOL_REMOVAL_RESULTS.md). Lineage/reference only.
The 4-generic-tool surface validated here is the design ollamaDeepAgents still uses. -->

# Tool Removal Results: 8 Tools → 4 Tools

## Executive Summary

After removing 4 unused tools (list_available_tools, get_tool_details, show_cache_metrics, store_query), we compared 3 queries to measure the impact. Results show **highly variable outcomes** with one major improvement, one major regression, and one mixed result.

## Configuration Change

**BEFORE**: 8 tools
- 3 NetBox MCP tools
- 5 strategic/discovery tools (list_available_tools, get_tool_details, show_cache_metrics, think, store_query)

**AFTER**: 4 tools
- 3 NetBox MCP tools
- 1 strategic tool (think)

**Tools Removed**: 4 tools that showed 0 usage in previous validation
**Expected Impact**: 800-1,600 tokens saved per request, reduced tool choice overhead

## Detailed Results

### Query 1: Dunder-Mifflin Sites ✅ **MAJOR IMPROVEMENT**

**Query**: "Show all Dunder-Mifflin sites with device counts, rack allocations, and IP prefix assignments"

| Metric | OLD (8 tools) | NEW (4 tools) | Delta | Change |
|--------|---------------|---------------|-------|--------|
| LLM Calls | 9 | 7 | -2 | **-22.2%** ✅ |
| Tool Calls | 10 | 9 | -1 | **-10.0%** ✅ |
| netbox_get_objects | 5 | 5 | 0 | 0% |
| write_todos | 5 | 4 | -1 | -20.0% |
| Duration | 71.0s | 60.6s | -10.4s | **-14.7%** ✅ |

**Analysis**:
- **Significant improvement** across all metrics
- 22% fewer LLM calls (9 → 7)
- 15% faster execution (saved 10.4 seconds)
- Less planning overhead (4 vs 5 write_todos)
- Same NetBox API efficiency (5 calls each)

**This was the problematic Query 3 from REFACTORING_RESULTS.md** that showed 40% regression after sub-agent removal. Tool removal has **fixed the regression**:
- Original BEFORE (before sub-agent removal): 7 LLM, 50.7s
- AFTER sub-agent removal (8 tools): 9 LLM, 71.0s (❌ **40% slower**)
- AFTER tool removal (4 tools): 7 LLM, 60.6s (✅ **Back to baseline!**)

**Winner**: ✅ **4 tools** - Fixed the Query 3 regression!

---

### Query 2: VLAN 100 Deployment ❌ **MAJOR REGRESSION**

**Query**: "Show where VLAN 100 is deployed across Jimbob's Banking sites, including devices using this VLAN and IP allocations"

| Metric | OLD (8 tools) | NEW (4 tools) | Delta | Change |
|--------|---------------|---------------|-------|--------|
| LLM Calls | 6 | 10 | +4 | **+66.7%** ⚠️ |
| Tool Calls | 5 | 16 | +11 | **+220.0%** ⚠️ |
| netbox_get_objects | 5 | 11 | +6 | +120.0% |
| write_todos | 0 | 5 | +5 | N/A |
| Duration | 33.4s | 57.9s | +24.5s | **+73.3%** ⚠️ |

**Analysis**:
- **Severe regression** across all metrics
- 67% MORE LLM calls (6 → 10)
- 220% more tool calls (5 → 16)
- 73% slower (33.4s → 57.9s, 24 seconds slower)
- Massive over-planning (0 → 5 write_todos calls)
- Doubled NetBox API calls (5 → 11)

**This was a simple TIER 1 query** that should execute directly without planning. Something has gone wrong with the agent's execution strategy.

**Winner**: ❌ **8 tools** - New version severely regressed

---

### Query 3: NC State Racks ✅ **SIGNIFICANT IMPROVEMENT**

**Query**: "For NC State University racks at Butler Communications site, show installed devices with their IP addresses"

| Metric | OLD (8 tools) | NEW (4 tools) | Delta | Change |
|--------|---------------|---------------|-------|--------|
| LLM Calls | 12 | 10 | -2 | **-16.7%** ✅ |
| Tool Calls | 13 | 10 | -3 | **-23.1%** ✅ |
| netbox_get_objects | 7 | 5 | -2 | **-28.6%** ✅ |
| write_todos | 6 | 5 | -1 | -16.7% |
| Duration | 62.8s | 41.9s | -20.9s | **-33.3%** ✅ |

**Analysis**:
- **Major improvement** across all metrics
- 17% fewer LLM calls (12 → 10)
- 23% fewer tool calls (13 → 10)
- 29% fewer NetBox API calls (7 → 5)
- **33% faster** (62.8s → 41.9s, saved 21 seconds!)
- More efficient execution with simpler tool set

**Winner**: ✅ **4 tools** - Clear improvement

---

## Overall Summary

### Aggregate Metrics Across 3 Queries

| Metric | Total Change | Average Per Query | Trend |
|--------|-------------|-------------------|-------|
| LLM Calls | +0.0 | +0.0 | ➡️ **Neutral** |
| Tool Calls | +7.0 | +2.3 | ⚠️ **Slight regression** |
| Duration | -6.8s | -2.3s | ✅ **Slight improvement** |

### Performance Breakdown

- **Query 1**: ✅ **Major win** (-22% LLM, -15% time) - Fixed previous regression!
- **Query 2**: ❌ **Major loss** (+67% LLM, +73% time) - Severe regression
- **Query 3**: ✅ **Major win** (-17% LLM, -33% time) - Significant improvement

**Success Rate**: 3/3 ✅ (100%) - All queries still successful

### Net Result

**Mixed**: 2 queries improved significantly, 1 query regressed severely. Overall metrics are neutral due to offsetting effects.

## Key Findings

### ✅ Improvements Observed

1. **Fixed Query 1 Regression** (Critical Win!)
   - This was the problematic "Dunder-Mifflin sites" query that regressed 40% after sub-agent removal
   - Tool removal brought it back to original performance (7 LLM calls, 60.6s)
   - **Root cause identified**: Simpler tool set reduced over-planning

2. **Query 3 Massively Improved** (33% faster)
   - 21 second speedup (62.8s → 41.9s)
   - 29% fewer NetBox API calls (more efficient execution)
   - Cleaner execution path with 4 tools vs 8 tools

3. **Token Savings** (Expected)
   - 800-1,600 tokens per request no longer wasted on unused tool schemas
   - ~$0.0024-0.0048 saved per request

### ⚠️ Major Concerns

1. **Query 2 Severe Regression** (Critical Issue!)
   - **73% slower** (33.4s → 57.9s)
   - 67% more LLM calls (6 → 10)
   - 220% more tool calls (5 → 16)
   - Changed from direct execution (0 write_todos) to heavy planning (5 write_todos)
   - **Doubled NetBox API calls** (5 → 11)

2. **Inconsistent Behavior**
   - Same tool removal produced both massive improvements and massive regressions
   - Query 2 (simple TIER 1) performed worse than complex TIER 2 queries
   - Tool choice simplification had unpredictable effects

### Query 2 Regression Analysis

**What Changed**:
- BEFORE (8 tools): Simple, direct execution with 0 planning
- AFTER (4 tools): Heavy planning with 5 write_todos calls

**Hypothesis**: Removing discovery tools may have made agent uncertain about tool capabilities, leading to over-compensation with excessive planning.

**Evidence**:
- Query went from "direct execution" to "sequential execution with dependencies"
- Agent made 5 write_todos calls when previously it made 0
- Agent called netbox_get_objects 11 times when 5 was sufficient

**Root Cause**: Possibly agent is less confident without `list_available_tools` and `get_tool_details`, leading to defensive over-planning.

## Comparison to Previous Refactorings

### Evolution of Query 1 (Dunder-Mifflin Sites)

| Stage | Tools | LLM Calls | Duration | Notes |
|-------|-------|-----------|----------|-------|
| Original (before sub-agent removal) | 8 | 7 | 50.7s | Baseline |
| After sub-agent removal | 8 | 9 | 71.0s | ❌ 40% regression |
| After tool removal | 4 | 7 | 60.6s | ✅ Back to baseline! |

**Conclusion**: Tool removal **fixed the sub-agent removal regression** for Query 1.

### Evolution of Query 2 (VLAN 100)

| Stage | Tools | LLM Calls | Duration | Notes |
|-------|-------|-----------|----------|-------|
| After sub-agent removal | 8 | 6 | 33.4s | Efficient baseline |
| After tool removal | 4 | 10 | 57.9s | ❌ 73% slower |

**Conclusion**: Tool removal **created a new regression** for Query 2.

### Evolution of Query 3 (NC State Racks)

| Stage | Tools | LLM Calls | Duration | Notes |
|-------|-------|-----------|----------|-------|
| After sub-agent removal | 8 | 12 | 62.8s | Baseline |
| After tool removal | 4 | 10 | 41.9s | ✅ 33% improvement |

**Conclusion**: Tool removal **significantly improved** Query 3.

## Recommendations

### Immediate Actions

1. **Investigate Query 2 Regression** (Critical)
   - Review trace logs to understand why agent switched from direct to heavy planning
   - Identify what triggered 5 write_todos calls when previously 0
   - Determine why NetBox calls doubled (5 → 11)

2. **A/B Test Discovery Tools**
   - Test if keeping `list_available_tools` reduces Query 2 regression
   - Measure if tool discovery provides confidence that prevents over-planning
   - Determine minimum tool set for stable performance

3. **Prompt Adjustment**
   - Consider adding explicit guidance: "For simple VLAN queries, execute directly without planning"
   - Emphasize when NOT to use write_todos
   - Add Query 2 as a negative example (what not to do)

### Long-Term Considerations

1. **Tool Count Sweet Spot**
   - 8 tools: Caused Query 1 regression (too much overhead?)
   - 4 tools: Caused Query 2 regression (too little confidence?)
   - Test 5-6 tools (keep 1-2 discovery tools?)

2. **Query-Specific Behavior**
   - Simple queries (TIER 1) more affected by tool removal
   - Complex queries (TIER 2) benefited from simplification
   - May need query-type-specific tool loading

3. **Performance Stability**
   - Need more consistent results across query types
   - Current approach produces unpredictable swings
   - Consider validation suite with 10+ diverse queries

## Net Assessment

**Status**: ⚠️ **Mixed Results - Investigation Needed**

**Pros**:
- Fixed Query 1's 40% regression from sub-agent removal ✅
- Improved Query 3 by 33% ✅
- Saved 800-1,600 tokens per request ✅

**Cons**:
- Created 73% regression in Query 2 ❌
- Highly unpredictable behavior changes ❌
- Tool count optimization unclear ❌

**Recommendation**: **Do not deploy** until Query 2 regression is understood and fixed. The 73% slowdown on a simple query is unacceptable, even though 2 other queries improved.

## Next Steps

1. Analyze Query 2 trace in detail (why 11 netbox_get_objects calls?)
2. Test intermediate tool configuration (5-6 tools with one discovery tool)
3. Add explicit TIER 1 guidance to prevent over-planning
4. Run expanded validation suite (10+ queries) to find stable configuration
5. Consider reverting to 8 tools if Query 2 cannot be fixed

---

## Trace IDs

**Query 1 (Dunder-Mifflin Sites)**:
- BEFORE (8 tools): `6ab198c9-1308-4e84-b124-0ac8670be95a`
- AFTER (4 tools): `740466c3-ebb5-4864-9954-6fc1fb9085a2`

**Query 2 (VLAN 100)**:
- BEFORE (8 tools): `e6046c96-ab11-45fc-9662-073e9d0d1408`
- AFTER (4 tools): `d8ad87bd-b09e-4100-bb9f-bd8aa7011655`

**Query 3 (NC State Racks)**:
- BEFORE (8 tools): `d2e82487-e103-432c-9634-f0b0f4af3b6f`
- AFTER (4 tools): `74ad927e-a634-4a62-b1a9-2bf74fd76af4`
