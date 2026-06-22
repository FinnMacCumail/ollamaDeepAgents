#!/usr/bin/env python3
"""
Analyze 5 validation test traces to measure prompt rewrite effectiveness.
"""

import os
from langsmith import Client
from datetime import datetime
import json

# Initialize LangSmith client
client = Client(api_key=os.environ.get("LANGSMITH_API_KEY"))

# Trace IDs provided by user
TRACE_IDS = [
    "a29bd4a3-3260-4b7c-82e6-f33074fbf0ad",
    "7b8f2650-86c2-441e-a974-4450678dfafa",
    "6976c584-778f-4744-bab8-624f785c788d",
    "5488b4d8-b1ef-4a84-8471-e10731fa63ae",
    "943e978f-65aa-43f7-9419-69fd204de6f9",
]

# Baseline metrics from VALIDATION_TEST_SUITE.md
BASELINE = {
    "Query 1": {"tool_calls": 75, "llm_calls": 76, "time": 347, "cost": 2.00, "result": "SUCCESS"},
    "Query 2": {"tool_calls": 12, "llm_calls": 13, "time": 58, "cost": 0.51, "result": "SUCCESS"},
    "Query 3": {"tool_calls": 30, "llm_calls": 31, "time": 162, "cost": 1.60, "result": "FAILED"},
    "Query 4": {"tool_calls": 19, "llm_calls": 20, "time": 91, "cost": 0.77, "result": "FAILED"},
    "Query 5": {"tool_calls": 41, "llm_calls": 32, "time": 149, "cost": 2.30, "result": "FAILED"},
}

EXPECTED = {
    "Query 1": {"tool_calls": "5-8", "classification": "TIER 2", "subagents": "NO"},
    "Query 2": {"tool_calls": "2-3", "classification": "TIER 1", "subagents": "NO"},
    "Query 3": {"tool_calls": "2-3", "classification": "TIER 1", "subagents": "NO"},
    "Query 4": {"tool_calls": "5-8", "classification": "TIER 2", "subagents": "NO"},
    "Query 5": {"tool_calls": "8-12", "classification": "TIER 1", "subagents": "NO"},
}

# Query text mapping (from VALIDATION_TEST_SUITE.md)
QUERY_PATTERNS = {
    "dunder-mifflin": "Query 1",
    "dmi01-nashua-rtr01": "Query 2",
    "vlan 100": "Query 3",
    "nc state": "Query 4",
    "dm-nashua": "Query 5",
}


def identify_query(run_data):
    """Identify which query this trace represents."""
    inputs = run_data.get("inputs", {})
    query_text = str(inputs).lower()

    for pattern, query_name in QUERY_PATTERNS.items():
        if pattern in query_text:
            return query_name

    return "Unknown"


def count_tool_calls(run_data):
    """Count tool calls, specifically looking for task() calls."""
    # This is a placeholder - need to traverse child runs
    # Will be implemented based on actual trace structure
    return 0, 0  # (total_tool_calls, task_calls)


def analyze_trace(trace_id):
    """Fetch and analyze a single trace."""
    try:
        run = client.read_run(trace_id)

        # Basic info
        query_name = identify_query(run.dict())
        status = "SUCCESS" if run.error is None else "FAILED"

        # Duration
        if run.start_time and run.end_time:
            duration = (run.end_time - run.start_time).total_seconds()
        else:
            duration = None

        # Count child runs (tool calls, LLM calls)
        child_runs = list(client.list_runs(
            trace_id=trace_id,
            select=["id", "name", "run_type", "inputs", "outputs", "error"]
        ))

        tool_calls = []
        llm_calls = 0
        task_calls = 0
        write_todos_calls = 0
        think_calls = 0
        netbox_calls = 0

        for child in child_runs:
            if child.run_type == "tool":
                tool_calls.append(child.name)
                if child.name == "task":
                    task_calls += 1
                elif child.name == "write_todos":
                    write_todos_calls += 1
                elif child.name == "think":
                    think_calls += 1
                elif "netbox" in child.name.lower():
                    netbox_calls += 1
            elif child.run_type == "llm":
                llm_calls += 1

        # Token usage (from last LLM call with usage data)
        total_tokens = 0
        input_tokens = 0
        output_tokens = 0
        cached_tokens = 0

        for child in reversed(child_runs):
            if child.run_type == "llm" and hasattr(child, 'outputs') and child.outputs:
                usage = child.outputs.get('llm_output', {}).get('token_usage', {})
                if usage:
                    input_tokens += usage.get('prompt_tokens', 0)
                    output_tokens += usage.get('completion_tokens', 0)
                    cached_tokens += usage.get('prompt_tokens_details', {}).get('cached_tokens', 0)

        total_tokens = input_tokens + output_tokens

        # Cost estimate (Anthropic Sonnet 4 pricing)
        # Input: $3/1M, Output: $15/1M, Cached: $0.30/1M
        cost = (
            (input_tokens - cached_tokens) * 3 / 1_000_000 +
            output_tokens * 15 / 1_000_000 +
            cached_tokens * 0.30 / 1_000_000
        )

        # Error message if failed
        error_msg = run.error if run.error else None

        return {
            "trace_id": trace_id,
            "query_name": query_name,
            "status": status,
            "duration": duration,
            "total_tool_calls": len(tool_calls),
            "llm_calls": llm_calls,
            "task_calls": task_calls,
            "write_todos_calls": write_todos_calls,
            "think_calls": think_calls,
            "netbox_calls": netbox_calls,
            "tool_breakdown": tool_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "total_tokens": total_tokens,
            "estimated_cost": cost,
            "error": error_msg,
        }

    except Exception as e:
        return {
            "trace_id": trace_id,
            "error": f"Failed to fetch trace: {str(e)}",
        }


