<!--
PROVENANCE: Harvested 2026-06-22 from the ancestor repo FinnMacCumail/deepagents
(examples/netbox/docs/netbox/reports/NO_SUBAGENTS_RATIONALE.md). The empirical finding
here — direct sequential execution beats spawning subagents for NetBox queries — STILL
holds in ollamaDeepAgents, and is corroborated by the 2026-06 QuickJS PTC spikes (the
model declined to use eval-based orchestration on the same sequential workload). See
docs/development/2026-06-03_quickjs-code-interpreter-research.md §15.
-->

# No Sub-Agents Design Decision

## Executive Summary

The NetBox agent has been refactored to **completely remove sub-agent support**. Validation testing demonstrated that direct sequential execution in the main agent context is more efficient, reliable, and cost-effective than spawning specialized domain sub-agents.

## Key Decision

**Sub-agents have been disabled permanently.** The agent now executes all queries through direct sequential tool calls in the main context.

## Evidence from Validation Testing

### Test Scope
5 cross-domain queries spanning 2-3 NetBox domains (DCIM, IPAM, Tenancy) were executed with sub-agents available but prompts strongly discouraging their use.

### Results

| Metric | Value | Notes |
|--------|-------|-------|
| **Success Rate** | 60% → 100%* | *After recursion limit fix |
| **task() Calls** | 0 | Sub-agents never invoked |
| **Avg Tool Calls** | 5-8 | Direct execution |
| **Query Types** | TIER 1 & TIER 2 | All real-world scenarios |
| **Failure Root Cause** | Recursion limit | Not sub-agent related |

**Critical Finding**: Despite having 5 specialized domain sub-agents available (dcim-specialist, ipam-specialist, tenancy-specialist, virtualization-specialist, system-specialist), the agent made **0 task() calls** across all 5 validation queries.

### Trace Analysis

Detailed trace analysis (see [VALIDATION_RESULTS_SUMMARY.md](VALIDATION_RESULTS_SUMMARY.md)) showed:

- **Query 1** (Tenant Sites Summary): 7 tool calls, TIER 2, 0 task() calls
- **Query 2** (Device Configuration): 3 tool calls, TIER 1, 0 task() calls
- **Query 3** (VLAN Deployment): 10 tool calls, TIER 1, 0 task() calls (failed due to recursion limit)
- **Query 4** (Rack Inventory): 10 tool calls, TIER 2, 0 task() calls (failed due to recursion limit)
- **Query 5** (Site Comparison): 12 tool calls, TIER 1, 0 task() calls

**Conclusion**: When given strong guidance toward direct execution, the agent naturally avoided sub-agents even when they were available.

## Why Direct Execution Won

### 1. Sequential Dependencies

Most NetBox queries have sequential dependencies:
- Tenant name → tenant_id → devices/racks/prefixes
- Site name → site_id → racks → devices → IPs

Sub-agents add coordination overhead for operations that are naturally sequential.

### 2. Bulk Query Optimization

NetBox's 3 generic MCP tools support bulk queries with filters:
```python
# Instead of spawning sub-agents per site:
devices = netbox_get_objects("devices", {"tenant_id": tenant_id})
# Then group by site in code
```

This pattern eliminates the need for parallel sub-agent execution.

### 3. Small Datasets

Real-world NetBox queries typically involve:
- Single tenant (1 entity)
- 3-5 sites (small dataset)
- <10 devices per site (small dataset)

The overhead of spawning sub-agents exceeds the benefits for datasets this size.

### 4. Generic Tool Interface

The 3 MCP tools (netbox_get_objects, netbox_get_object_by_id, netbox_get_changelogs) can access ALL NetBox data. There's no tool specialization that would benefit from domain-specific sub-agents.

### 5. Cost Efficiency

**Previous sub-agent approach** (before prompt rewrite):
- 75 tool calls
- 347 seconds
- Failed at recursion limit
- Token explosion from delegation overhead

**Direct execution approach**:
- 5-12 tool calls per query
- 12-15 seconds average
- 100% success rate
- 14x cost reduction

## Technical Changes

### Code Changes

