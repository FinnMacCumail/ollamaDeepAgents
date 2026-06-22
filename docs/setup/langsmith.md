# LangSmith Setup Guide

Quick guide to enable LangSmith tracing for your ollamaDeepAgents project.

## Why Enable LangSmith?

LangSmith will help you:
- 🐛 **Debug the messy output issue** - See exactly which messages are being streamed
- 📊 **Compare Ollama vs llama.cpp** - Benchmark performance differences
- 🔍 **Trace tool calls** - See which NetBox MCP tools are used and in what order
- ⏱️ **Monitor performance** - Track response times and token usage
- 🧪 **Test improvements** - Validate fixes to streaming output

## Setup Steps (5 minutes)

### 1. Get Your LangSmith API Key

1. Go to **[https://smith.langchain.com/](https://smith.langchain.com/)**
2. Sign up or log in (free tier: 5,000 traces/month)
3. Navigate to **Settings** → **API Keys**
4. Click **Create API Key**
5. Copy the key (starts with `lsv2_pt_...`)

### 2. Configure Your .env File

Edit `.env` and uncomment these lines (around line 32-37):

```bash
# LangSmith Tracing (optional, for debugging and observability)
# To enable: Get your API key from https://smith.langchain.com/
# Then uncomment the lines below and add your key
LANGCHAIN_API_KEY=lsv2_pt_YOUR_ACTUAL_KEY_HERE  # <-- Paste your key
LANGCHAIN_PROJECT=netbox-deepagents-llamacpp
LANGCHAIN_TRACING_V2=true
```

**Important:**
- Replace `lsv2_pt_YOUR_ACTUAL_KEY_HERE` with your real API key
- Remove the `#` at the start of each line
- Keep the project name as `netbox-deepagents-llamacpp` (or change to `netbox-deepagents-ollama` if using Ollama)

### 3. Verify Configuration

Confirm the env vars are loaded and the client can authenticate:

```bash
./venv/bin/python -c "
from dotenv import load_dotenv; load_dotenv()
import os
from langsmith import Client
assert os.getenv('LANGCHAIN_API_KEY'), 'LANGCHAIN_API_KEY not set'
# A successful list call confirms the key authenticates:
list(Client().list_datasets(limit=1))
print('✅ LangSmith client authenticated OK')
"
```

A `401 Unauthorized` here means the key is missing, expired, or revoked — rotate it
at <https://smith.langchain.com/settings>. A clean exit means tracing is wired up.

### 4. Test with Your Agent

Run your agent:

```bash
python -m src.main
```

Make a query:
```
list all sites
```

### 5. View Traces in Dashboard

1. Go to **[https://smith.langchain.com/](https://smith.langchain.com/)**
2. Click on your project: **netbox-deepagents-llamacpp**
3. You should see your traces!

## What You'll See in Traces

Each query creates a trace showing:

### Timeline View
```
Query: "list all sites"
│
├─ Agent Planning (LLM call)
│  ├─ Input: System prompt + user query
│  └─ Output: Decision to use netbox_get_objects
│
├─ Tool: netbox_get_objects
│  ├─ Input: {"object_type": "dcim.sites", "limit": 5}
│  ├─ MCP Server Call
│  └─ Output: Raw JSON (24 sites)
│
├─ Agent Formatting (LLM call)
│  ├─ Input: Format this data for user
│  └─ Output: Formatted table
│
└─ Final Response: "Here are the first 5 sites..."
```

### Metrics
- **Total duration** - Time from query to response
- **Token count** - Input/output tokens per LLM call
- **Tool calls** - Number and type of NetBox MCP tools used
- **Errors** - Any failures or retries

## Analyzing Your Messy Output

Remember the messy output from before? LangSmith will show you:

### Before Fix
```
Trace shows 7 message chunks:
1. User query echo
2. Tool call structure
3. Raw JSON from NetBox (huge!)
4. Intermediate processing
5. Another JSON wrapper
6. Final formatted response
7. Duplicate response
```

### After Fix
```
Trace shows clean output:
1. User query
2. Tool call
3. Final formatted response
```

## Troubleshooting

### Script Says "Not Configured"

Make sure you:
- Uncommented the lines in `.env` (removed the `#`)
- Added your actual API key
- Saved the `.env` file

### No Traces Appearing

Check:
```bash
# Verify environment variables are loaded
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print(f'Tracing: {os.getenv(\"LANGCHAIN_TRACING_V2\")}')"
```

Should output: `Tracing: true`

### API Key Invalid

- Check you copied the full key (starts with `lsv2_pt_`)
- Make sure there are no extra spaces
- Try creating a new API key in the LangSmith dashboard

## Privacy Note

LangSmith will receive:
- ✅ Your queries
- ✅ Tool calls and responses
- ✅ LLM prompts and completions
- ❌ NetBox API token (automatically redacted by MCP server)

To disable tracing for sensitive queries:
```bash
# In .env, set to false
LANGCHAIN_TRACING_V2=false
```

## Next Steps

After enabling LangSmith:

1. **Compare backends** - Run same queries with Ollama vs llama.cpp
   - Change `LLM_BACKEND=ollama` and `LANGCHAIN_PROJECT=netbox-deepagents-ollama`
   - Run queries
   - Compare traces between projects

2. **Analyze patterns** - Check which queries work best
   - Look for queries with many tool calls
   - Find slow responses
   - Identify common failures

3. **Optimize** - Use trace insights to improve
   - Reduce unnecessary tool calls
   - Fix streaming output issues
   - Improve system prompts

4. **Use analysis scripts** - Adapt tools from `/home/ola/dev/rnd/langOllama`
   - `analyze_traces.py` - Generate reports
   - `compare_traces.py` - Compare runs

## Resources

- **Full Guide**: `docs/guides/langsmith-tracing.md`
- **Evaluation harness**: `tests/eval/` (model-matrix testing) — run via `./venv/bin/python -m tests.eval.run_matrix`
- **LangSmith Docs**: https://docs.smith.langchain.com/
- **Dashboard**: https://smith.langchain.com/

---

**Need help?** Re-run the verification snippet in §3 to diagnose connectivity/auth issues.
