# Documentation

Complete documentation for the NetBox DeepAgents project.

## Quick Links

- **[Setup Guides](setup/)** - Get started with installation and configuration
- **[Reference](reference/)** - Technical reference documentation
- **[How-to Guides](guides/)** - In-depth guides for specific tasks
- **[Development Notes](development/)** - Development decisions and session notes
- **[Trace Analysis](traces/)** - Performance analysis and trace reports

## Getting Started

1. Start with [Setup → Quick Start](setup/README.md#quickstart)
2. Configure your LLM backend: [llama.cpp](setup/llamacpp.md) or Ollama
3. Optionally enable [LangSmith tracing](setup/langsmith.md)
4. Review [Architecture](reference/architecture.md) to understand the system

## Documentation Structure

```
docs/
├── setup/          Setup and configuration guides
├── reference/      Technical reference and API docs
├── guides/         How-to guides and tutorials
├── development/    Development notes and decisions
├── traces/         LangSmith trace analysis reports
└── archive/        Obsolete content (kept for reference)
```

## Popular Topics

### Configuration
- [llama.cpp Setup](setup/llamacpp.md) - Use local GGUF models
- [LangSmith Setup](setup/langsmith.md) - Enable tracing and debugging
- [Model Compatibility](reference/model-compatibility.md) - Tested models and performance

### Understanding the System
- [Architecture](reference/architecture.md) - System design and components
- [MCP Constraints](reference/mcp-constraints.md) - NetBox MCP filter limitations
- [Ollama Models](reference/ollama-models.md) - Recommended Ollama models

### Advanced Usage
- [LangSmith Skills Assessment](guides/langsmith-skills-assessment.md) - Using LangSmith Skills
- [LangSmith Tracing Guide](guides/langsmith-tracing.md) - Deep dive into tracing

## Contributing

When adding documentation:
1. Place files in the appropriate directory
2. Update the relevant README.md
3. Use clear, descriptive filenames
4. Include a date prefix for development notes (YYYY-MM-DD)

---

**Project:** NetBox DeepAgents
**Backend:** llama.cpp (default) or Ollama
**Framework:** DeepAgents 0.6.10