1. **[netbox_agent.py:703](netbox_agent.py#L703)**
   - Changed `netbox_subagents = create_netbox_subagents()` to `netbox_subagents = []`
   - Added comment explaining why sub-agents are disabled

2. **[netbox_agent.py:41-190](netbox_agent.py#L41)** (removed)
   - Deleted 150-line parallel execution pattern comment block
   - Removed misleading guidance about task() delegation

3. **[netbox_subagents_deprecated.py](netbox_subagents_deprecated.py)** (new file)
   - Preserved original sub-agent creation function for reference
   - Marked as deprecated with explanation

### Prompt Changes

1. **[prompts.py:SIMPLE_MCP_INSTRUCTIONS](prompts.py#L3)**
   - Removed "WHEN TO AVOID SUB-AGENTS" section
   - Simplified to "Direct Execution" and "Multi-Step Queries"
   - Added tool usage guidelines for think() and store_query()
   - Reduced from ~1,800 tokens to ~1,200 tokens (33% reduction)

2. **[prompts.py:NETBOX_SUPERVISOR_INSTRUCTIONS](prompts.py#L54)**
   - Removed TIER 3 (Parallel Delegation)
   - Removed "When NOT to Use Sub-Agents" section
   - Removed Example 6 (50 tenant counter-example)
   - Changed from 3-tier to 2-tier execution framework
   - Updated final guidance: "Direct sequential execution is optimal"

### Error Handling Improvements

1. **[netbox_agent.py:152](netbox_agent.py#L152)**
   - Changed `return {"error": str(e)}` to `raise ToolException(...)`
   - Prevents agent from treating error dicts as successful data
   - Makes tool failures explicit to the agent

## When Would Sub-Agents Be Appropriate?

Based on validation evidence, sub-agents would only make sense for:

1. **Massive parallel workloads**: 50+ truly independent entities, each requiring 3+ tool calls (150-250 total calls)
2. **Computational isolation**: Each sub-task requires complex in-memory processing that would pollute main agent context
3. **Specialized tools**: Different sub-agents need access to completely different tool sets (not applicable with our 3 generic tools)

**For NetBox queries, none of these conditions apply.**

## Performance Comparison

### Before (Sub-Agent Approach)
```
Query: "Show all Dunder-Mifflin sites with device counts, rack allocations, and IP prefix assignments"

Execution:
- 14 task() calls spawning domain specialists
- 75 total tool calls (delegation overhead)
- 347 seconds total time
- FAILED: Hit recursion limit
- Cost: ~14x higher due to delegation overhead
```

### After (Direct Execution)
```
Query: "Show all Dunder-Mifflin sites with device counts, rack allocations, and IP prefix assignments"

Execution:
- 0 task() calls
- 7 direct tool calls
- 12 seconds total time
- SUCCESS: Completed within limits
- Cost: Baseline (no delegation overhead)
```

## Architecture Decision

**Sub-agents are not conditionally disabled - they are architecturally removed.**

The original plan considered making sub-agents conditional on query analysis. However, validation evidence showed this is unnecessary complexity:

1. Agent naturally avoided sub-agents when given proper guidance
2. 0 task() calls across all validation scenarios
3. No benefit observed from having sub-agents available

**Simpler is better**: Remove the capability entirely rather than add conditional logic.

## Future Considerations

If NetBox query patterns change significantly (e.g., new API requiring 100+ independent entity processing), sub-agents could be re-enabled by:

1. Restoring code from [netbox_subagents_deprecated.py](netbox_subagents_deprecated.py)
2. Changing `netbox_subagents = []` to `netbox_subagents = create_netbox_subagents()`
3. Adding TIER 3 back to prompts

**However**, current validation shows no realistic NetBox use case requires this.

## Conclusion

**Direct sequential execution is the optimal architecture for NetBox queries.**

The sub-agent infrastructure has been completely removed based on empirical evidence showing it provides no benefit for real-world NetBox use cases. The agent is now simpler, faster, more reliable, and more cost-effective.

## References

- [VALIDATION_RESULTS_SUMMARY.md](VALIDATION_RESULTS_SUMMARY.md) - Complete validation test results
- [VALIDATION_TEST_SUITE.md](VALIDATION_TEST_SUITE.md) - Test queries used for validation
- [RECURSION_LIMIT_ADJUSTMENT.md](RECURSION_LIMIT_ADJUSTMENT.md) - Recursion limit analysis
- [PROMPT_REWRITE_SUMMARY.md](PROMPT_REWRITE_SUMMARY.md) - Original prompt rewrite rationale
- [netbox_subagents_deprecated.py](netbox_subagents_deprecated.py) - Preserved sub-agent code

---

**Date**: 2025-10-13
**Decision Owner**: Architecture refactoring based on validation evidence
**Status**: Implemented and deployed
