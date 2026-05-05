#!/usr/bin/env python3
"""Fetch detailed run information from LangSmith including inputs/outputs."""

import os
import json
import sys

# Get API key from environment
api_key = os.getenv("LANGCHAIN_API_KEY")
if not api_key:
    print("Error: LANGCHAIN_API_KEY not set", file=sys.stderr)
    sys.exit(1)

print(f"API Key loaded: {api_key[:20]}...", file=sys.stderr)

try:
    from langsmith import Client

    client = Client(api_key=api_key)

    # Get run details
    run_id = sys.argv[1] if len(sys.argv) > 1 else "019df45c-c9c4-7771-81cd-516847850ed7"

    print(f"Fetching run: {run_id}", file=sys.stderr)

    run = client.read_run(run_id)

    # Extract relevant information
    result = {
        "run_id": str(run.id),
        "name": run.name,
        "run_type": run.run_type,
        "start_time": run.start_time.isoformat() if run.start_time else None,
        "end_time": run.end_time.isoformat() if run.end_time else None,
        "inputs": run.inputs,
        "outputs": run.outputs,
        "error": run.error,
    }

    # Pretty print
    print(json.dumps(result, indent=2))

except ImportError:
    print("Error: langsmith package not installed", file=sys.stderr)
    print("Install with: pip install langsmith", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Error fetching run: {e}", file=sys.stderr)
    sys.exit(1)
