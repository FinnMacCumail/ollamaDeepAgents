# NetBox DeepAgents Query System

An intelligent NetBox infrastructure query system built on the **DeepAgents 0.6** framework. It
answers natural-language questions against NetBox data, working around the NetBox MCP server's
strict filter constraints through automatic error recovery and progressive knowledge disclosure.

Inference runs through one of two interchangeable backends (one-line `.env` switch):
- **Ollama** — local models *and* Ollama Cloud frontier models (`:cloud`). Default:
  `deepseek-v4-flash:cloud`.
- **llama.cpp** — OpenAI-compatible server for the fully-local / privacy-critical path.

## 🎯 Key Features

- **Dual backend**: Ollama (local + Cloud) or llama.cpp, selected via `LLM_BACKEND`
- **Automatic Filter Recovery**: converts MCP filter violations into recoverable structured errors
- **Progressive Skills System**: loads NetBox domain knowledge just-in-time
- **Model-matrix evaluation**: LangSmith-based harness (`tests/eval/`) scoring models on a fixed benchmark
- **Real-time Streaming**: responsive conversational interface

> **Privacy note:** the default Ollama Cloud path sends queries and tool results to `ollama.com`.
> Use the [llama.cpp backend](docs/setup/llamacpp.md) for data-never-leaves-the-box operation.

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- NetBox instance with API access + the NetBox MCP server
- One inference backend: Ollama (local daemon and/or Cloud Pro subscription) **or** a llama.cpp server

### Installation

1. Clone and install:
```bash
git clone https://github.com/yourusername/netbox-deepagents-ollama.git
cd netbox-deepagents-ollama
pip install -e .                     # pulls deepagents>=0.6.10
```

2. Pick a backend and model:
```bash
# Ollama Cloud (default): see docs/setup/ollama-cloud.md
ollama signin && ollama run deepseek-v4-flash:cloud "hi"
# or a local Ollama model:  ollama pull qwen2.5:32b
# or llama.cpp:             see docs/setup/llamacpp.md
```

3. Configure environment, then run:
```bash
cp .env.example .env                 # edit with your values
./venv/bin/python -m src.main
```

## 📋 Configuration

Create a `.env` file with:

```env
# Backend selection
LLM_BACKEND=ollama                       # ollama | llamacpp

# NetBox
NETBOX_URL=http://localhost:8000
NETBOX_TOKEN=your-netbox-api-token
MCP_SERVER_PATH=/path/to/netbox-mcp-server

# Ollama (local + cloud)
OLLAMA_MODEL=deepseek-v4-flash:cloud     # default; gpt-oss:20b if unset
OLLAMA_BASE_URL=http://localhost:11434

# llama.cpp backend (when LLM_BACKEND=llamacpp)
LLAMACPP_BASE_URL=http://localhost:8080/v1
LLAMACPP_MODEL=Qwen_Qwen3-14B-Q5_K_M.gguf

# LangSmith tracing (optional; never commit a real key)
LANGCHAIN_API_KEY=lsv2_pt_xxxxxxxx
LANGCHAIN_TRACING_V2=true

# Dev
DEBUG=false                              # DEBUG=true bypasses the model-prefix validator
```

See `docs/setup/` for backend-specific guides (Ollama Cloud, llama.cpp, LangSmith).

## 💡 Usage Examples

### Interactive Mode

```bash
python -m src.main

NetBox Query> Show all devices in site NYC-DC1
# Returns devices with automatic filter handling

NetBox Query> List cables connected to router01
# Automatically uses two-step query to avoid filter errors
```

### Batch Mode

```bash
python -m src.main --batch \
  "Count devices in production" \
  "Show all active circuits" \
  "Find interfaces on switch01"
```

### Python API

```python
import asyncio
from src.agents.netbox_agent import create_netbox_agent

async def main():
    agent = await create_netbox_agent()

    # Simple query
    response = await agent.query_sync("Show all sites")
    print(response)

    # Streaming response
    async for chunk in agent.query("List devices in rack R01"):
        print(chunk, end="")

    await agent.cleanup()

asyncio.run(main())
```

## 🔧 How It Works

### MCP Filter Constraints

The NetBox MCP server has strict filter limitations:

❌ **Not Supported:**
- Multi-hop filters: `device__site_id`
- Django lookups: `name__icontains`
- Relationship traversals: `interface__device__name`

✅ **Supported:**
- Direct ID filters: `{"device_id": 123}`
- Exact matches: `{"name": "exact-name"}`
- Simple fields: `{"status": "active"}`

### Automatic Recovery

When a filter fails, the system:

1. **Detects** the invalid filter pattern
2. **Generates** a recovery strategy (two-step query or search)
3. **Retries** with the corrected approach
4. **Succeeds** where baseline implementations fail

### Example Recovery

**Failed Query:** "Show cables for device router01"

**Baseline Approach (Fails):**
```python
cables = netbox_get_objects("dcim.cable", {"termination_a__device_id": 19})
# ERROR: Invalid filter
```

**Our Approach (Succeeds):**
```python
# Step 1: Get device by name
device = netbox_get_objects("dcim.device", {"name": "router01"})
# Step 2: Use device ID
cables = netbox_get_objects("dcim.cable", {"device_id": device['id']})
```

## 📊 Performance Metrics

