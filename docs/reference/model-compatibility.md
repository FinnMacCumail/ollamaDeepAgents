# Model Compatibility Guide

## Overview

This document explains which Ollama models work with the DeepAgents framework and why some models (like `gpt-oss:20b`) are incompatible.

## Why gpt-oss:20b Fails with DeepAgents

### The Architecture Issue

DeepAgents is built on LangChain/LangGraph but adds validation layers for:
- Planning and task decomposition
- Structured output validation with Pydantic schemas
- Tool call format validation
- Agent state management

### gpt-oss's Unique "Harmony" Format

The `gpt-oss` models use OpenAI's proprietary "Harmony" response format:

```
<|start|>assistant<|channel|>commentary to=functions.toolname<|message|>
```

**Key characteristics:**
- All messages must specify a channel: `analysis`, `commentary`, or `final`
- Tool calls use format: `toolname<|channel|>commentary`
- Channel markers are embedded in the response

### The Incompatibility

When `gpt-oss:20b` tries to call `netbox_get_objects`, it outputs:
```
netbox_get_objects<|channel|>commentary
```

DeepAgents' validation layer sees this as:
- Tool name: `netbox_get_objects<|channel|>commentary` ❌
- Expected: `netbox_get_objects` ✅

Result: **"netbox_get_objects<|channel|>commentary is not a valid tool"**

### Why It Works in langOllama

The `langOllama` repo uses plain `langchain.agents.create_agent()` which:
- Has simpler tool calling logic without extra validation
- Lets Ollama's template layer handle format conversion
- Trusts the model output more directly

DeepAgents adds stricter validation that rejects non-standard formats.

## Recommended Models

### ✅ DeepAgents-Compatible Models

These models use standard tool calling formats:

#### Tier 1: Production Ready (32B)
- **qwen2.5:32b-instruct-q4_K_M** ⭐ RECOMMENDED
  - Best balance of speed and accuracy
  - 19GB VRAM required
  - Excellent tool calling support
  - Proven with LangChain/DeepAgents

- **deepseek-r1:32b**
  - Superior reasoning capabilities
  - 19GB VRAM required
  - Strong for complex multi-step queries
  - r1 = reasoning-optimized

#### Tier 2: Lightweight Options (7-14B)
- **qwen2.5:14b-instruct-8k**
  - Good performance, 4.7GB
  - 8K context window
  - Fast inference

- **qwen2.5:7b-instruct-q4_K_M**
  - Lightweight, 4.7GB
  - Fast responses
  - Good for simple queries

- **llama3.1:8b**
  - Reliable and well-tested
  - 4.9GB VRAM
  - Standard tool calling

#### Tier 3: High-End (70B+)
- **llama3.1:70b** (if you have 40GB+ VRAM)
  - Best open-source reasoning
  - Very high accuracy
  - Slow inference

### ❌ Incompatible Models

**Do NOT use these with DeepAgents:**

- ❌ **gpt-oss:20b** - Harmony format incompatible
- ❌ **gpt-oss:120b** - Same Harmony format issues
- ❌ **qwen2.5-coder variants** - Optimized for code, not queries
- ❌ **llama3.2-vision** - Vision-specific model

## Model Name Format

### Full Quantization Names Supported

The system now accepts full Ollama model names with quantization suffixes:

✅ **Supported formats:**
```
qwen2.5:32b
qwen2.5:32b-instruct-q4_K_M
qwen2.5:14b-instruct-8k
deepseek-r1:32b
deepseek-r1:14b-q4_K_M
llama3.1:8b
llama3.1:70b-q4_K_M
```

❌ **Invalid formats:**
```
gpt-4  # Not an Ollama model
claude-3  # Not an Ollama model
random-model:123  # Not in supported families
```

### Validation Logic

The system validates model names using **prefix matching**:

```python
# src/utils/config.py — OllamaConfig.validate_model()
allowed_prefixes = [
    "gpt-oss:",
    "qwen2.5:",
    "qwen2:",
    "qwen3-coder:",
    "deepseek-r1:",
    "deepseek-r:",
    "deepseek-v3.1:",
    "deepseek-v4-pro:",
    "deepseek-v4-flash:",   # current default family
    "llama3.1:",
    "llama3.2:",
    "llama3:",
    "mixtral:",
]
```

Any model starting with these prefixes is accepted, including `:cloud` suffixed Ollama Cloud
variants and all quantization variants. To use a model whose prefix isn't listed, either add the
prefix here or set `DEBUG=true` to bypass validation. **The eval harness
(`tests/eval/run_matrix.py`) bypasses this validator entirely** via `load_netbox_config()`, so it
can score arbitrary models without editing the allow-list.

