# Analysis: Why ollamaDeepAgents Produces Messy Output

## Root Cause

The messy output is caused by **incorrect stream mode usage** in the agent's query method.

### The Problem

**File:** `src/agents/netbox_agent.py:171-177`

```python
async for chunk in self.agent.astream(
    {"messages": [{"role": "user", "content": user_query}]},
    stream_mode="values"  # <-- THIS IS THE PROBLEM
):
    if "messages" in chunk and chunk["messages"]:
        last_msg = chunk["messages"][-1]
        if hasattr(last_msg, "content"):
            yield last_msg.content  # <-- YIELDS ALL MESSAGE TYPES
```

### What's Happening

With `stream_mode="values"`, LangGraph/DeepAgents returns the **ENTIRE state** after **EVERY step** of execution:

1. **Step 1:** User message added
   - `last_msg.content` = `"list all sites"`
   - ✅ **Yielded** → Shows in output

2. **Step 2:** Agent plans/thinks (may repeat user query)
   - `last_msg.content` = `"list all sites"` or thinking text
   - ✅ **Yielded** → Causes duplication

3. **Step 3:** Agent makes tool call
   - `last_msg` is a `ToolCall` message
   - `last_msg.content` = Tool call parameters
   - ✅ **Yielded** → Shows `[[{"type": "text", "text": "...`

4. **Step 4:** Tool execution completes
   - `last_msg` is a `ToolMessage`
   - `last_msg.content` = **RAW JSON from NetBox API** (huge!)
   - ✅ **Yielded** → This is the giant JSON dump!

5. **Step 5:** Agent processes tool result
   - `last_msg.content` = Intermediate processing
   - ✅ **Yielded** → More noise

6. **Step 6:** Agent generates final response
   - `last_msg.content` = **Formatted human-readable response**
   - ✅ **Yielded** → The actual desired output

7. **Step 7:** Possible post-processing
   - Additional steps may yield more content
   - ✅ **Yielded** → More duplication

### Why llama.cpp Works Better

The llama.cpp implementation:
- Uses **direct model inference**
- **Single response** generation
- **Clean system prompt** that produces structured output
- **No middleware** adding/duplicating content
- **Simple streaming** of just the model's response

### Observed Output Breakdown

Looking at your actual output:

```
list all siteslist all siteslist all sites
```
↳ User message echoed 3 times (steps 1, 2, and possibly another repeat)

```
[[{"type": "text", "text": "{"count":24...
```
↳ Tool call structure (step 3)

```
{"count":24,"next":"http://localhost:8000/api/dcim/sites/?limit=5&offset=5"...
```
↳ Raw JSON tool response (step 4) - **THE MESSY PART**

```
{"structured_content": {"count": 24, "next": ...
```
↳ Same JSON wrapped differently (step 5)

```
The JSON data provided contains a list of network sites...
```
↳ Finally, the actual formatted response (step 6)

Then it **repeats** the formatted response again (likely step 7 or middleware duplication)

## LangGraph Stream Modes

### Available Modes:

1. **`"values"`** (Currently used - WRONG)
   - Returns full state after each step
   - Includes ALL messages (user, assistant, tool, system)
   - **Problem:** Yields everything including internal processing

2. **`"updates"`** (Better option)
   - Returns only state changes/diffs
   - Would reduce duplication but still includes tool messages

3. **`"messages"`** (Doesn't exist in LangGraph)
   - This is what you'd want but it's not a valid option

### The Correct Approach

The code should **filter message types** before yielding:

```python
async for chunk in self.agent.astream(..., stream_mode="values"):
    if "messages" in chunk and chunk["messages"]:
        last_msg = chunk["messages"][-1]

        # FILTER: Only yield AIMessage (final responses)
        # Skip: ToolMessage, ToolCall, HumanMessage echoes
        if hasattr(last_msg, "type") and last_msg.type == "ai":
            if hasattr(last_msg, "content") and last_msg.content:
                # Also filter out tool calls
                if not hasattr(last_msg, "tool_calls") or not last_msg.tool_calls:
                    yield last_msg.content
```

OR use a different approach entirely:

```python
# Option 1: Wait for final state
final_state = await self.agent.ainvoke(...)
final_message = final_state["messages"][-1]
yield final_message.content

# Option 2: Stream only specific events
async for event in self.agent.astream_events(..., version="v2"):
    if event["event"] == "on_chat_model_stream":
        chunk = event["data"]["chunk"]
        if hasattr(chunk, "content"):
            yield chunk.content
```

## Why Middleware Isn't Helping

The middleware in the stack:
- `FilterErrorRecoveryMiddleware` - Only triggers on errors
- `MetricsMiddleware` - Just logs, doesn't filter output
- `QueryMetricsMiddleware` - Just tracking
- `TokenOptimizationMiddleware` - Truncates but doesn't filter message types

**None of them prevent tool messages from being streamed to the user.**

## Additional Issues

### 1. DeepAgents Complexity
- Multiple middleware layers
- Complex state management
- Streaming is not well-documented for this use case
- Designed for more complex agentic workflows, overkill for simple queries

### 2. Token Optimization Backfire
The `TokenOptimizationMiddleware(max_tokens_per_message=1000)` might be:
- Truncating tool responses mid-JSON
- Not actually reducing what gets displayed to user
- Only affecting internal message history

### 3. Model Size Mismatch
- Using 32B model (slower) when 14B produces better formatted output
- Suggests the prompt engineering in llama.cpp is superior
- DeepAgents default prompts may not be optimized for this use case

## Performance Impact

### ollamaDeepAgents:
- **Response time:** 50+ seconds
- **Token usage:** Very high (all the raw JSON is processed)
- **Output quality:** Poor (messy, duplicated)
- **User experience:** Confusing

### llama.cpp:
- **Response time:** Likely faster (smaller model, simpler flow)
- **Token usage:** Optimized (only model output)
- **Output quality:** Excellent (clean, formatted)
- **User experience:** Great

## Recommendations (If Changes Were Allowed)

1. **Quick Fix:** Filter message types before yielding
2. **Better Fix:** Use `ainvoke` instead of `astream` for simpler queries
3. **Best Fix:** Implement custom streaming that only yields final responses
4. **Alternative:** Switch to direct Ollama API calls like llama.cpp does

## Conclusion

The messy output is **architectural**, not a bug:
- DeepAgents is designed for complex multi-step reasoning
- The streaming implementation exposes all internal steps
- For simple "query → tool call → format response" flows, this is overkill
- llama.cpp's direct approach is more appropriate for this use case

**The framework is working as designed - it's just not the right design for this use case.**
