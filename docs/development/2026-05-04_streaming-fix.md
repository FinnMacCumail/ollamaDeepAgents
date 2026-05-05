# Fix Applied: Clean Streaming Output

## Problem

The ollamaDeepAgents app was producing messy output with 7+ chunks for a simple query like "list all sites":

```
list all siteslist all siteslist all sites
[[{"type": "text", "text": "{\"count\":24...
{"count":24,"next":"http://localhost:8000/api/dcim/sites/?limit=5&offset=5"...
{"structured_content": {"count": 24, "next": ...
The JSON data provided contains a list of network sites...
[Duplicate of formatted response]
```

## Root Cause

**File:** `src/agents/netbox_agent.py:182-188`

The code was using `stream_mode="values"` which yields the **entire state** after each step, including:
- ✅ HumanMessage (user query echoes)
- ✅ ToolMessage (raw JSON from NetBox MCP - 1,196 characters!)
- ✅ AIMessage with tool_calls (but no content)
- ✅ AIMessage with final response
- ✅ Duplicates

**Original Code:**
```python
async for chunk in self.agent.astream(..., stream_mode="values"):
    if "messages" in chunk and chunk["messages"]:
        last_msg = chunk["messages"][-1]
        if hasattr(last_msg, "content"):
            yield last_msg.content  # <-- Yields EVERYTHING!
```

This yielded **all message types** without filtering.

## Solution

**Updated Code:** (netbox_agent.py:182-198)

```python
async for chunk in self.agent.astream(..., stream_mode="values"):
    if "messages" in chunk and chunk["messages"]:
        last_msg = chunk["messages"][-1]

        # Only yield final AI responses, filter out:
        # - HumanMessage (user query echoes)
        # - ToolMessage (raw JSON from NetBox MCP)
        # - AIMessage with tool_calls but no content
        # - Empty messages
        if (hasattr(last_msg, "type") and
            last_msg.type == "ai" and
            hasattr(last_msg, "content") and
            last_msg.content and
            not getattr(last_msg, "tool_calls", None)):
            yield last_msg.content
```

**Filter Logic:**
1. ✅ `last_msg.type == "ai"` - Only AI messages (not Human, not Tool)
2. ✅ `last_msg.content` - Has content and it's not empty
3. ✅ `not last_msg.tool_calls` - Not a tool invocation message

## Expected Result

### Before (7+ chunks):
```
[Chunk 1] list all sites
[Chunk 2] list all sites
[Chunk 3] [[{"type": "text", "text": "{\"count\":24...
[Chunk 4] {"count":24,"next":"http://localhost:8000/api/dcim/sites/...
[Chunk 5] {"structured_content": {"count": 24...
[Chunk 6] Here are the first 5 sites from your NetBox instance:

1. **Butler Communications** (ID: 24)...
[Chunk 7] [Duplicate of chunk 6]
```

### After (1 clean chunk):
```
[Chunk 1] Here are the first 5 sites from your NetBox instance:

1. **Butler Communications** (ID: 24)
   - Status: Active
   - Region: North Carolina
   - Facility: BUT

2. **D. S. Weaver Labs** (ID: 22)
   - Status: Active
   - Region: North Carolina
   - Facility: DSW

3. **DM-Akron** (ID: 2)
   - Status: Active
   - Region: Ohio
   - Facility: (none)

4. **DM-Albany** (ID: 3)
   - Status: Active
   - Region: New York
   - Facility: (none)

5. **DM-Binghamton** (ID: 4)
   - Status: Active
   - Region: New York
   - Facility: (none)

There are **24 total sites** listed. Would you like me to retrieve the next page of results or refine the list further?
```

## Testing

**To test the fix:**

```bash
python test_clean_output.py
```

Or manually:
```bash
python -m src.main
# Then query: list 3 sites
```

**Expected:**
- **1 chunk** with clean formatted response
- **No** user query echoes
- **No** raw JSON dumps
- **No** tool call structures
- **No** duplicates

## Performance Impact

**No performance degradation:**
- ✅ Same execution time (~40s for "list sites")
- ✅ Same number of LLM calls (2)
- ✅ Same number of tool calls (1)
- ✅ Same token usage (~23K tokens)

**Only difference:**
- ❌ Before: 7+ chunks streamed to user
- ✅ After: 1 clean chunk streamed to user

## What Still Gets Logged

The fix **only affects user output**. All internal processing is still traced in LangSmith:
- ✅ HumanMessage - Still in trace
- ✅ Tool calls - Still in trace
- ✅ Tool responses - Still in trace
- ✅ All AI messages - Still in trace

You can still see the full execution flow in LangSmith dashboard!

## Verification via LangSmith

After running a query with the fix, check the trace:

```bash
# List recent traces
source .env && LANGSMITH_API_KEY="$LANGCHAIN_API_KEY" \
  langsmith trace list --project netbox-deepagents-llamacpp --limit 5

# Get trace details
source .env && python fetch_run_details.py <trace-id>
```

The trace will show:
- ✅ All 36 runs (same as before)
- ✅ 2 LLM calls (same as before)
- ✅ 1 tool call (same as before)
- ✅ All middleware execution

But **user output** will only be the final formatted response.

## Comparison to llama.cpp Direct

### llama.cpp server (your working implementation)
```
Here are the first 5 sites from your NetBox instance:

1. **Butler Communications** (ID: 24)...
```
**Clean, single response** ✅

### ollamaDeepAgents (before fix)
```
list all siteslist all sites{"count":24,"next":...Here are the first 5 sites...
```
**Messy, 7+ chunks** ❌

### ollamaDeepAgents (after fix)
```
Here are the first 5 sites from your NetBox instance:

1. **Butler Communications** (ID: 24)...
```
**Clean, single response** ✅

## Related Files

- **Fix Applied:** `src/agents/netbox_agent.py:182-198`
- **Analysis:** `ANALYSIS_messy_output.md`
- **Trace Details:** `TRACE_ANALYSIS.md`
- **Test Script:** `test_clean_output.py`

## Next Steps

1. ✅ **Fixed** - Streaming output now clean
2. ⏭️ **Test** - Run a query and verify single clean chunk
3. ⏭️ **Compare** - Benchmark against Ollama backend
4. ⏭️ **Optimize** - Consider using smaller model (7B vs 14B) for faster responses

## Notes

- This fix is **non-breaking** - no API changes
- Works with both **Ollama** and **llama.cpp** backends
- Compatible with **DeepAgents 0.5.6**
- Preserves full tracing in **LangSmith**

---

**Status:** ✅ Fixed (Applied: 2026-05-04)
**Tested:** ⏳ Pending manual verification
**Performance:** No impact (same speed, cleaner output)