def print_analysis(results):
    """Print detailed analysis of results."""
    print("=" * 80)
    print("VALIDATION TEST RESULTS - Prompt Rewrite Effectiveness")
    print("=" * 80)
    print()

    # Individual query results
    for result in results:
        if "error" in result and result.get("query_name") is None:
            print(f"❌ Error fetching {result['trace_id']}: {result['error']}")
            continue

        query_name = result["query_name"]
        baseline = BASELINE.get(query_name, {})
        expected = EXPECTED.get(query_name, {})

        print(f"\n{query_name} - Trace: {result['trace_id'][:8]}...")
        print("-" * 80)

        # Status comparison
        baseline_status = baseline.get("result", "?")
        status_symbol = "✅" if result["status"] == "SUCCESS" else "❌"
        status_change = ""
        if baseline_status == "FAILED" and result["status"] == "SUCCESS":
            status_change = " (FIXED! 🎉)"
        elif baseline_status == "SUCCESS" and result["status"] == "FAILED":
            status_change = " (REGRESSION! 😱)"

        print(f"  Status: {status_symbol} {result['status']}{status_change}")
        if result.get("error"):
            print(f"  Error: {result['error']}")

        # Duration
        if result.get("duration"):
            baseline_time = baseline.get("time", 0)
            time_change = ((result["duration"] - baseline_time) / baseline_time * 100) if baseline_time else 0
            time_symbol = "📉" if time_change < 0 else "📈"
            print(f"  Duration: {result['duration']:.1f}s (baseline: {baseline_time}s, {time_symbol} {time_change:+.0f}%)")

        # Tool calls
        baseline_calls = baseline.get("tool_calls", 0)
        calls_change = ((result["total_tool_calls"] - baseline_calls) / baseline_calls * 100) if baseline_calls else 0
        calls_symbol = "📉" if calls_change < 0 else "📈"
        print(f"  Tool calls: {result['total_tool_calls']} (baseline: {baseline_calls}, {calls_symbol} {calls_change:+.0f}%)")
        print(f"    - NetBox API calls: {result['netbox_calls']}")
        print(f"    - task() calls (sub-agents): {result['task_calls']} (expected: 0)")
        print(f"    - write_todos() calls: {result['write_todos_calls']}")
        print(f"    - think() calls: {result['think_calls']}")

        # Sub-agent validation
        if result["task_calls"] > 0:
            print(f"    ⚠️  FAILED: Sub-agents spawned (expected 0)")
        else:
            print(f"    ✅ PASSED: No sub-agents spawned")

        # LLM calls
        baseline_llm = baseline.get("llm_calls", 0)
        print(f"  LLM calls: {result['llm_calls']} (baseline: {baseline_llm})")

        # Tokens
        print(f"  Tokens: {result['total_tokens']:,} ({result['input_tokens']:,} in, {result['output_tokens']:,} out)")
        if result['cached_tokens'] > 0:
            cache_rate = result['cached_tokens'] / result['input_tokens'] * 100
            print(f"    - Cached: {result['cached_tokens']:,} ({cache_rate:.1f}% cache hit rate)")

        # Cost
        baseline_cost = baseline.get("cost", 0)
        cost_change = ((result["estimated_cost"] - baseline_cost) / baseline_cost * 100) if baseline_cost else 0
        cost_symbol = "📉" if cost_change < 0 else "📈"
        print(f"  Cost: ${result['estimated_cost']:.4f} (baseline: ${baseline_cost:.2f}, {cost_symbol} {cost_change:+.0f}%)")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Aggregate metrics
    total_duration = sum(r.get("duration", 0) for r in results if r.get("duration"))
    total_tool_calls = sum(r.get("total_tool_calls", 0) for r in results)
    total_task_calls = sum(r.get("task_calls", 0) for r in results)
    total_cost = sum(r.get("estimated_cost", 0) for r in results)
    success_count = sum(1 for r in results if r.get("status") == "SUCCESS")

    baseline_duration = sum(BASELINE[q]["time"] for q in BASELINE)
    baseline_tool_calls = sum(BASELINE[q]["tool_calls"] for q in BASELINE)
    baseline_cost = sum(BASELINE[q]["cost"] for q in BASELINE)
    baseline_success = sum(1 for q in BASELINE if BASELINE[q]["result"] == "SUCCESS")

    print(f"\nSuccess Rate:")
    print(f"  Current: {success_count}/5 ({success_count/5*100:.0f}%)")
    print(f"  Baseline: {baseline_success}/5 (40%)")
    if success_count == 5:
        print(f"  ✅ TARGET MET: 100% success rate achieved!")
    else:
        print(f"  ❌ TARGET MISSED: {5-success_count} queries still failing")

    print(f"\nSub-Agent Usage:")
    print(f"  Total task() calls: {total_task_calls}")
    if total_task_calls == 0:
        print(f"  ✅ TARGET MET: Zero sub-agent spawns (critical success criterion)")
    else:
        print(f"  ❌ TARGET MISSED: Sub-agents still being used")

    print(f"\nEfficiency Metrics:")
    print(f"  Total duration: {total_duration:.0f}s (baseline: {baseline_duration}s, {(total_duration-baseline_duration)/baseline_duration*100:+.0f}%)")
    print(f"  Total tool calls: {total_tool_calls} (baseline: {baseline_tool_calls}, {(total_tool_calls-baseline_tool_calls)/baseline_tool_calls*100:+.0f}%)")
    print(f"  Total cost: ${total_cost:.2f} (baseline: ${baseline_cost:.2f}, {(total_cost-baseline_cost)/baseline_cost*100:+.0f}%)")

    print(f"\nValidation Criteria:")
    criteria_met = []
    criteria_failed = []

    if success_count == 5:
        criteria_met.append("✅ All 5 queries complete successfully")
    else:
        criteria_failed.append(f"❌ Only {success_count}/5 queries succeeded")

    if total_task_calls == 0:
        criteria_met.append("✅ ZERO task() calls (no sub-agent delegation)")
    else:
        criteria_failed.append(f"❌ {total_task_calls} task() calls detected")

    if total_tool_calls < 40:
        criteria_met.append(f"✅ Total tool calls {total_tool_calls} < 40 target")
    else:
        criteria_failed.append(f"❌ Total tool calls {total_tool_calls} >= 40")

    if total_cost < 1.00:
        criteria_met.append(f"✅ Total cost ${total_cost:.2f} < $1.00 target")
    else:
        criteria_failed.append(f"❌ Total cost ${total_cost:.2f} >= $1.00")

    if total_duration < 150:
        criteria_met.append(f"✅ Total time {total_duration:.0f}s < 150s target")
    else:
        criteria_failed.append(f"❌ Total time {total_duration:.0f}s >= 150s")

    print("\nMET:")
    for criterion in criteria_met:
        print(f"  {criterion}")

    if criteria_failed:
        print("\nFAILED:")
        for criterion in criteria_failed:
            print(f"  {criterion}")

    # Overall pass/fail
    print("\n" + "=" * 80)
    if len(criteria_failed) == 0:
        print("🎉 VALIDATION PASSED - All criteria met!")
    else:
        print(f"⚠️  VALIDATION PARTIAL - {len(criteria_failed)} criteria failed")
    print("=" * 80)


def main():
    print("Fetching and analyzing 5 validation traces...")
    print()

    results = []
    for trace_id in TRACE_IDS:
        print(f"Analyzing {trace_id}...")
        result = analyze_trace(trace_id)
        results.append(result)

    print()
    print_analysis(results)

    # Save detailed results to JSON
    output_file = "/home/ola/dev/rnd/deepagents/examples/netbox/validation_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