Quality and latency are now measured empirically by the model-matrix eval harness against the
fixed `netbox-benchmark-v2` dataset, not estimated. Representative result for the default model
(`deepseek-v4-flash:cloud`): entity-coverage ~0.95, completeness ~1.00 across the four benchmark
queries; per-query wall time ranges from ~15s (single-object) to ~90s (multi-aspect / cross-
relationship). See `tests/eval/` and the experiment results on LangSmith, plus
`docs/development/2026-06-14_deepagents-0.6-upgrade.md` for the latest measured baselines.

## 🏗️ Architecture

```
├── src/
│   ├── main.py              # CLI entry point
│   ├── agents/              # Agent factory + backend model setup
│   │   ├── netbox_agent.py  #   core factory + HarnessProfile (Workaround B)
│   │   ├── ollama_config.py #   Ollama (local + :cloud)
│   │   └── llamacpp_config.py
│   ├── middleware/          # filter_recovery.py, metrics.py
│   ├── tools/               # netbox_tools.py (MCP client, validator)
│   ├── skills/              # netbox-mcp-filters/ (progressive disclosure)
│   └── utils/               # config.py, logging.py
├── tests/
│   ├── eval/                # model-matrix evaluation harness (LangSmith)
│   ├── spike/               # QuickJS PTC verification spikes
│   └── test_*.py            # unit / integration tests
└── docs/                    # development/, setup/, guides/, reference/, traces/
```

### Key Components

- **DeepAgents 0.6 framework** with a custom middleware stack + Workaround-B HarnessProfile
- **Dual backend**: Ollama (local + Cloud) / llama.cpp
- **Skills System**: just-in-time NetBox knowledge loading
- **Recovery Middleware**: filter violations → recoverable structured errors
- **Eval harness**: LangSmith model-matrix scoring (`tests/eval/`)

See [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md) for the full architecture.

## 🧪 Testing

Run the test suite:

```bash
# Unit / integration tests
./venv/bin/python -m pytest tests/test_filters.py -v             # Filter validator
./venv/bin/python -m pytest tests/test_netbox_integration.py -v  # Agent init + query
./venv/bin/python -m pytest tests/test_ollama_models.py -v       # Model compatibility

# Model-matrix evaluation (LangSmith) — quality gate after agent changes
./venv/bin/python -m tests.eval.run_matrix
EVAL_FORCE_RERUN=1 EVAL_MODELS="ollama:deepseek-v4-flash:cloud" \
  ./venv/bin/python -m tests.eval.run_matrix   # single-model regression check
```

The eval harness scores models against the fixed `netbox-benchmark-v2` dataset
(entity coverage, completeness, tool-call efficiency). See `tests/eval/` and
`docs/development/2026-06-03_langsmith-evaluation-research.md`.

## 🤖 Supported Models

Selected via `OLLAMA_MODEL` (or `--model`). Benchmarked in the 10-model cloud sweep:
- **deepseek-v4-flash:cloud** — default; matches `pro` quality at ~36% lower latency
- **deepseek-v4-pro:cloud** — 1.6T frontier MoE
- **glm-5:cloud** — fastest in the matrix (LangChain's DeepAgents reference model)
- **kimi-k2.6:cloud**, **minimax-m3:cloud**, **nemotron-3-ultra:cloud** — other frontier options
- Local models (Ollama / llama.cpp): **qwen2.5:32b**, **gpt-oss:20b**, etc. — viable but the
  matrix shows frontier models are needed for the hardest multi-aspect queries.

The model-prefix validator in `src/utils/config.py` gates `OLLAMA_MODEL`; add prefixes there or
set `DEBUG=true` to experiment with others.

## 🔍 Troubleshooting

### Common Issues

**"Invalid filter" errors:**
- The system should automatically recover
- Check logs for recovery attempts
- Ensure skills are loaded from `src/skills/`

**Ollama connection failed:**
```bash
# Check Ollama is running
ollama list
ollama serve  # Start if needed
```

**NetBox authentication:**
- Verify NETBOX_URL and NETBOX_TOKEN in `.env`
- Check token has appropriate permissions

## 📚 Documentation

### Core Documentation
- [Documentation Index](docs/README.md) - Complete documentation overview
- [Setup Guides](docs/setup/) - Installation and configuration
- [Reference Documentation](docs/reference/) - Technical details

### Quick Links
- [Architecture Overview](docs/reference/architecture.md)
- [MCP Constraints Detail](docs/reference/mcp-constraints.md)
- [Ollama Model Comparison](docs/reference/ollama-models.md)
- [llama.cpp Setup](docs/setup/llamacpp.md)
- [LangSmith Tracing](docs/setup/langsmith.md)
- [Skills Development](src/skills/README.md)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- DeepAgents framework by LangChain
- Ollama for local LLM inference
- NetBox for infrastructure management
- MCP protocol for tool integration

## 📈 Roadmap

- [ ] Add more Ollama model support
- [ ] Implement caching layer
- [ ] Create web interface
- [ ] Add bulk operation support
- [ ] Enhance metrics dashboard
- [ ] Support for NetBox plugins

---

**Note:** This project addresses critical limitations in NetBox MCP server filter handling —
queries that fail in naive implementations succeed here via the `FilterValidator` + automatic
error recovery and the progressive-disclosure skills system. Quality is tracked empirically by
the `tests/eval/` model-matrix harness. See [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md)
for the architecture and engineering conventions.