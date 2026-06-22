#!/usr/bin/env python3
"""
Manual trace analysis - paste trace URLs and extract metrics.
Alternative when API access isn't available.
"""

# Baseline metrics from VALIDATION_TEST_SUITE.md
BASELINE = {
    "Query 1": {"tool_calls": 75, "llm_calls": 76, "time": 347, "cost": 2.00, "result": "SUCCESS"},
    "Query 2": {"tool_calls": 12, "llm_calls": 13, "time": 58, "cost": 0.51, "result": "SUCCESS"},
    "Query 3": {"tool_calls": 30, "llm_calls": 31, "time": 162, "cost": 1.60, "result": "FAILED"},
    "Query 4": {"tool_calls": 19, "llm_calls": 20, "time": 91, "cost": 0.77, "result": "FAILED"},
    "Query 5": {"tool_calls": 41, "llm_calls": 32, "time": 149, "cost": 2.30, "result": "FAILED"},
}

print("""
================================================================================
MANUAL TRACE ANALYSIS TEMPLATE
================================================================================

Please provide the following information for each of the 5 validation queries:

Trace IDs:
1. a29bd4a3-3260-4b7c-82e6-f33074fbf0ad (Query ?)
2. 7b8f2650-86c2-441e-a974-4450678dfafa (Query ?)
3. 6976c584-778f-4744-bab8-624f785c788d (Query ?)
4. 5488b4d8-b1ef-4a84-8471-e10731fa63ae (Query ?)
5. 943e978f-65aa-43f7-9419-69fd204de6f9 (Query ?)

For each trace, go to: https://smith.langchain.com/o/<your-org>/projects/p/<project>/r/<run-id>

Extract and provide:
- Query text (which of the 5 queries from VALIDATION_TEST_SUITE.md)
- Status (SUCCESS/FAILED)
- Duration (seconds)
- Tool calls count
- Number of task() calls (sub-agent spawns) - CRITICAL
- Number of write_todos() calls
- Number of think() calls
- Number of netbox_* calls
- LLM calls count
- Input tokens
- Output tokens
- Cached tokens (if shown)

Alternatively, export trace data as JSON and we can parse it.

================================================================================
BASELINE COMPARISON
================================================================================
""")

for query, metrics in BASELINE.items():
    print(f"\n{query}:")
    print(f"  Baseline: {metrics['tool_calls']} tool calls, {metrics['time']}s, ${metrics['cost']:.2f}, {metrics['result']}")
    print(f"  Target: TIER 1/2 execution, 0 sub-agents, 2-12 tool calls, <30s, SUCCESS")

print("""
================================================================================
CRITICAL SUCCESS CRITERIA
================================================================================

MUST ACHIEVE:
1. ✅ All 5 queries complete successfully (100% success rate)
2. ✅ ZERO task() calls across all queries (no sub-agent delegation)
3. ✅ Total tool calls <40 (vs 177 baseline)
4. ✅ Total cost <$1.00 (vs $7.18 baseline)
5. ✅ Total time <150s (vs 807s baseline)

FAILURE TRIGGERS:
- ❌ Any query uses task() tool (sub-agent delegation)
- ❌ Any query hits recursion limit
- ❌ Success rate <100%
- ❌ Query 3 fails or spirals searching (>5 tool calls)
- ❌ Query 1 uses site-by-site iteration (>15 tool calls)

================================================================================
""")
