# Manual Test Scripts

Manual testing scripts for development and verification.

## Purpose

These scripts provide manual testing capabilities that complement the automated test suite. Use them for:
- Interactive testing during development
- Verification of fixes
- Performance testing
- Connection and integration testing

## Available Scripts

### [test_clean_output.py](test_clean_output.py)
Test that streaming output filtering is working correctly.

**Usage:**
```bash
python tests/manual/test_clean_output.py
```

**What it tests:**
- Creates NetBox agent
- Runs simple query ("list 3 sites")
- Counts chunks yielded
- Verifies single clean chunk

**Expected output:**
```
✅ SUCCESS: Only one clean chunk yielded!
```

**When to use:**
- After modifying streaming logic
- Verifying streaming fix (2026-05-04)
- Testing message filtering

### [test_connection.py](test_connection.py)
Test basic connectivity to services.

**Usage:**
```bash
python tests/manual/test_connection.py
```

**What it tests:**
- NetBox API connectivity
- LLM backend connectivity
- Environment configuration

**When to use:**
- Initial setup verification
- Troubleshooting connection issues
- Before running full queries

### [test_mcp_connection.py](test_mcp_connection.py)
Test NetBox MCP server connectivity and basic operations.

**Usage:**
```bash
python tests/manual/test_mcp_connection.py
```

**What it tests:**
- MCP server initialization
- Tool discovery
- Basic tool invocation

**When to use:**
- Testing MCP integration
- Debugging tool wrapper issues
- Verifying MCP server configuration

### [test_query.py](test_query.py)
Test basic query execution end-to-end.

**Usage:**
```bash
python tests/manual/test_query.py
```

**What it tests:**
- Full agent initialization
- Query execution
- Response generation

**When to use:**
- Verification after changes
- Integration testing
- Performance testing

### [test_tool_direct.py](test_tool_direct.py)
Test MCP tools directly without agent wrapper.

**Usage:**
```bash
python tests/manual/test_tool_direct.py
```

**What it tests:**
- Direct tool invocation
- MCP client communication
- Raw tool responses

**When to use:**
- Debugging tool issues
- Testing MCP server directly
- Isolating tool problems from agent logic

### [test_tool_wrapper.py](test_tool_wrapper.py)
Test tool wrapper validation and error handling.

**Usage:**
```bash
python tests/manual/test_tool_wrapper.py
```

**What it tests:**
- Tool wrapper functionality
- Filter validation
- Error recovery middleware

**When to use:**
- Testing filter error handling
- Verifying wrapper fixes (2026-02-09)
- Debugging validation logic

## Running Tests

### Quick Verification

Run all tests in sequence:
```bash
cd /home/ola/dev/netboxdev/ollamaDeepAgents

# Connection tests (fast)
python tests/manual/test_connection.py
python tests/manual/test_mcp_connection.py

# Tool tests (medium)
python tests/manual/test_tool_direct.py
python tests/manual/test_tool_wrapper.py

# Full tests (slow)
python tests/manual/test_query.py
python tests/manual/test_clean_output.py
```

### Testing After Changes

**After modifying streaming logic:**
```bash
python tests/manual/test_clean_output.py
```

**After modifying tools:**
```bash
python tests/manual/test_tool_wrapper.py
python tests/manual/test_tool_direct.py
```

**After configuration changes:**
```bash
python tests/manual/test_connection.py
python tests/manual/test_query.py
```

## Requirements

All tests require:
- NetBox instance running and accessible
- Valid NetBox API token in `.env`
- LLM backend (llama.cpp or Ollama) running
- Project dependencies installed

### Environment Variables

Ensure `.env` is configured with:
```env
NETBOX_URL=http://localhost:8000
NETBOX_TOKEN=<your-token>
LLM_BACKEND=llamacpp
LLAMACPP_BASE_URL=http://localhost:58123/v1
LLAMACPP_MODEL=Qwen_Qwen3-14B-Q5_K_M.gguf
```

## Expected Results

### Success Indicators

- ✅ No exceptions raised
- ✅ Connections established
- ✅ Tools execute without errors
- ✅ Responses are well-formatted
- ✅ Single chunk for streaming tests

### Common Failures

**Connection refused:**
- Check NetBox is running
- Check LLM backend is running
- Verify URLs in `.env`

**Authentication errors:**
- Verify `NETBOX_TOKEN` is correct
- Check token permissions

**Filter errors:**
- Expected for some tests (validates error handling)
- Should be caught by middleware

## Automated vs Manual Tests

### Automated Tests (`tests/test_*.py`)
- Unit tests with mocks
- Fast execution
- CI/CD integration
- No external dependencies

### Manual Tests (`tests/manual/test_*.py`)
- Integration tests with real services
- Slower execution
- Requires running services
- End-to-end verification

**Use both:** Automated tests for development speed, manual tests for verification.

## Adding New Manual Tests

When adding manual test scripts:

1. **Name clearly:** `test_<feature>.py`
2. **Document purpose:** Clear docstring
3. **Add to README:** Update this file
4. **Handle errors gracefully:** Catch and explain failures
5. **Print clear output:** What passed, what failed, why

**Template:**
```python
#!/usr/bin/env python3
"""
Test <feature> functionality.

Usage:
    python tests/manual/test_<feature>.py

Requirements:
    - <requirement 1>
    - <requirement 2>
"""

async def test_feature():
    """Test <feature>."""
    print("Testing <feature>...")

    # Test logic here

    print("✅ Test passed")

if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(test_feature())
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
```

## Related Documentation

- [Automated Tests](../) - pytest test suite
- [Development Notes](../../docs/development/) - Implementation details
- [Scripts](../../scripts/) - Utility scripts

---

**Directory:** `tests/manual/`
**Purpose:** Manual integration testing
**Last Updated:** 2026-05-05
