# Setup & Configuration

Guides for installing and configuring the NetBox DeepAgents system.

## Quick Start {#quickstart}

### 1. Install Dependencies

```bash
# Clone the repository
git clone <repo-url>
cd ollamaDeepAgents

# Install Python dependencies
pip install -e .
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env` with your settings:
- NetBox URL and API token
- LLM backend selection (llama.cpp or ollama)
- Optional: LangSmith tracing credentials

### 3. Start Your LLM Backend

Choose one:

**Option A: llama.cpp (Recommended)**
```bash
# Start llama.cpp server (see llamacpp.md for details)
./llama-server --model models/Qwen_Qwen3-14B-Q5_K_M.gguf --port 58123
```

**Option B: Ollama**
```bash
# Start Ollama (see Ollama documentation)
ollama serve
ollama pull qwen2.5:14b
```

### 4. Run the Agent

```bash
python -m src.main
```

## Configuration Guides

### Core Configuration

- **[llama.cpp Setup](llamacpp.md)** - Configure local GGUF models with llama.cpp
  - Model selection and download
  - Server configuration
  - Performance tuning
  - Troubleshooting

### Optional Features

- **[LangSmith Tracing](langsmith.md)** - Enable observability and debugging
  - Quick 5-minute setup
  - Environment variables
  - Verification steps

- **[LangSmith Skills](langsmith-skills.md)** - Terminal-based trace analysis
  - Installation guide
  - Available skills
  - Usage examples

## Common Configurations

### Development Setup (Fast Iteration)
```env
LLM_BACKEND=llamacpp
LLAMACPP_MODEL=Qwen_Qwen3-14B-Q5_K_M.gguf  # 14B for good quality
LANGCHAIN_TRACING_V2=true                   # Enable tracing
```

### Production Setup (Best Quality)
```env
LLM_BACKEND=llamacpp
LLAMACPP_MODEL=Qwen_Qwen3-14B-Q5_K_M.gguf  # Or larger model
LANGCHAIN_TRACING_V2=false                  # Disable for performance
```

### Testing Setup (Fast, Minimal)
```env
LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5:7b                     # Smaller, faster
LANGCHAIN_TRACING_V2=true                   # Enable for debugging
```

## Environment Variables Reference

### Required
- `NETBOX_URL` - NetBox instance URL
- `NETBOX_TOKEN` - NetBox API token
- `LLM_BACKEND` - `llamacpp` or `ollama`

### LLM Backend (llama.cpp)
- `LLAMACPP_BASE_URL` - Default: `http://localhost:58123/v1`
- `LLAMACPP_MODEL` - GGUF filename or model name
- `LLAMACPP_API_KEY` - Default: `not-needed`

### LLM Backend (Ollama)
- `OLLAMA_BASE_URL` - Default: `http://localhost:11434`
- `OLLAMA_MODEL` - Model name (e.g., `qwen2.5:14b`)

### Optional: LangSmith Tracing
- `LANGCHAIN_API_KEY` - Your LangSmith API key
- `LANGCHAIN_PROJECT` - Project name (e.g., `netbox-deepagents-llamacpp`)
- `LANGCHAIN_TRACING_V2` - `true` to enable

## Troubleshooting

### "Connection refused" errors
- Ensure your LLM backend is running
- Check the URL in `.env` matches your server
- Verify firewall settings

### "Model not found" errors
- For llama.cpp: Ensure model file exists in the path specified
- For Ollama: Run `ollama pull <model-name>` first

### Slow responses
- Use a smaller model (7B instead of 14B)
- Check GPU availability
- Enable prompt caching (automatic in llama.cpp)

### Import errors
- Ensure you installed with `pip install -e .`
- Check Python version >= 3.11

## Next Steps

After setup:
1. Review [Architecture](../reference/architecture.md) to understand the system
2. Check [Model Compatibility](../reference/model-compatibility.md) for tested models
3. Read [MCP Constraints](../reference/mcp-constraints.md) for NetBox query patterns
4. Try the examples in `examples/`

## Getting Help

- Check [Development Notes](../development/) for troubleshooting similar issues
- Review [Trace Analysis](../traces/) for performance patterns
- See main [README](../../README.md) for project overview

---

**Last Updated:** 2026-05-05
