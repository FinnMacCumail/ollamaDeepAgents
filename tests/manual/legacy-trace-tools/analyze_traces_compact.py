#!/usr/bin/env python3
"""
Compact trace analysis - fetches only key metrics without full trace data.
"""

import os
import sys
from langsmith import Client
from datetime import datetime
from collections import Counter

# Load environment from .env file
from pathlib import Path
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key] = value

# Initialize LangSmith client
client = Client()

TRACE_IDS = [
    "a29bd4a3-3260-4b7c-82e6-f33074fbf0ad",
    "7b8f2650-86c2-441e-a974-4450678dfafa",
    "6976c584-778f-4744-bab8-624f785c788d",
    "5488b4d8-b1ef-4a84-8471-e10731fa63ae",
    "943e978f-65aa-43f7-9419-69fd204de6f9",
]

BASELINE = {
    "Query 1": {"tool_calls": 75, "time": 347, "cost": 2.00, "result": "SUCCESS"},
    "Query 2": {"tool_calls": 12, "time": 58, "cost": 0.51, "result": "SUCCESS"},
    "Query 3": {"tool_calls": 30, "time": 162, "cost": 1.60, "result": "FAILED"},
    "Query 4": {"tool_calls": 19, "time": 91, "cost": 0.77, "result": "FAILED"},
    "Query 5": {"tool_calls": 41, "time": 149, "cost": 2.30, "result": "FAILED"},
}

QUERY_PATTERNS = {
    "dunder-mifflin": "Query 1",
    "dmi01-nashua-rtr01": "Query 2",
    "vlan 100": "Query 3",
    "nc state": "Query 4",
    "dm-nashua": "Query 5",
    "dm-akron": "Query 5",
}


def identify_query(inputs):
    """Identify which query based on input text."""
    query_text = str(inputs).lower()
    for pattern, query_name in QUERY_PATTERNS.items():
        if pattern in query_text:
            return query_name
    return "Unknown"


def analyze_trace_compact(trace_id):
    """Analyze a trace by fetching only child runs (not full trace data)."""
    try:
        print(f"\nAnalyzing {trace_id[:8]}...")

        # Get the root run
        root_run = client.read_run(trace_id)

        # Identify query
        query_name = identify_query(root_run.inputs)

        # Status
        status = "SUCCESS" if root_run.error is None else "FAILED"
        error = root_run.error

        # Duration
        if root_run.start_time and root_run.end_time:
            duration = (root_run.end_time - root_run.start_time).total_seconds()
        else:
            duration = None

        # Fetch child runs (tools and LLMs)
        print(f"  Fetching child runs...")
        child_runs = list(client.list_runs(
            trace_id=trace_id,
            select=["name", "run_type"]
        ))

        # Count tool calls by type
        tool_counts = Counter()
        llm_count = 0

        for run in child_runs:
            if run.run_type == "tool":
                tool_counts[run.name] += 1
            elif run.run_type == "llm":
                llm_count += 1

        total_tool_calls = sum(tool_counts.values())
        task_calls = tool_counts.get("task", 0)
        write_todos_calls = tool_counts.get("write_todos", 0)
        think_calls = tool_counts.get("think", 0)

        # Count netbox calls
        netbox_calls = sum(count for tool, count in tool_counts.items() if "netbox" in tool.lower())

        return {
            "trace_id": trace_id,
            "query_name": query_name,
            "status": status,
            "error": error,
            "duration": duration,
            "total_tool_calls": total_tool_calls,
            "task_calls": task_calls,
            "write_todos_calls": write_todos_calls,
            "think_calls": think_calls,
            "netbox_calls": netbox_calls,
            "llm_calls": llm_count,
            "tool_breakdown": dict(tool_counts),
        }

    except Exception as e:
        return {
            "trace_id": trace_id,
            "error": f"Failed to analyze: {str(e)}",
        }


