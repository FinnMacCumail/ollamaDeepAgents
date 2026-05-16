# Reference Documentation

Technical reference documentation for the NetBox DeepAgents system.

## Architecture & Design

### [Architecture](architecture.md)
System architecture and component overview:
- DeepAgents framework integration
- LLM provider abstraction (llama.cpp/Ollama)
- NetBox MCP client integration
- Middleware stack
- Skills system

## NetBox Integration

### [MCP Constraints](mcp-constraints.md)
Critical knowledge about NetBox MCP filter limitations:
- Unsupported filter patterns
- Two-step query patterns
- Search vs filter strategies
- Common error patterns
- Recovery strategies

**This is essential reading** - understanding these constraints is key to successful queries.

## Model Information

### [Model Compatibility](model-compatibility.md)
Tested models and their performance characteristics:
- Recommended models for different use cases
- Token usage patterns
- Response time benchmarks
- Quality comparisons
- Hardware requirements

### [Ollama Models](ollama-models.md)
Detailed guide to Ollama models:
- Model selection criteria
- Installation instructions
- Configuration best practices
- Model comparison matrix

## Skills System

Skills are stored in `src/skills/` and provide progressive disclosure of domain knowledge:

### Available Skills

**netbox-mcp-filters** (Priority: High)
- Filter constraint knowledge
- Two-step query patterns
- Pattern matching strategies
- See: `src/skills/netbox-mcp-filters/SKILL.md`

For more on the skills system, see `src/skills/README.md`.

### Developer-only Skills (Claude Code, not runtime)

These live under `.claude/skills/` and are loaded by Claude Code sessions opened
in this repo. They are NOT loaded by the deployed NetBox agent:

**trace-analysis** (`.claude/skills/trace-analysis/SKILL.md`)
- LangSmith trace analysis workflow
- Report generation into `docs/traces/`
- Used when a developer is interactively analysing agent behaviour

## API Reference

### Main Components

**NetBoxDeepAgent**
```python
from src.agents.netbox_agent import create_netbox_agent

agent = await create_netbox_agent(
    model_name="Qwen_Qwen3-14B-Q5_K_M.gguf",
    backend="llamacpp",
    enable_metrics=True
)

async for chunk in agent.query("list all sites"):
    print(chunk)
```

**Middleware Stack**
- `FilterErrorRecoveryMiddleware` - Automatic filter error recovery
- `MetricsMiddleware` - Performance tracking
- `TokenOptimizationMiddleware` - Token usage optimization
- `SummarizationMiddleware` - Context window management (DeepAgents built-in)

**Tools**
- `netbox_get_objects` - Fetch objects with filters
- `netbox_search_objects` - Full-text search
- `netbox_list_object_types` - Discover available object types

## Performance Characteristics

### Typical Query Performance (14B Model)

**Simple "list sites" query:**
- Duration: ~35-40 seconds
- Token usage: ~23K tokens
- LLM calls: 2 (tool selection + formatting)
- Cache hit rate: 88-99%

**Complex multi-step query:**
- Duration: ~60-90 seconds
- Token usage: ~40-50K tokens
- LLM calls: 4-6
- Cache hit rate: 85-95%

See [Trace Analysis](../traces/) for detailed performance reports.

## Configuration

### Environment Variables

See [Setup Guide](../setup/README.md#environment-variables-reference) for complete list.

### Model Selection

| Use Case | Recommended Model | Rationale |
|----------|------------------|-----------|
| Development | Qwen3-14B-Q5_K_M | Best balance of speed/quality |
| Production | Qwen3-14B or larger | Best quality |
| Testing | Qwen2.5:7b | Fastest responses |
| Complex queries | 32B+ models | Superior reasoning |

## System Requirements

### Minimum
- Python 3.11+
- 8GB RAM
- NetBox instance with API access

### Recommended for llama.cpp
- 16GB+ RAM (for 14B models)
- GPU with 8GB+ VRAM (optional, for faster inference)
- SSD for model storage

### Recommended for Ollama
- 16GB+ RAM
- GPU with 8GB+ VRAM (recommended)

## Troubleshooting

### Common Issues

**Filter errors**
- Read [MCP Constraints](mcp-constraints.md)
- The `netbox-mcp-filters` skill provides automatic recovery

**Slow performance**
- Use smaller models
- Enable GPU acceleration
- Check [Model Compatibility](model-compatibility.md) for benchmarks

**Out of memory**
- Reduce model size
- Increase system RAM
- Use quantized models (Q4, Q5 instead of Q8)

## Further Reading

- [Setup Guides](../setup/) - Installation and configuration
- [How-to Guides](../guides/) - Specific tasks and features
- [Development Notes](../development/) - Implementation decisions
- [Trace Analysis](../traces/) - Performance analysis

---

**Framework:** DeepAgents 0.5.6
**Supported Backends:** llama.cpp, Ollama
**Python:** 3.11+
