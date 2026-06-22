"""
Compare traces before/after tool removal (8 tools → 4 tools).
"""

import os
from dotenv import load_dotenv
from langsmith import Client

load_dotenv()
client = Client()

def analyze_trace(trace_id: str, label: str):
    """Analyze a single trace"""
    print(f"\n{'=' * 100}")
    print(f"{label}: {trace_id}")
    print(f"{'=' * 100}")

    try:
        run = client.read_run(trace_id)
        
        # Get query
        query = "Unknown"
        if run.inputs and 'messages' in run.inputs:
            messages = run.inputs['messages']
            if messages and len(messages) > 0:
                first_msg = messages[0]
                if isinstance(first_msg, dict) and 'content' in first_msg:
                    query = first_msg['content']
        
        print(f"\n📝 Query: {query[:100]}{'...' if len(query) > 100 else ''}")
        print(f"🎯 Status: {'✅ SUCCESS' if run.error is None else f'❌ FAILED: {run.error}'}")
        
        duration = 0
        if run.end_time and run.start_time:
            duration = (run.end_time - run.start_time).total_seconds()
            print(f"⏱️  Duration: {duration:.1f}s")
        
        # Get child runs
        child_runs = list(client.list_runs(
            project_name=os.getenv("LANGSMITH_PROJECT", "netbox-agent"),
            filter=f'eq(trace_id, "{trace_id}")'
        ))
        
        llm_runs = [r for r in child_runs if r.run_type == 'llm']
        tool_runs = [r for r in child_runs if r.run_type == 'tool']
        
        print(f"\n📊 Execution Metrics:")
        print(f"  LLM Calls: {len(llm_runs)}")
        print(f"  Tool Calls: {len(tool_runs)}")
        
        # Count tools by name
        tool_counts = {}
        for tool_run in tool_runs:
            name = tool_run.name
            tool_counts[name] = tool_counts.get(name, 0) + 1
        
        if tool_counts:
            print(f"\n🔧 Tool Breakdown:")
            for tool_name in sorted(tool_counts.keys()):
                count = tool_counts[tool_name]
                print(f"  {tool_name}: {count}")
        
        return {
            'trace_id': trace_id,
            'query': query,
            'success': run.error is None,
            'llm_calls': len(llm_runs),
            'tool_calls': len(tool_runs),
            'tool_counts': tool_counts,
            'duration': duration
        }
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return None


def compare_traces(new_ids, old_ids, query_name):
    """Compare new traces (4 tools) vs old traces (8 tools)"""
    
    print(f"\n\n{'#' * 100}")
    print(f"# {query_name}")
    print(f"{'#' * 100}")
    
    print(f"\n## AFTER TOOL REMOVAL (4 tools)")
    new_results = []
    for trace_id in new_ids:
        result = analyze_trace(trace_id, "NEW")
        if result:
            new_results.append(result)
    
    print(f"\n\n## BEFORE TOOL REMOVAL (8 tools)")
    old_results = []
    for trace_id in old_ids:
        result = analyze_trace(trace_id, "OLD")
        if result:
            old_results.append(result)
    
    # Calculate averages
    if new_results and old_results:
        avg_new_llm = sum(r['llm_calls'] for r in new_results) / len(new_results)
        avg_old_llm = sum(r['llm_calls'] for r in old_results) / len(old_results)
        avg_new_tools = sum(r['tool_calls'] for r in new_results) / len(new_results)
        avg_old_tools = sum(r['tool_calls'] for r in old_results) / len(old_results)
        avg_new_duration = sum(r['duration'] for r in new_results) / len(new_results)
        avg_old_duration = sum(r['duration'] for r in old_results) / len(old_results)
        
        print(f"\n\n{'=' * 100}")
        print(f"COMPARISON: {query_name}")
        print(f"{'=' * 100}")
        
        print(f"\n{'Metric':<30} {'OLD (8 tools)':<20} {'NEW (4 tools)':<20} {'Delta':<20}")
        print('-' * 90)
        
        llm_delta = avg_new_llm - avg_old_llm
        llm_pct = f"({llm_delta / avg_old_llm * 100:+.1f}%)" if avg_old_llm > 0 else ""
        print(f"{'LLM Calls (avg)':<30} {avg_old_llm:<20.1f} {avg_new_llm:<20.1f} {llm_delta:+.1f} {llm_pct}")
        
        tool_delta = avg_new_tools - avg_old_tools
        tool_pct = f"({tool_delta / avg_old_tools * 100:+.1f}%)" if avg_old_tools > 0 else ""
        print(f"{'Tool Calls (avg)':<30} {avg_old_tools:<20.1f} {avg_new_tools:<20.1f} {tool_delta:+.1f} {tool_pct}")
        
        time_delta = avg_new_duration - avg_old_duration
        time_pct = f"({time_delta / avg_old_duration * 100:+.1f}%)" if avg_old_duration > 0 else ""
        print(f"{'Duration (avg)':<30} {f'{avg_old_duration:.1f}s':<20} {f'{avg_new_duration:.1f}s':<20} {f'{time_delta:+.1f}s'} {time_pct}")
        
        return {
            'query': query_name,
            'llm_delta': llm_delta,
            'tool_delta': tool_delta,
            'time_delta': time_delta
        }
    
    return None