## Configuration

### .env File

```env
# RECOMMENDED: Use qwen2.5:32b with quantization suffix
OLLAMA_MODEL=qwen2.5:32b-instruct-q4_K_M

# Alternative: Use shorter name (Ollama will use default quantization)
OLLAMA_MODEL=qwen2.5:32b

# Lightweight option
OLLAMA_MODEL=qwen2.5:14b-instruct-8k

# Reasoning-focused
OLLAMA_MODEL=deepseek-r1:32b
```

### Command Line Override

```bash
# Use specific model
python -m src.main --model qwen2.5:32b-instruct-q4_K_M

# List available models
ollama list

# Check model details
ollama show qwen2.5:32b-instruct-q4_K_M
```

### Debug Mode

To bypass validation entirely (for testing):

```env
DEBUG=true
OLLAMA_MODEL=any-model-name:variant
```

## Testing Model Compatibility

### Quick Test (model connectivity)

```bash
./venv/bin/python -c "
from src.agents.ollama_config import create_ollama_model
m = create_ollama_model('gpt-oss:20b')  # or your OLLAMA_MODEL
print(m.invoke('reply with OK').content)
"
```

### Full Query Test

```bash
./venv/bin/python -m src.main
# Then type: "Show me all sites in NetBox"
```

### Example Scripts

```bash
./venv/bin/python examples/basic_usage.py
./venv/bin/python examples/failed_query_recovery.py
```

> A reproducible spike harness for direct MCP/PTC tool tests lives in `tests/spike/`
> (e.g. `./venv/bin/python -m tests.spike.spike1_mcp_ptc_bridge`).

## Performance Comparison

Based on available models:

| Model | Size | Speed | Accuracy | Tool Calling | Recommended |
|-------|------|-------|----------|--------------|-------------|
| qwen2.5:32b-instruct-q4_K_M | 19GB | Fast | Excellent | ✅ Yes | ⭐ Primary |
| deepseek-r1:32b | 19GB | Medium | Excellent | ✅ Yes | ⭐ Reasoning |
| qwen2.5:14b-instruct-8k | 4.7GB | Very Fast | Good | ✅ Yes | 💚 Light |
| llama3.1:8b | 4.9GB | Very Fast | Good | ✅ Yes | 💚 Light |
| gpt-oss:20b | 19GB | Fast | Good | ❌ No | ⛔ Incompatible |

## Troubleshooting

### "Model must start with one of..."

**Problem**: Your model name doesn't match the allowed prefixes.

**Solutions:**
1. Check your `.env` file for typos
2. Verify model is installed: `ollama list`
3. Use full model name from Ollama: `ollama list | grep qwen`
4. Enable debug mode temporarily: `DEBUG=true`

### "Model not found (status code: 404)"

**Problem**: Model not installed locally.

**Solution:**
```bash
ollama pull qwen2.5:32b-instruct-q4_K_M
```

### Tool calling produces strange output

**Problem**: Model might be using incompatible format.

**Solutions:**
1. Switch to recommended model (qwen2.5:32b-instruct-q4_K_M)
2. Check model template: `ollama show <model> --modelfile | grep TEMPLATE`
3. Verify model supports standard function calling

## Migration Guide

### From gpt-oss:20b to qwen2.5:32b

1. **Pull new model:**
   ```bash
   ollama pull qwen2.5:32b-instruct-q4_K_M
   ```

2. **Update .env:**
   ```env
   OLLAMA_MODEL=qwen2.5:32b-instruct-q4_K_M
   ```

3. **Test:**
   ```bash
   ./venv/bin/python -c "from src.agents.ollama_config import create_ollama_model; print(create_ollama_model('qwen2.5:32b-instruct-q4_K_M').invoke('OK').content)"
   ```

4. **Verify:**
   - Agent initialization succeeds
   - Tools load (4 tools)
   - No channel format errors

### Performance Notes

- **gpt-oss:20b**: 19GB, Harmony format, ❌ incompatible
- **qwen2.5:32b-instruct-q4_K_M**: 19GB, standard format, ✅ works perfectly

Same resource requirements, better compatibility!

## Additional Resources

- [Ollama Model Library](https://ollama.com/library)
- [LangChain Ollama Integration](https://python.langchain.com/docs/integrations/llms/ollama)
- [DeepAgents Documentation](https://docs.langchain.com/oss/python/deepagents/overview)
- [NetBox MCP Server](https://github.com/netbox-community/netbox-mcp-server)

---

**Last Updated**: 2026-02-09
**Issue**: Tool wrapper signature fixed, model validation improved
