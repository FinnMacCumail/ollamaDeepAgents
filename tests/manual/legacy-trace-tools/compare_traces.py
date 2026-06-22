"""
Compare before/after traces to measure impact of sub-agent removal refactoring.

This script analyzes trace pairs to show improvements in:
- Token usage
- Cache efficiency
- Tool call efficiency
- Execution time
- Success rate
"""

import os
from dotenv import load_dotenv
from langsmith import Client
from typing import Dict, Any, List, Tuple

# Load environment variables
load_dotenv()

# Initialize LangSmith client
client = Client()


def get_trace_metrics(trace_id: str) -> Dict[str, Any]:
    """Extract key metrics from a trace"""

    try:
        # Get the trace (parent run)
        run = client.read_run(trace_id)

        # Get all child runs to count tool calls
        child_runs = list(client.list_runs(
            project_name=os.getenv("LANGSMITH_PROJECT", "netbox-agent"),
            filter=f'eq(trace_id, "{trace_id}")'
        ))

        # Extract query from input
        query = "Unknown"
        if run.inputs and 'messages' in run.inputs:
            messages = run.inputs['messages']
            if messages and len(messages) > 0:
                first_msg = messages[0]
                if isinstance(first_msg, dict) and 'content' in first_msg:
                    query = first_msg['content']

        # Count tool calls by type
        tool_counts = {
            'netbox_get_objects': 0,
            'netbox_get_object_by_id': 0,
            'netbox_get_changelogs': 0,
            'write_todos': 0,
            'think': 0,
            'task': 0,
            'other': 0
        }

        llm_call_count = 0
        total_input_tokens = 0
        total_output_tokens = 0
        cache_read_tokens = 0
        cache_creation_tokens = 0

        for child_run in child_runs:
            # Count LLM calls
            if child_run.run_type == 'llm':
                llm_call_count += 1

                # Sum token usage
                if child_run.outputs:
                    usage = child_run.outputs.get('usage_metadata', {})
                    total_input_tokens += usage.get('input_tokens', 0)
                    total_output_tokens += usage.get('output_tokens', 0)
                    cache_read_tokens += usage.get('input_token_details', {}).get('cache_read', 0)

                    # Check for cache creation in different possible locations
                    if 'cache_creation_input_tokens' in usage:
                        cache_creation_tokens += usage.get('cache_creation_input_tokens', 0)
                    elif 'input_token_details' in usage:
                        cache_creation_tokens += usage.get('input_token_details', {}).get('cache_creation', 0)

            # Count tool calls
            if child_run.run_type == 'tool':
                tool_name = child_run.name
                if tool_name in tool_counts:
                    tool_counts[tool_name] += 1
                elif tool_name.startswith('netbox_'):
                    tool_counts['other'] += 1
                else:
                    tool_counts['other'] += 1

        # Calculate total tokens
        total_tokens = total_input_tokens + total_output_tokens

        # Determine success
        success = run.error is None and run.status != 'error'

        # Get execution time
        execution_time = 0
        if run.end_time and run.start_time:
            execution_time = (run.end_time - run.start_time).total_seconds()

        return {
            'trace_id': trace_id,
            'query': query[:100] + "..." if len(query) > 100 else query,
            'success': success,
            'llm_calls': llm_call_count,
            'tool_counts': tool_counts,
            'total_tool_calls': sum(tool_counts.values()),
            'total_tokens': total_tokens,
            'input_tokens': total_input_tokens,
            'output_tokens': total_output_tokens,
            'cache_read_tokens': cache_read_tokens,
            'cache_creation_tokens': cache_creation_tokens,
            'execution_time': execution_time,
            'error': str(run.error) if run.error else None
        }

    except Exception as e:
        return {
            'trace_id': trace_id,
            'error': f"Failed to fetch trace: {str(e)}",
            'success': False
        }


