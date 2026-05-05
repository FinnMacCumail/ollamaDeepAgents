# LangSmith Tracing for DeepAgents

This guide shows you how to add LangSmith tracing to your ollamaDeepAgents application for observability, debugging, and performance monitoring.

## What is LangSmith?

**LangSmith** is LangChain's official observability platform that provides:
- 📊 **Trace visualization** - See every step of your agent's execution
- 🔍 **Debugging tools** - Identify where things go wrong
- ⏱️ **Performance metrics** - Track response times, token usage, costs
- 🧪 **Testing & evaluation** - Compare different models and configurations
- 📈 **Analytics** - Understand usage patterns and optimize workflows

## Why Add Tracing?

Based on the `/home/ola/dev/rnd/langOllama` project's analysis, LangSmith helps you:

1. **Debug messy output** - Trace exactly which messages are being generated
2. **Optimize tool calls** - See which NetBox MCP tools are called and in what order
3. **Track performance** - Measure response times for queries
4. **Identify patterns** - Understand which queries work well and which don't
5. **Compare backends** - Benchmark Ollama vs llama.cpp performance

## Setup Instructions

### 1. Get a LangSmith API Key

1. Go to [https://smith.langchain.com/](https://smith.langchain.com/)
2. Sign up or log in
3. Navigate to **Settings** → **API Keys**
4. Create a new API key
5. Copy the key (starts with `lsv2_pt_...`)

### 2. Update Your .env File

Add these three lines to your `.env` file:

```bash
# LangSmith Tracing (optional, for debugging and observability)
LANGCHAIN_API_KEY=lsv2_pt_YOUR_API_KEY_HERE
LANGCHAIN_PROJECT=netbox-deepagents-ollama
LANGCHAIN_TRACING_V2=true
```

**That's it!** No code changes needed. LangChain/DeepAgents automatically detects these environment variables.

### 3. Verify Tracing is Working

Run your agent:

```bash
python -m src.main
```

Make a query:
```
list all sites
```

Then check the LangSmith dashboard:
1. Go to [https://smith.langchain.com/](https://smith.langchain.com/)
2. Navigate to your project: **netbox-deepagents-ollama**
3. You should see a trace with all the steps

## What Gets Traced?

With LangSmith enabled, every query traces:

### 1. User Input
- Original query text
- Timestamp

### 2. Agent Reasoning
- System prompt
- Agent's internal thinking
- Planning steps

### 3. Tool Calls
- Which NetBox MCP tools were called
- Tool input parameters
- Tool responses (including raw JSON)

### 4. LLM Calls
- Model used (Ollama or llama.cpp)
- Input tokens
- Output tokens
- Response time
- Full prompt and completion

### 5. Final Response
- Complete agent response
- Total execution time

## Example Trace Structure

```
Query: "list all sites"
│
├─ Agent Planning
│  ├─ LLM Call (reasoning)
│  └─ Decision: Use netbox_get_objects
│
├─ Tool: netbox_get_objects
│  ├─ Input: {"object_type": "dcim.sites", "filters": {}, "limit": 5}
│  ├─ MCP Server Call
│  └─ Output: [raw JSON with 24 sites]
│
├─ Agent Formatting
│  ├─ LLM Call (formatting)
│  └─ Decision: Create table
│
└─ Final Response: "Here are the first 5 sites..."
```

## Analyzing Traces

### View Individual Traces

Click on any trace to see:
- **Timeline** - Visual execution flow
- **Inputs/Outputs** - Every step's data
- **Metadata** - Tokens, costs, latencies
- **Errors** - If something failed

### Compare Runs

Compare different configurations:
- Ollama vs llama.cpp
- Different models (14B vs 32B)
- With/without middleware
- Different system prompts

### Export Traces

Export traces for offline analysis:

```python
# The langOllama project has scripts for this
# See: /home/ola/dev/rnd/langOllama/fetch_claude_sdk_traces.py
```

## Privacy & Data Handling

**Important considerations:**

### What Gets Sent to LangSmith
- ✅ Query text
- ✅ Tool calls and responses
- ✅ LLM prompts and completions
- ✅ Metadata (timestamps, tokens, etc.)

### What NOT to Send
- ❌ NetBox API tokens (automatically redacted by MCP server)
- ❌ Sensitive infrastructure data (consider this before enabling)

### Disable for Sensitive Queries

Temporarily disable tracing:
```bash
# In .env, comment out or set to false
LANGCHAIN_TRACING_V2=false
```

Or disable programmatically for specific queries:
```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "false"
# Run sensitive query
os.environ["LANGCHAIN_TRACING_V2"] = "true"
```

## Advanced Configuration

### Custom Project Names

Use different projects for different environments:

```bash
# Development
LANGCHAIN_PROJECT=netbox-deepagents-dev

# Production
LANGCHAIN_PROJECT=netbox-deepagents-prod

# Testing llama.cpp
LANGCHAIN_PROJECT=netbox-deepagents-llamacpp

# Testing Ollama
LANGCHAIN_PROJECT=netbox-deepagents-ollama
```

### Add Custom Metadata

Tag traces with custom metadata:

```python
from langsmith import traceable

@traceable(
    run_type="chain",
    metadata={"backend": "llamacpp", "model": "qwen3-14b"}
)
async def query_with_metadata(agent, query):
    return await agent.query_sync(query)
```

### Filter Sensitive Data

Create a callback to filter sensitive data:

```python
from langchain.callbacks import LangChainTracer

class FilteredTracer(LangChainTracer):
    def _persist_run(self, run):
        # Remove sensitive fields
        if "netbox_token" in str(run.inputs):
            run.inputs = {"query": "[REDACTED]"}
        super()._persist_run(run)
```

## Analysis Tools (from langOllama)

The `/home/ola/dev/rnd/langOllama` project has analysis scripts you can adapt:

### 1. Fetch Traces
```python
# Based on: /home/ola/dev/rnd/langOllama/fetch_claude_sdk_traces.py
# Fetches traces from LangSmith API to local JSON files
```

### 2. Analyze Traces
```python
# Based on: /home/ola/dev/rnd/langOllama/analyze_traces.py
# Generates comprehensive analysis reports:
# - Tool usage patterns
# - Query completion rates
# - Performance metrics
# - Common failure patterns
```

### 3. Compare Frameworks
```python
# Based on: /home/ola/dev/rnd/langOllama/compare_traces.py
# Compare different implementations:
# - Ollama vs llama.cpp
# - DeepAgents vs custom agents
# - Different models
```

## Troubleshooting

### Traces Not Appearing

**Check environment variables:**
```bash
python -c "import os; print(os.getenv('LANGCHAIN_TRACING_V2'))"
# Should output: true
```

**Verify API key:**
```bash
python -c "import os; print(os.getenv('LANGCHAIN_API_KEY')[:20])"
# Should output: lsv2_pt_...
```

**Check network:**
```bash
curl -H "x-api-key: YOUR_API_KEY" https://api.smith.langchain.com/info
```

### Slow Performance

LangSmith adds minimal overhead (~10-50ms per trace), but if you notice slowness:

1. **Use async mode** (already enabled in DeepAgents)
2. **Batch uploads** (LangSmith does this automatically)
3. **Disable for production** if needed

### Too Much Data

If traces are too large:

1. **Filter tool responses** - Only trace summaries, not full JSON
2. **Sample traces** - Only trace 10% of queries
3. **Use separate projects** - Dev vs Prod

## Comparing to Your Messy Output Issue

Remember your messy output from `ANALYSIS_messy_output.md`? LangSmith helps you:

### See Exactly What's Being Streamed

Trace shows each chunk:
- ✅ User message echo
- ✅ Tool call structure
- ✅ Raw JSON from NetBox
- ✅ Intermediate processing
- ✅ Final formatted response

### Identify the Problem

Visual trace makes it obvious:
- 7 separate message chunks for one query
- Tool messages being yielded to user
- `stream_mode="values"` yielding everything

### Test Fixes

Compare traces before/after fixing:
- Original: 7 chunks with raw JSON
- Fixed: Single clean response

## Next Steps

1. **Enable LangSmith** - Add the 3 env vars
2. **Run some queries** - Generate traces
3. **Explore the dashboard** - Understand your agent's behavior
4. **Analyze patterns** - Find optimization opportunities
5. **Compare backends** - Benchmark Ollama vs llama.cpp
6. **Adapt analysis scripts** - Use langOllama's tools for your traces

## Resources

- [LangSmith Documentation](https://docs.smith.langchain.com/)
- [LangSmith Pricing](https://www.langchain.com/pricing) - Free tier: 5,000 traces/month
- [LangChain Tracing Guide](https://python.langchain.com/docs/langsmith/walkthrough)
- [Example Analysis Scripts](file:///home/ola/dev/rnd/langOllama)

---

**Pro Tip:** The langOllama project at `/home/ola/dev/rnd/langOllama` has excellent trace analysis examples. Check out:
- `analyze_traces.py` - Comprehensive trace analysis
- `trace_analysis_report.md` - Example report output
- `compare_traces.py` - Framework comparison tool