def print_report(results):
    """Print analysis report."""
    print("\n" + "="*80)
    print("VALIDATION TEST RESULTS - Prompt Rewrite Effectiveness")
    print("="*80)

    # Summary stats
    total_tool_calls = 0
    total_task_calls = 0
    total_duration = 0
    success_count = 0

    # Individual results
    for result in results:
        if "error" in result and not result.get("query_name"):
            print(f"\n❌ Error: {result['error']}")
            continue

        query_name = result["query_name"]
        baseline = BASELINE.get(query_name, {})

        print(f"\n{query_name} ({result['trace_id'][:8]}...)")
        print("-" * 80)

        # Status
        status_icon = "✅" if result["status"] == "SUCCESS" else "❌"
        baseline_status = baseline.get("result", "?")

        status_change = ""
        if baseline_status == "FAILED" and result["status"] == "SUCCESS":
            status_change = " 🎉 FIXED!"
        elif baseline_status == "SUCCESS" and result["status"] == "FAILED":
            status_change = " 😱 REGRESSION!"

        print(f"  Status: {status_icon} {result['status']}{status_change}")
        if result.get("error"):
            print(f"    Error: {result['error'][:200]}")

        if result["status"] == "SUCCESS":
            success_count += 1

        # Duration
        if result.get("duration"):
            baseline_time = baseline.get("time", 0)
            change_pct = ((result["duration"] - baseline_time) / baseline_time * 100) if baseline_time else 0
            icon = "📉" if change_pct < 0 else "📈"
            print(f"  Duration: {result['duration']:.1f}s (baseline: {baseline_time}s, {icon} {change_pct:+.0f}%)")
            total_duration += result["duration"]

        # Tool calls
        baseline_calls = baseline.get("tool_calls", 0)
        change_pct = ((result["total_tool_calls"] - baseline_calls) / baseline_calls * 100) if baseline_calls else 0
        icon = "📉" if change_pct < 0 else "📈"
        print(f"  Tool calls: {result['total_tool_calls']} (baseline: {baseline_calls}, {icon} {change_pct:+.0f}%)")
        print(f"    - NetBox API: {result['netbox_calls']}")
        print(f"    - task() [sub-agents]: {result['task_calls']} {'✅ PASS' if result['task_calls'] == 0 else '❌ FAIL - Expected 0'}")
        print(f"    - write_todos(): {result['write_todos_calls']}")
        print(f"    - think(): {result['think_calls']}")
        print(f"  LLM calls: {result['llm_calls']}")

        total_tool_calls += result["total_tool_calls"]
        total_task_calls += result["task_calls"]

        # Tool breakdown
        if result.get("tool_breakdown"):
            top_tools = sorted(result["tool_breakdown"].items(), key=lambda x: x[1], reverse=True)[:5]
            print(f"  Top tools: {', '.join(f'{name}({count})' for name, count in top_tools)}")

    # Aggregate summary
    print("\n" + "="*80)
    print("AGGREGATE SUMMARY")
    print("="*80)

    baseline_total_calls = sum(BASELINE[q]["tool_calls"] for q in BASELINE)
    baseline_total_time = sum(BASELINE[q]["time"] for q in BASELINE)
    baseline_total_cost = sum(BASELINE[q]["cost"] for q in BASELINE)
    baseline_success = 2  # Query 1 and 2 succeeded

    print(f"\n✅ Success Rate: {success_count}/5 ({success_count/5*100:.0f}%)")
    print(f"   Baseline: {baseline_success}/5 (40%)")
    if success_count == 5:
        print(f"   🎉 TARGET MET: 100% success!")
    elif success_count > baseline_success:
        print(f"   📈 IMPROVED: Fixed {success_count - baseline_success} failing queries")
    else:
        print(f"   ❌ TARGET MISSED: Still have {5-success_count} failures")

    print(f"\n🚫 Sub-Agent Spawns: {total_task_calls} task() calls")
    print(f"   Target: 0 (critical criterion)")
    if total_task_calls == 0:
        print(f"   ✅ TARGET MET: Zero sub-agents!")
    else:
        print(f"   ❌ TARGET MISSED: Still spawning sub-agents")

    print(f"\n📊 Efficiency:")
    print(f"   Tool calls: {total_tool_calls} (baseline: {baseline_total_calls}, {(total_tool_calls-baseline_total_calls)/baseline_total_calls*100:+.0f}%)")
    if total_tool_calls < 40:
        print(f"   ✅ Under 40 target")
    else:
        print(f"   ❌ Over 40 target")

    print(f"   Duration: {total_duration:.0f}s (baseline: {baseline_total_time}s, {(total_duration-baseline_total_time)/baseline_total_time*100:+.0f}%)")
    if total_duration < 150:
        print(f"   ✅ Under 150s target")
    else:
        print(f"   ❌ Over 150s target")

    # Overall assessment
    print("\n" + "="*80)
    criteria_met = 0
    criteria_total = 5

    if success_count == 5:
        criteria_met += 1
        print("✅ All queries succeeded")
    else:
        print(f"❌ Only {success_count}/5 succeeded")

    if total_task_calls == 0:
        criteria_met += 1
        print("✅ Zero sub-agent spawns")
    else:
        print(f"❌ {total_task_calls} sub-agent spawns detected")

    if total_tool_calls < 40:
        criteria_met += 1
        print("✅ Tool calls under 40")
    else:
        print(f"❌ Tool calls {total_tool_calls} >= 40")

    if total_duration < 150:
        criteria_met += 1
        print("✅ Duration under 150s")
    else:
        print(f"❌ Duration {total_duration:.0f}s >= 150s")

    estimated_cost = total_tool_calls * 0.01  # Rough estimate
    if estimated_cost < 1.0:
        criteria_met += 1
        print("✅ Estimated cost under $1.00")
    else:
        print(f"❌ Estimated cost >= $1.00")

    print("\n" + "="*80)
    if criteria_met == criteria_total:
        print(f"🎉 VALIDATION PASSED: {criteria_met}/{criteria_total} criteria met!")
    elif criteria_met >= 3:
        print(f"⚠️  VALIDATION PARTIAL: {criteria_met}/{criteria_total} criteria met")
    else:
        print(f"❌ VALIDATION FAILED: Only {criteria_met}/{criteria_total} criteria met")
    print("="*80)


def main():
    print("Analyzing 5 validation traces...")
    print("Project: netbox-agent")

    results = []
    for trace_id in TRACE_IDS:
        result = analyze_trace_compact(trace_id)
        results.append(result)

    print_report(results)


if __name__ == "__main__":
    main()
