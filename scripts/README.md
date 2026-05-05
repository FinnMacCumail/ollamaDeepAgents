# Utility Scripts

Helper scripts for development, debugging, and analysis.

## Available Scripts

### [fetch_run_details.py](fetch_run_details.py)
Fetch detailed LangSmith run information including inputs/outputs.

**Usage:**
```bash
LANGCHAIN_API_KEY=<your-key> python scripts/fetch_run_details.py <run-id>
```

**Purpose:**
- Retrieve full LLM call details from LangSmith
- View inputs, outputs, and metadata
- Useful for trace analysis

**Example:**
```bash
# Get API key from .env
LANGCHAIN_API_KEY=$(grep LANGCHAIN_API_KEY .env | cut -d'=' -f2)

# Fetch run details
python scripts/fetch_run_details.py 019df48b-2844-7e03-817e-7fce1967270c
```

**Output:**
- JSON with inputs, outputs, token usage
- Formatted for readability

### [verify_langsmith.py](verify_langsmith.py)
Verify LangSmith configuration and connectivity.

**Usage:**
```bash
python scripts/verify_langsmith.py
```

**Purpose:**
- Check environment variables
- Test API connectivity
- Verify LangSmith client initialization
- Create test trace

**Checks:**
- ✅ LANGCHAIN_API_KEY set
- ✅ LANGCHAIN_PROJECT configured
- ✅ API reachable
- ✅ Can create traces

**Example Output:**
```
✅ Environment variables configured
✅ LangSmith API reachable
✅ Client initialized successfully
✅ Test trace created: <trace-id>
```

### [debug_streaming.py](debug_streaming.py)
Debug streaming output from the agent.

**Usage:**
```bash
python scripts/debug_streaming.py
```

**Purpose:**
- Test streaming message flow
- Inspect message types
- Debug filter logic
- Verify clean output

**What it does:**
- Creates agent instance
- Runs test query
- Shows each chunk with metadata
- Counts message types

## Using Scripts

### Development Workflow

**1. Verify Setup:**
```bash
python scripts/verify_langsmith.py
```

**2. Run Query:**
```bash
python -m src.main
```

**3. Analyze Trace:**
```bash
# List recent traces
LANGSMITH_API_KEY=$(grep LANGCHAIN_API_KEY .env | cut -d'=' -f2) \
  /home/ola/.local/bin/langsmith trace list \
  --project netbox-deepagents-llamacpp --limit 5

# Get details for specific run
python scripts/fetch_run_details.py <run-id>
```

**4. Debug Streaming:**
```bash
python scripts/debug_streaming.py
```

### Common Tasks

**Check LangSmith Connection:**
```bash
python scripts/verify_langsmith.py
```

**Analyze Latest Trace:**
```bash
# Get latest trace ID from LangSmith
# Then fetch details
python scripts/fetch_run_details.py <trace-id>
```

**Test Output Filtering:**
```bash
python scripts/debug_streaming.py
```

## Requirements

All scripts require:
- Python 3.11+
- Project dependencies installed (`pip install -e .`)
- Appropriate environment variables set

### Specific Requirements

**fetch_run_details.py:**
- `LANGCHAIN_API_KEY` environment variable
- LangSmith account

**verify_langsmith.py:**
- `LANGCHAIN_API_KEY` environment variable
- `LANGCHAIN_PROJECT` environment variable
- LangSmith account

**debug_streaming.py:**
- NetBox instance running
- LLM backend (llama.cpp or Ollama) running

## Adding New Scripts

When adding utility scripts:

1. **Place in this directory**
2. **Add to this README:**
   - Brief description
   - Usage example
   - Purpose and use cases
   - Requirements

3. **Include docstring:**
```python
#!/usr/bin/env python3
"""
Brief description of what this script does.

Usage:
    python scripts/your_script.py [args]

Requirements:
    - List requirements here
"""
```

4. **Make executable (optional):**
```bash
chmod +x scripts/your_script.py
```

## Related Documentation

- [LangSmith Setup](../docs/setup/langsmith.md) - Configure tracing
- [Trace Analysis](../docs/traces/) - Analysis reports
- [Development Notes](../docs/development/) - Implementation details

## Troubleshooting

### "ModuleNotFoundError"
Install project dependencies:
```bash
pip install -e .
```

### "LANGCHAIN_API_KEY not set"
Set environment variable or source .env:
```bash
export LANGCHAIN_API_KEY=<your-key>
# or
source .env  # May not work in all shells
```

### "Connection refused"
Ensure your backend (llama.cpp or Ollama) is running.

---

**Directory:** `scripts/`
**Purpose:** Development utilities
**Last Updated:** 2026-05-05
