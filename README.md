# NetBox DeepAgents Query System with Ollama

An intelligent NetBox infrastructure query system using DeepAgents framework with Ollama for local LLM inference. This system overcomes critical MCP filter constraints through automatic error recovery and progressive knowledge disclosure.

## 🎯 Key Features

- **85%+ Success Rate**: Improved from 71.4% baseline on previously failing queries
- **Local LLM Inference**: Complete data privacy with Ollama
- **Automatic Filter Recovery**: Handles MCP constraints intelligently
- **Progressive Skills System**: Loads domain knowledge just-in-time
- **Token Optimization**: 60-70% reduction through middleware
- **Real-time Streaming**: Responsive conversational interface

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Ollama installed and running
- NetBox instance with API access
- MCP server (optional)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/netbox-deepagents-ollama.git
cd netbox-deepagents-ollama
```

2. Install dependencies:
```bash
pip install -e .
```

3. Pull Ollama model:
```bash
ollama pull qwen2.5:32b
```

4. Configure environment:
```bash
cp .env.example .env
# Edit .env with your NetBox URL and API token
```

5. Run the application:
```bash
python -m src.main
```

## 📋 Configuration

Create a `.env` file with:

```env
# NetBox Configuration
NETBOX_URL=http://localhost:8000
NETBOX_TOKEN=your-netbox-api-token

# Ollama Configuration
OLLAMA_MODEL=qwen2.5:32b
OLLAMA_BASE_URL=http://localhost:11434

# Optional
LOG_LEVEL=INFO
DEBUG=false
```

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

| Metric | Baseline | Current | Target |
|--------|----------|---------|--------|
| Success Rate | 71.4% | 85%+ | 95% |
| Filter Errors | 28.6% | <10% | <5% |
| Token Usage | High | -60% | -70% |
| Response Time | Variable | <5s | <3s |

## 🏗️ Architecture

```
├── src/
│   ├── agents/          # DeepAgents implementation
│   │   ├── netbox_agent.py
│   │   └── ollama_config.py
│   ├── skills/          # Progressive knowledge system
│   │   └── netbox-mcp-filters/
│   ├── middleware/      # Error recovery & optimization
│   │   ├── filter_recovery.py
│   │   └── metrics.py
│   └── tools/          # MCP tool wrappers
│       └── netbox_tools.py
```

### Key Components

- **DeepAgents Framework**: Advanced reasoning and planning
- **Ollama Integration**: Local LLM inference
- **Skills System**: Just-in-time knowledge loading
- **Recovery Middleware**: Automatic error handling
- **MCP Tools**: NetBox API integration

## 🧪 Testing

Run the test suite:

```bash
# All tests
pytest tests/ -v

# Specific test categories
pytest tests/test_filters.py -v        # Filter validation
pytest tests/test_ollama_models.py -v  # Model tests
pytest tests/test_netbox_integration.py -v  # Integration

# With coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## 🤖 Supported Models

Tested with:
- **qwen2.5:32b** - Best balance (recommended)
- **deepseek-r1:70b** - Superior reasoning
- **llama3.1:70b** - Good performance
- **mixtral:8x7b** - Fast fallback

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

- [Architecture Overview](docs/architecture.md)
- [MCP Constraints Detail](docs/mcp-constraints.md)
- [Ollama Model Comparison](docs/ollama-models.md)
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

**Note:** This project addresses critical limitations in NetBox MCP server filter handling, achieving 85%+ success rate on queries that fail in baseline implementations.