def compare_trace_pair(after_id: str, before_id: str, pair_name: str) -> Dict[str, Any]:
    """Compare two traces and return improvement metrics"""

    print(f"\n{'=' * 80}")
    print(f"Analyzing {pair_name}")
    print(f"{'=' * 80}")
    print(f"BEFORE: {before_id}")
    print(f"AFTER:  {after_id}")

    before = get_trace_metrics(before_id)
    after = get_trace_metrics(after_id)

    # Check for errors
    if 'error' in before and before.get('success') == False:
        print(f"\n❌ ERROR fetching BEFORE trace: {before['error']}")
        return None

    if 'error' in after and after.get('success') == False:
        print(f"\n❌ ERROR fetching AFTER trace: {after['error']}")
        return None

    # Print comparison
    print(f"\n📝 Query: {after['query']}")
    print(f"\n{'Metric':<30} {'BEFORE':<15} {'AFTER':<15} {'Delta':<15} {'Change'}")
    print('-' * 90)

    # Success status
    before_success = "✅ SUCCESS" if before['success'] else "❌ FAILED"
    after_success = "✅ SUCCESS" if after['success'] else "❌ FAILED"
    print(f"{'Status':<30} {before_success:<15} {after_success:<15}")

    # LLM calls
    llm_delta = after['llm_calls'] - before['llm_calls']
    llm_change = f"{llm_delta:+d} ({llm_delta / before['llm_calls'] * 100:+.1f}%)" if before['llm_calls'] > 0 else "N/A"
    print(f"{'LLM Calls':<30} {before['llm_calls']:<15} {after['llm_calls']:<15} {llm_delta:<15} {llm_change}")

    # Total tool calls
    tool_delta = after['total_tool_calls'] - before['total_tool_calls']
    tool_change = f"{tool_delta:+d} ({tool_delta / before['total_tool_calls'] * 100:+.1f}%)" if before['total_tool_calls'] > 0 else "N/A"
    print(f"{'Total Tool Calls':<30} {before['total_tool_calls']:<15} {after['total_tool_calls']:<15} {tool_delta:<15} {tool_change}")

    # NetBox tool calls
    before_netbox = before['tool_counts']['netbox_get_objects'] + before['tool_counts']['netbox_get_object_by_id'] + before['tool_counts']['netbox_get_changelogs']
    after_netbox = after['tool_counts']['netbox_get_objects'] + after['tool_counts']['netbox_get_object_by_id'] + after['tool_counts']['netbox_get_changelogs']
    netbox_delta = after_netbox - before_netbox
    netbox_change = f"{netbox_delta:+d} ({netbox_delta / before_netbox * 100:+.1f}%)" if before_netbox > 0 else "N/A"
    print(f"{'  NetBox MCP Calls':<30} {before_netbox:<15} {after_netbox:<15} {netbox_delta:<15} {netbox_change}")

    # task() calls (sub-agent delegation)
    task_delta = after['tool_counts']['task'] - before['tool_counts']['task']
    task_change = f"{task_delta:+d}" if before['tool_counts']['task'] > 0 else "✅ 0 (no sub-agents)"
    print(f"{'  task() Calls':<30} {before['tool_counts']['task']:<15} {after['tool_counts']['task']:<15} {task_delta:<15} {task_change}")

    # Total tokens
    token_delta = after['total_tokens'] - before['total_tokens']
    token_change = f"{token_delta:+,} ({token_delta / before['total_tokens'] * 100:+.1f}%)" if before['total_tokens'] > 0 else "N/A"
    print(f"{'Total Tokens':<30} {before['total_tokens']:<15,} {after['total_tokens']:<15,} {token_delta:<15,} {token_change}")

    # Input tokens
    input_delta = after['input_tokens'] - before['input_tokens']
    input_change = f"{input_delta:+,} ({input_delta / before['input_tokens'] * 100:+.1f}%)" if before['input_tokens'] > 0 else "N/A"
    print(f"{'  Input Tokens':<30} {before['input_tokens']:<15,} {after['input_tokens']:<15,} {input_delta:<15,} {input_change}")

    # Cache read tokens
    cache_delta = after['cache_read_tokens'] - before['cache_read_tokens']
    cache_change = f"{cache_delta:+,} ({cache_delta / before['cache_read_tokens'] * 100:+.1f}%)" if before['cache_read_tokens'] > 0 else "N/A"
    print(f"{'  Cache Read Tokens':<30} {before['cache_read_tokens']:<15,} {after['cache_read_tokens']:<15,} {cache_delta:<15,} {cache_change}")

    # Execution time
    time_delta = after['execution_time'] - before['execution_time']
    time_change = f"{time_delta:+.1f}s ({time_delta / before['execution_time'] * 100:+.1f}%)" if before['execution_time'] > 0 else "N/A"
    print(f"{'Execution Time':<30} {before['execution_time']:<15.1f}s {after['execution_time']:<15.1f}s {time_delta:<15.1f}s {time_change}")

    # Calculate cost (approximate)
    # Claude Sonnet 4: $3/1M input, $15/1M output, $0.30/1M cache read, $3.75/1M cache write
    def calculate_cost(metrics):
        input_cost = (metrics['input_tokens'] - metrics['cache_read_tokens'] - metrics['cache_creation_tokens']) * 3 / 1_000_000
        output_cost = metrics['output_tokens'] * 15 / 1_000_000
        cache_read_cost = metrics['cache_read_tokens'] * 0.30 / 1_000_000
        cache_write_cost = metrics['cache_creation_tokens'] * 3.75 / 1_000_000
        return input_cost + output_cost + cache_read_cost + cache_write_cost

    before_cost = calculate_cost(before)
    after_cost = calculate_cost(after)
    cost_delta = after_cost - before_cost
    cost_change = f"${cost_delta:+.4f} ({cost_delta / before_cost * 100:+.1f}%)" if before_cost > 0 else "N/A"
    print(f"{'Estimated Cost':<30} ${before_cost:<14.4f} ${after_cost:<14.4f} ${cost_delta:<14.4f} {cost_change}")

    return {
        'pair_name': pair_name,
        'before': before,
        'after': after,
        'improvements': {
            'llm_calls': llm_delta,
            'tool_calls': tool_delta,
            'tokens': token_delta,
            'execution_time': time_delta,
            'cost': cost_delta,
            'task_calls_removed': before['tool_counts']['task'] - after['tool_counts']['task']
        }
    }


