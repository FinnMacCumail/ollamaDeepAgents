"""
Detailed trace analysis with better token extraction.
"""

import os
from dotenv import load_dotenv
from langsmith import Client
import json

# Load environment variables
load_dotenv()

# Initialize LangSmith client
client = Client()


def analyze_trace_detailed(trace_id: str, label: str):
    """Analyze a single trace with detailed output"""

    print(f"\n{'=' * 100}")
    print(f"{label}: {trace_id}")
    print(f"{'=' * 100}")

    try:
        # Get the parent run
        run = client.read_run(trace_id)

        # Get query
        query = "Unknown"
        if run.inputs and 'messages' in run.inputs:
            messages = run.inputs['messages']
            if messages and len(messages) > 0:
                first_msg = messages[0]
                if isinstance(first_msg, dict) and 'content' in first_msg:
                    query = first_msg['content']

        print(f"\n📝 Query: {query[:150]}{'...' if len(query) > 150 else ''}")
        print(f"\n🎯 Status: {'✅ SUCCESS' if run.error is None else f'❌ FAILED: {run.error}'}")

        if run.end_time and run.start_time:
            duration = (run.end_time - run.start_time).total_seconds()
            print(f"⏱️  Duration: {duration:.1f}s")

        # Get all child runs
        child_runs = list(client.list_runs(
            project_name=os.getenv("LANGSMITH_PROJECT", "netbox-agent"),
            filter=f'eq(trace_id, "{trace_id}")'
        ))

        print(f"\n📊 Total Runs: {len(child_runs)}")

        # Analyze by run type
        llm_runs = [r for r in child_runs if r.run_type == 'llm']
        tool_runs = [r for r in child_runs if r.run_type == 'tool']

        print(f"  LLM Calls: {len(llm_runs)}")
        print(f"  Tool Calls: {len(tool_runs)}")

        # Count tools by name
        tool_counts = {}
        for tool_run in tool_runs:
            name = tool_run.name
            tool_counts[name] = tool_counts.get(name, 0) + 1

        if tool_counts:
            print(f"\n🔧 Tool Call Breakdown:")
            for tool_name in sorted(tool_counts.keys()):
                count = tool_counts[tool_name]
                print(f"  {tool_name}: {count}")

        # Try to extract token usage from LLM runs
        print(f"\n💾 Token Analysis:")

        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_creation = 0

        for idx, llm_run in enumerate(llm_runs, 1):
            # Try multiple ways to get token usage
            usage = None

            # Method 1: Check outputs.usage_metadata
            if llm_run.outputs and 'usage_metadata' in llm_run.outputs:
                usage = llm_run.outputs['usage_metadata']

            # Method 2: Check outputs directly
            elif llm_run.outputs:
                # Sometimes usage is at top level of outputs
                if 'input_tokens' in llm_run.outputs:
                    usage = llm_run.outputs

            if usage:
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)

                # Try different keys for cache tokens
                cache_read = 0
                cache_creation = 0

                if 'input_token_details' in usage:
                    cache_read = usage['input_token_details'].get('cache_read', 0)
                    cache_creation = usage['input_token_details'].get('cache_creation', 0)
                elif 'cache_read_input_tokens' in usage:
                    cache_read = usage.get('cache_read_input_tokens', 0)
                    cache_creation = usage.get('cache_creation_input_tokens', 0)

                total_input += input_tokens
                total_output += output_tokens
                total_cache_read += cache_read
                total_cache_creation += cache_creation

                if input_tokens > 0:
                    cache_info = ""
                    if cache_read > 0:
                        cache_info += f" (cache read: {cache_read:,})"
                    if cache_creation > 0:
                        cache_info += f" (cache write: {cache_creation:,})"

                    print(f"  LLM Call {idx}: {input_tokens:,} in / {output_tokens:,} out{cache_info}")

        if total_input > 0:
            print(f"\n📈 Total Tokens:")
            print(f"  Input:          {total_input:,}")
            print(f"  Output:         {total_output:,}")
            print(f"  Total:          {total_input + total_output:,}")

            if total_cache_read > 0:
                cache_hit_rate = (total_cache_read / total_input * 100) if total_input > 0 else 0
                print(f"  Cache Read:     {total_cache_read:,} ({cache_hit_rate:.1f}% hit rate)")

            if total_cache_creation > 0:
                print(f"  Cache Created:  {total_cache_creation:,}")

            # Calculate cost
            # Claude Sonnet 4: $3/1M input, $15/1M output, $0.30/1M cache read, $3.75/1M cache write
            normal_input = total_input - total_cache_read - total_cache_creation
            input_cost = normal_input * 3 / 1_000_000
            output_cost = total_output * 15 / 1_000_000
            cache_read_cost = total_cache_read * 0.30 / 1_000_000
            cache_write_cost = total_cache_creation * 3.75 / 1_000_000
            total_cost = input_cost + output_cost + cache_read_cost + cache_write_cost

            print(f"\n💰 Estimated Cost: ${total_cost:.4f}")
            print(f"  Input:          ${input_cost:.4f}")
            print(f"  Output:         ${output_cost:.4f}")
            print(f"  Cache Read:     ${cache_read_cost:.4f}")
            print(f"  Cache Write:    ${cache_write_cost:.4f}")
        else:
            print("  ⚠️  No token usage data found in trace")

        return {
            'success': run.error is None,
            'query': query,
            'llm_calls': len(llm_runs),
            'tool_calls': len(tool_runs),
            'tool_counts': tool_counts,
            'total_input_tokens': total_input,
            'total_output_tokens': total_output,
            'cache_read_tokens': total_cache_read,
            'cache_creation_tokens': total_cache_creation,
            'duration': (run.end_time - run.start_time).total_seconds() if run.end_time and run.start_time else 0
        }

    except Exception as e:
        print(f"❌ Error analyzing trace: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def compare_pair(before_id: str, after_id: str, pair_name: str):
    """Compare a before/after pair"""

    print(f"\n\n{'#' * 100}")
    print(f"# {pair_name}")
    print(f"{'#' * 100}")

    before = analyze_trace_detailed(before_id, "BEFORE")
    after = analyze_trace_detailed(after_id, "AFTER")

    if before and after:
        print(f"\n{'=' * 100}")
        print(f"COMPARISON: {pair_name}")
        print(f"{'=' * 100}")

        print(f"\n{'Metric':<30} {'BEFORE':<20} {'AFTER':<20} {'Delta':<20}")
        print('-' * 90)

        # LLM calls
        llm_delta = after['llm_calls'] - before['llm_calls']
        llm_pct = f"({llm_delta / before['llm_calls'] * 100:+.1f}%)" if before['llm_calls'] > 0 else ""
        print(f"{'LLM Calls':<30} {before['llm_calls']:<20} {after['llm_calls']:<20} {llm_delta:+d} {llm_pct}")

        # Tool calls
        tool_delta = after['tool_calls'] - before['tool_calls']
        tool_pct = f"({tool_delta / before['tool_calls'] * 100:+.1f}%)" if before['tool_calls'] > 0 else ""
        print(f"{'Tool Calls':<30} {before['tool_calls']:<20} {after['tool_calls']:<20} {tool_delta:+d} {tool_pct}")

        # Tokens
        if before['total_input_tokens'] > 0 and after['total_input_tokens'] > 0:
            token_delta = (after['total_input_tokens'] + after['total_output_tokens']) - (before['total_input_tokens'] + before['total_output_tokens'])
            token_pct = f"({token_delta / (before['total_input_tokens'] + before['total_output_tokens']) * 100:+.1f}%)"
            print(f"{'Total Tokens':<30} {before['total_input_tokens'] + before['total_output_tokens']:<20,} {after['total_input_tokens'] + after['total_output_tokens']:<20,} {token_delta:+,} {token_pct}")

            # Cache efficiency
            if after['cache_read_tokens'] > 0:
                after_cache_rate = after['cache_read_tokens'] / after['total_input_tokens'] * 100
                print(f"{'Cache Hit Rate':<30} {'N/A':<20} {f'{after_cache_rate:.1f}%':<20} {'N/A'}")

        # Duration
        time_delta = after['duration'] - before['duration']
        time_pct = f"({time_delta / before['duration'] * 100:+.1f}%)" if before['duration'] > 0 else ""
        print(f"{'Duration':<30} {f'{before["duration"]:.1f}s':<20} {f'{after["duration"]:.1f}s':<20} {f'{time_delta:+.1f}s'} {time_pct}")


def main():
    """Analyze all three pairs"""

    pairs = [
        ("4fd513bf-fb7e-4e0b-992e-c86695b24978", "d2e82487-e103-432c-9634-f0b0f4af3b6f", "Pair 1: NC State Racks Query"),
        ("d404be62-c289-4679-bafe-e0e7e1f98d96", "e6046c96-ab11-45fc-9662-073e9d0d1408", "Pair 2: VLAN 100 Deployment Query"),
        ("a29bd4a3-3260-4b7c-82e6-f33074fbf0ad", "6ab198c9-1308-4e84-b124-0ac8670be95a", "Pair 3: Dunder-Mifflin Sites Query")
    ]

    for before_id, after_id, pair_name in pairs:
        compare_pair(before_id, after_id, pair_name)


if __name__ == "__main__":
    main()