def main():
    """Compare all three query sets"""
    
    comparisons = []
    
    # Query 1: Dunder-Mifflin sites (the one user selected)
    comp1 = compare_traces(
        new_ids=["740466c3-ebb5-4864-9954-6fc1fb9085a2"],
        old_ids=["6ab198c9-1308-4e84-b124-0ac8670be95a"],  # AFTER sub-agent removal
        query_name="Query 1: Dunder-Mifflin Sites (4 tools vs 8 tools)"
    )
    if comp1:
        comparisons.append(comp1)
    
    # Query 2: Second trace
    comp2 = compare_traces(
        new_ids=["d8ad87bd-b09e-4100-bb9f-bd8aa7011655"],
        old_ids=["e6046c96-ab11-45fc-9662-073e9d0d1408"],  # AFTER sub-agent removal
        query_name="Query 2: VLAN 100 Deployment (4 tools vs 8 tools)"
    )
    if comp2:
        comparisons.append(comp2)
    
    # Query 3: Third trace
    comp3 = compare_traces(
        new_ids=["74ad927e-a634-4a62-b1a9-2bf74fd76af4"],
        old_ids=["d2e82487-e103-432c-9634-f0b0f4af3b6f"],  # AFTER sub-agent removal
        query_name="Query 3: NC State Racks (4 tools vs 8 tools)"
    )
    if comp3:
        comparisons.append(comp3)
    
    # Overall summary
    if comparisons:
        print(f"\n\n{'#' * 100}")
        print(f"# OVERALL SUMMARY: Tool Removal Impact (8 tools → 4 tools)")
        print(f"{'#' * 100}")
        
        total_llm_delta = sum(c['llm_delta'] for c in comparisons)
        total_tool_delta = sum(c['tool_delta'] for c in comparisons)
        total_time_delta = sum(c['time_delta'] for c in comparisons)
        
        print(f"\nAcross {len(comparisons)} queries:")
        print(f"  LLM Calls:      {total_llm_delta:+.1f} total ({total_llm_delta / len(comparisons):+.1f} avg per query)")
        print(f"  Tool Calls:     {total_tool_delta:+.1f} total ({total_tool_delta / len(comparisons):+.1f} avg per query)")
        print(f"  Duration:       {total_time_delta:+.1f}s total ({total_time_delta / len(comparisons):+.1f}s avg per query)")
        
        if total_llm_delta < 0:
            print(f"\n✅ Tool removal improved efficiency!")
        elif total_llm_delta > 0:
            print(f"\n⚠️  Tool removal slightly increased overhead")
        else:
            print(f"\n➡️  No significant change in efficiency")


if __name__ == "__main__":
    main()