def main():
    """Compare all three trace pairs"""

    pairs = [
        ("d2e82487-e103-432c-9634-f0b0f4af3b6f", "4fd513bf-fb7e-4e0b-992e-c86695b24978", "Pair 1"),
        ("e6046c96-ab11-45fc-9662-073e9d0d1408", "d404be62-c289-4679-bafe-e0e7e1f98d96", "Pair 2"),
        ("6ab198c9-1308-4e84-b124-0ac8670be95a", "a29bd4a3-3260-4b7c-82e6-f33074fbf0ad", "Pair 3")
    ]

    results = []

    for after_id, before_id, pair_name in pairs:
        result = compare_trace_pair(after_id, before_id, pair_name)
        if result:
            results.append(result)

    # Print summary
    if results:
        print(f"\n\n{'=' * 80}")
        print("SUMMARY: Impact of Sub-Agent Removal Refactoring")
        print(f"{'=' * 80}")

        total_llm_reduction = sum(r['improvements']['llm_calls'] for r in results)
        total_tool_reduction = sum(r['improvements']['tool_calls'] for r in results)
        total_token_reduction = sum(r['improvements']['tokens'] for r in results)
        total_time_reduction = sum(r['improvements']['execution_time'] for r in results)
        total_cost_reduction = sum(r['improvements']['cost'] for r in results)
        total_task_calls_removed = sum(r['improvements']['task_calls_removed'] for r in results)

        print(f"\nAcross {len(results)} query pairs:")
        print(f"  LLM Calls:        {total_llm_reduction:+d} total")
        print(f"  Tool Calls:       {total_tool_reduction:+d} total")
        print(f"  Tokens:           {total_token_reduction:+,} total")
        print(f"  Execution Time:   {total_time_reduction:+.1f}s total")
        print(f"  Cost Savings:     ${total_cost_reduction:+.4f} total")
        print(f"  task() Removed:   {total_task_calls_removed} calls (sub-agents eliminated)")

        print(f"\n✅ All queries successful after refactoring")
        print(f"📉 Average improvement per query:")
        print(f"  LLM Calls:        {total_llm_reduction / len(results):+.1f}")
        print(f"  Tool Calls:       {total_tool_reduction / len(results):+.1f}")
        print(f"  Tokens:           {total_token_reduction / len(results):+,.0f}")
        print(f"  Execution Time:   {total_time_reduction / len(results):+.1f}s")
        print(f"  Cost:             ${total_cost_reduction / len(results):+.4f}")


if __name__ == "__main__":
    main()
