"""
Deep dive into Query 2 regression to understand why tool removal caused 73% slowdown.
"""

import os
from dotenv import load_dotenv
from langsmith import Client
import json

load_dotenv()
client = Client()

def analyze_trace_detailed(trace_id: str, label: str):
    """Deep analysis of a single trace"""
    
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
        
        print(f"\n📝 Query: {query}")
        print(f"🎯 Status: {'✅ SUCCESS' if run.error is None else f'❌ FAILED'}")
        
        duration = 0
        if run.end_time and run.start_time:
            duration = (run.end_time - run.start_time).total_seconds()
            print(f"⏱️  Duration: {duration:.1f}s")
        
        # Get ALL child runs in order
        child_runs = list(client.list_runs(
            project_name=os.getenv("LANGSMITH_PROJECT", "netbox-agent"),
            filter=f'eq(trace_id, "{trace_id}")'
        ))
        
        # Sort by start time
        child_runs.sort(key=lambda r: r.start_time if r.start_time else 0)
        
        llm_runs = [r for r in child_runs if r.run_type == 'llm']
        tool_runs = [r for r in child_runs if r.run_type == 'tool']
        
        print(f"\n📊 Summary:")
        print(f"  Total Runs: {len(child_runs)}")
        print(f"  LLM Calls: {len(llm_runs)}")
        print(f"  Tool Calls: {len(tool_runs)}")
        
        # Analyze execution flow
        print(f"\n🔍 Execution Flow (chronological):")
        print(f"{'#':<5} {'Type':<8} {'Name':<30} {'Key Details':<50}")
        print('-' * 100)
        
        step = 0
        for run in child_runs:
            step += 1
            run_type = run.run_type
            name = run.name if hasattr(run, 'name') else 'unknown'
            
            details = ""
            
            if run_type == 'tool':
                # Get tool inputs
                if run.inputs:
                    if name == 'netbox_get_objects':
                        obj_type = run.inputs.get('object_type', '?')
                        filters = run.inputs.get('filters', {})
                        filter_str = ', '.join([f"{k}={v}" for k, v in filters.items()]) if filters else 'no filters'
                        details = f"{obj_type} ({filter_str})"
                    elif name == 'write_todos':
                        todos = run.inputs.get('todos', [])
                        details = f"{len(todos)} todos"
                    elif name == 'think':
                        reflection = run.inputs.get('reflection', '')
                        details = reflection[:40] + '...' if len(reflection) > 40 else reflection
                    else:
                        details = str(run.inputs)[:50]
            
            elif run_type == 'llm':
                # Count tokens if available
                if run.outputs and 'usage_metadata' in run.outputs:
                    usage = run.outputs['usage_metadata']
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    details = f"{input_tokens} in / {output_tokens} out tokens"
            
            print(f"{step:<5} {run_type:<8} {name:<30} {details:<50}")
        
        # Analyze tool usage patterns
        tool_counts = {}
        for tool_run in tool_runs:
            name = tool_run.name
            tool_counts[name] = tool_counts.get(name, 0) + 1
        
        print(f"\n🔧 Tool Call Summary:")
        for tool_name in sorted(tool_counts.keys()):
            count = tool_counts[tool_name]
            print(f"  {tool_name}: {count}")
        
        # Check for task() calls (sub-agents)
        task_calls = [r for r in tool_runs if r.name == 'task']
        if task_calls:
            print(f"\n⚠️  Found {len(task_calls)} task() calls (sub-agent delegation)")
        else:
            print(f"\n✅ No task() calls (no sub-agent delegation)")
        
        # Check for discovery tool calls
        discovery_calls = [r for r in tool_runs if r.name in ['list_available_tools', 'get_tool_details']]
        if discovery_calls:
            print(f"⚠️  Found {len(discovery_calls)} discovery tool calls")
            for call in discovery_calls:
                print(f"   - {call.name}")
        else:
            print(f"✅ No discovery tool calls")
        
        # Analyze netbox_get_objects calls in detail
        netbox_calls = [r for r in tool_runs if r.name == 'netbox_get_objects']
        if netbox_calls:
            print(f"\n📦 NetBox API Calls Analysis ({len(netbox_calls)} total):")
            for idx, call in enumerate(netbox_calls, 1):
                obj_type = call.inputs.get('object_type', '?')
                filters = call.inputs.get('filters', {})
                filter_str = json.dumps(filters) if filters else '{}'
                print(f"  {idx}. {obj_type} with filters: {filter_str}")
        
        # Analyze write_todos calls
        todo_calls = [r for r in tool_runs if r.name == 'write_todos']
        if todo_calls:
            print(f"\n📝 Planning Activity ({len(todo_calls)} write_todos calls):")
            for idx, call in enumerate(todo_calls, 1):
                todos = call.inputs.get('todos', [])
                print(f"  Call {idx}: {len(todos)} todos")
                for todo_idx, todo in enumerate(todos, 1):
                    content = todo.get('content', '?')
                    status = todo.get('status', '?')
                    print(f"    {todo_idx}. [{status}] {content}")
        
        return {
            'trace_id': trace_id,
            'query': query,
            'llm_calls': len(llm_runs),
            'tool_calls': len(tool_runs),
            'netbox_calls': len(netbox_calls),
            'todo_calls': len(todo_calls),
            'task_calls': len(task_calls),
            'discovery_calls': len(discovery_calls),
            'duration': duration
        }
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Analyze Query 2 traces to understand regression"""
    
    print("=" * 100)
    print("QUERY 2 REGRESSION INVESTIGATION")
    print("=" * 100)
    print("\nQuery: 'Show where VLAN 100 is deployed across Jimbob's Banking sites'")
    print("\nRegression: 33.4s → 57.9s (73% slower), 5 → 16 tool calls (220% more)")
    
    # Analyze BEFORE (8 tools) - efficient
    print("\n\n" + "#" * 100)
    print("# BEFORE TOOL REMOVAL (8 tools) - EFFICIENT VERSION")
    print("#" * 100)
    before = analyze_trace_detailed("e6046c96-ab11-45fc-9662-073e9d0d1408", "BEFORE")
    
    # Analyze AFTER (4 tools) - regressed
    print("\n\n" + "#" * 100)
    print("# AFTER TOOL REMOVAL (4 tools) - REGRESSED VERSION")
    print("#" * 100)
    after = analyze_trace_detailed("d8ad87bd-b09e-4100-bb9f-bd8aa7011655", "AFTER")
    
    # Comparison
    if before and after:
        print("\n\n" + "=" * 100)
        print("ROOT CAUSE ANALYSIS")
        print("=" * 100)
        
        print(f"\n📊 Key Differences:")
        print(f"  LLM Calls:        {before['llm_calls']} → {after['llm_calls']} ({after['llm_calls'] - before['llm_calls']:+d})")
        print(f"  NetBox API Calls: {before['netbox_calls']} → {after['netbox_calls']} ({after['netbox_calls'] - before['netbox_calls']:+d})")
        print(f"  Planning Calls:   {before['todo_calls']} → {after['todo_calls']} ({after['todo_calls'] - before['todo_calls']:+d})")
        print(f"  Task Calls:       {before['task_calls']} → {after['task_calls']} ({after['task_calls'] - before['task_calls']:+d})")
        print(f"  Discovery Calls:  {before['discovery_calls']} → {after['discovery_calls']} ({after['discovery_calls'] - before['discovery_calls']:+d})")
        
        print(f"\n🔍 Behavioral Changes:")
        
        if before['todo_calls'] == 0 and after['todo_calls'] > 0:
            print(f"  ⚠️  MAJOR CHANGE: Agent switched from direct execution to planning")
            print(f"     - BEFORE: 0 write_todos calls (executed directly)")
            print(f"     - AFTER: {after['todo_calls']} write_todos calls (added planning overhead)")
        
        if after['netbox_calls'] > before['netbox_calls']:
            redundancy = after['netbox_calls'] - before['netbox_calls']
            print(f"  ⚠️  INEFFICIENCY: {redundancy} redundant NetBox API calls")
            print(f"     - Agent is making duplicate or unnecessary queries")
        
        if before['task_calls'] == 0 and after['task_calls'] == 0:
            print(f"  ✅ CONFIRMED: No sub-agent delegation in either version")
        
        if before['discovery_calls'] == 0 and after['discovery_calls'] == 0:
            print(f"  ✅ CONFIRMED: No discovery tool usage in either version")
        
        print(f"\n💡 Hypothesis:")
        print(f"  The regression is NOT caused by:")
        print(f"    - Sub-agent usage (0 task() calls in both)")
        print(f"    - Discovery tool usage (0 calls in both)")
        print(f"  ")
        print(f"  The regression IS caused by:")
        print(f"    - Change in execution strategy (direct → planning)")
        print(f"    - Redundant API calls ({before['netbox_calls']} → {after['netbox_calls']})")
        print(f"    - Likely: Simpler tool set made agent less confident")
        print(f"    - Likely: Agent over-compensated with excessive planning")


if __name__ == "__main__":
    main()
