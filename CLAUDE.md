# DeepAgents NetBox Query System with Ollama

## Project Purpose

This project creates an intelligent NetBox infrastructure query system using DeepAgents framework with Ollama for local LLM inference. It enables natural language queries against NetBox data while maintaining complete data privacy through local model execution, addressing the critical challenge of MCP filter constraints that cause failures in simpler implementations.

## Project Context & Awareness

### Before Starting Any Task:
1. **Read Project Documentation**:
   - Review this CLAUDE.md file completely
   - Check `README.md` for setup instructions
   - Review `docs/` for architecture decisions
   - Check `skills/` directory for NetBox-specific skills

2. **Understand the Problem Domain**:
   - NetBox MCP server has strict filter limitations
   - Multi-hop filters like `device__site_id` are NOT supported
   - Django lookup suffixes (`__icontains`, `__in`) fail
   - Previous implementations achieved only 71.4% success rate

3. **Check Development Status**:
   - Review `TODO.md` for pending tasks
   - Check git log for recent changes
   - Verify test results in `tests/results/`

## Architecture Overview

### Core Components

```
ollamaDeepAgents/
├── src/
│   ├── agents/          # DeepAgents implementation
│   │   ├── netbox_agent.py
│   │   └── ollama_config.py
│   ├── skills/          # NetBox-specific skills
│   │   └── netbox-mcp-filters/
│   │       ├── SKILL.md
│   │       └── constraints.md
│   ├── middleware/      # Custom middleware
│   │   ├── filter_recovery.py
│   │   └── token_optimizer.py
│   └── tools/          # MCP tool wrappers
│       └── netbox_tools.py
├── tests/              # Comprehensive test suite
├── docs/              # Documentation
└── examples/          # Usage examples
```

### Technology Stack
- **Framework**: DeepAgents 0.3.12+ (LangChain + LangGraph)
- **LLM Provider**: Ollama (local inference)
- **Recommended Models**: qwen2.5:32b, deepseek-r1:70b
- **MCP Server**: NetBox MCP v1.0.0
- **Python**: 3.11+

## Code Structure & Best Practices

### Module Organization
```python
# Maximum file size: 500 lines
# If exceeding, split into logical modules

# src/agents/netbox_agent.py - Core agent
# src/agents/ollama_config.py - Model configuration
# src/middleware/filter_recovery.py - Error handling
# src/tools/netbox_tools.py - MCP tool wrappers
```

### Import Conventions
```python
# Standard library
import os
import sys
from typing import Dict, List, Optional

# Third-party
from deepagents import create_deep_agent
from langchain_ollama import ChatOllama
from langchain.agents.middleware import SummarizationMiddleware

# Local - use relative imports
from ..skills import load_netbox_skills
from ..middleware.filter_recovery import FilterErrorRecoveryMiddleware
from ..tools.netbox_tools import create_mcp_tools
```

## Skills System Implementation

### NetBox MCP Filter Skill
```markdown
# skills/netbox-mcp-filters/SKILL.md
---
title: NetBox MCP Filter Constraints
type: knowledge
trigger: netbox queries with filtering
priority: high
---

## CRITICAL FILTER LIMITATIONS

### NEVER Use These Patterns:
1. Relationship traversal: `device__site_id`, `termination_a__device_id`
2. Django lookups: `__icontains`, `__contains`, `__startswith`, `__in`
3. Multi-hop patterns: Any filter with double underscores for relationships

### ALWAYS Use These Patterns:
1. Direct ID filters: `{"device_id": 123}`, `{"site_id": 5}`
2. Exact name matches: `{"name": "exact-match"}`
3. Two-step queries for relationships:
   ```python
   # Step 1: Get entity by name
   device = netbox_get_objects("dcim.device", {"name": "pdu01"})
   # Step 2: Use entity ID in filter
   cables = netbox_get_objects("dcim.cable", {"device_id": device['id']})
   ```
4. Pattern matching: Use `netbox_search_objects(query="pattern")`

## Common Failure Patterns & Solutions

### Cable Query Pattern
**WRONG**: `{"termination_a__device_id": 19}`
**RIGHT**: Two-step query with device lookup first

### Site Search Pattern
**WRONG**: `{"name__icontains": "dunder"}`
**RIGHT**: `netbox_search_objects(query="dunder")`
```

## Ollama Integration

### Model Configuration
```python
# src/agents/ollama_config.py
from langchain_ollama import ChatOllama

def create_ollama_model(
    model_name: str = "qwen2.5:32b",
    temperature: float = 0.0,
    validate: bool = True
) -> ChatOllama:
    """Create Ollama model with optimized settings for NetBox queries."""
    return ChatOllama(
        model=model_name,
        temperature=temperature,
        validate_model_on_init=validate,
        format=None,  # Use 'json' for structured output if needed
        options={
            "num_ctx": 8192,  # Context window
            "num_predict": 2048,  # Max tokens to generate
            "top_k": 10,
            "top_p": 0.95,
        }
    )

# Recommended models by capability:
# - qwen2.5:32b - Best balance of speed and accuracy
# - deepseek-r1:70b - Superior reasoning for complex queries
# - llama3.1:70b - Good general performance
# - mixtral:8x7b - Fast with decent accuracy
```

## Testing Strategy

### Test Categories
1. **Filter Constraint Tests** (`tests/test_filters.py`):
   - Test all known failure patterns
   - Verify two-step query execution
   - Validate error recovery

2. **Model Compatibility Tests** (`tests/test_ollama_models.py`):
   - Test with multiple Ollama models
   - Measure success rates per model
   - Document model-specific quirks

3. **Integration Tests** (`tests/test_netbox_integration.py`):
   - Test real NetBox queries
   - Validate MCP tool responses
   - Verify skill loading

### Test Fixtures
```python
# tests/conftest.py
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_netbox_response():
    """Mock NetBox API responses for testing."""
    return {
        "count": 1,
        "results": [{"id": 1, "name": "test-device"}]
    }

@pytest.fixture
def failed_queries():
    """Queries that fail in baseline implementation."""
    return [
        "Show cables connected to device dmi01-nashua-pdu01",
        "Show all Dunder-Mifflin sites with device counts",
    ]
```

## Success Metrics

### Target Performance
| Metric | Baseline | Target | Stretch Goal |
|--------|----------|--------|--------------|
| Query Success Rate | 71.4% | 85% | 95% |
| Filter Errors | 28.6% | <10% | <5% |
| Token Usage | High | -60% | -70% |
| Response Time | Variable | <5s | <3s |

### Monitoring
```python
# src/utils/metrics.py
class QueryMetrics:
    def __init__(self):
        self.total_queries = 0
        self.successful_queries = 0
        self.filter_errors = 0
        self.token_usage = []

    def log_query(self, query: str, success: bool, tokens: int):
        self.total_queries += 1
        if success:
            self.successful_queries += 1
        self.token_usage.append(tokens)

    @property
    def success_rate(self) -> float:
        return (self.successful_queries / self.total_queries) * 100
```

## Critical Implementation Rules

### MCP Filter Constraints (MUST FOLLOW)
1. **NEVER** attempt multi-hop filters in a single query
2. **ALWAYS** use two-step queries for relationship traversal
3. **VALIDATE** filter patterns before MCP tool execution
4. **IMPLEMENT** FilterErrorRecoveryMiddleware for automatic retry

### Error Recovery Pattern
```python
# src/middleware/filter_recovery.py
class FilterErrorRecoveryMiddleware(AgentMiddleware):
    """Catches and recovers from MCP filter errors."""

    def after_model(self, state: AgentState) -> Dict[str, Any] | None:
        if "Invalid filter" in str(state.get("error", "")):
            # Extract invalid filter pattern
            invalid_filter = self.extract_filter(state["error"])

            # Generate corrected approach
            if "__" in invalid_filter:
                # Suggest two-step query
                return {
                    "retry_strategy": "two_step_query",
                    "hint": f"Use two-step query instead of {invalid_filter}"
                }
        return None
```

## Development Workflow

### 1. Feature Development
```bash
# Create feature branch
git checkout -b feature/improved-filter-handling

# Implement with TDD
# 1. Write failing test
# 2. Implement minimal code to pass
# 3. Refactor for clarity

# Test locally with Ollama
ollama run qwen2.5:32b
python -m pytest tests/

# Document changes
# Update README.md, add to CHANGELOG.md
```

### 2. Testing Failed Queries
```python
# examples/test_failed_queries.py
failed_queries = [
    "Show cables connected to device dmi01-nashua-pdu01",
    "Show all Dunder-Mifflin sites with device counts",
]

for query in failed_queries:
    result = agent.invoke({"messages": [{"role": "user", "content": query}]})
    print(f"Query: {query}")
    print(f"Success: {result.success}")
    print(f"Response: {result.content[:200]}...")
```

## Task Completion Checklist

When implementing features:
- [ ] Write comprehensive tests first
- [ ] Implement with clear, modular code
- [ ] Add error handling and recovery
- [ ] Update documentation
- [ ] Test with multiple Ollama models
- [ ] Verify filter constraint compliance
- [ ] Update metrics tracking
- [ ] Add to CHANGELOG.md

## Known Issues & Workarounds

### Issue 1: Ollama Context Window Limits
**Problem**: Some models have small context windows
**Solution**: Use SummarizationMiddleware to reduce token usage

### Issue 2: Tool Binding with init_chat_model
**Problem**: NotImplementedError with some Ollama models
**Solution**: Use ChatOllama directly instead of init_chat_model

### Issue 3: Slow Response with Large Models
**Problem**: deepseek-r1:70b takes 10+ seconds
**Solution**: Use qwen2.5:32b for development, larger models for production

## Resources & Documentation

### Internal Documentation
- `docs/architecture.md` - System design decisions
- `docs/mcp-constraints.md` - Detailed filter limitations
- `docs/ollama-models.md` - Model comparison results
- `skills/README.md` - Skills development guide

### External Resources
- [DeepAgents Documentation](https://docs.langchain.com/oss/python/deepagents)
- [Ollama Model Library](https://ollama.com/library)
- [NetBox API Documentation](https://docs.netbox.dev/en/stable/rest-api/)
- [MCP Protocol Specification](https://modelcontextprotocol.io/)

## Security & Privacy

### Local Model Advantages
- **Zero API costs**: All inference is local
- **Complete privacy**: Data never leaves your infrastructure
- **No rate limits**: Process unlimited queries
- **Compliance ready**: Meets data residency requirements

### Security Considerations
```python
# Always validate NetBox credentials
if not os.getenv("NETBOX_TOKEN"):
    raise ValueError("NETBOX_TOKEN environment variable required")

# Never log sensitive data
logger.info(f"Querying NetBox at {netbox_url}")  # OK
# logger.info(f"Token: {token}")  # NEVER DO THIS
```

## Environment Variables

Required in `.env`:
```bash
# NetBox Configuration
NETBOX_URL=http://localhost:8000
NETBOX_TOKEN=your-netbox-api-token

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:32b
OLLAMA_TEMPERATURE=0.0

# DeepAgents Configuration
DEEPAGENTS_LOG_LEVEL=INFO
DEEPAGENTS_USE_SKILLS=true
DEEPAGENTS_CACHE_ENABLED=true

# Development
DEBUG=false
TEST_MODE=false
```

## Definition of Done

A feature is complete when:
1. All tests pass (unit, integration, e2e)
2. Documentation is updated
3. Code follows project conventions
4. Filter constraints are validated
5. Success rate meets or exceeds target
6. Changes are logged in CHANGELOG.md
7. Code review completed
8. Merged to main branch

## AI Assistant Behavior Rules

### DO:
- Ask for clarification on ambiguous requirements
- Verify file paths before operations
- Test filter patterns before implementation
- Document reasoning in code comments
- Suggest two-step queries for relationships
- Use skills system for knowledge management

### DON'T:
- Assume filter patterns will work
- Skip error handling
- Use deprecated LangChain patterns
- Hardcode model names
- Ignore token optimization
- Bypass the skills system

## Success Criteria

The project is successful when:
1. **Query success rate >= 85%** on previously failed queries
2. **Token usage reduced by 60%** through skills and middleware
3. **All filter errors handled** gracefully with recovery
4. **Multiple Ollama models** supported and tested
5. **Documentation complete** for all components
6. **Production ready** with monitoring and metrics

---

*This CLAUDE.md file is the source of truth for project context and development guidelines. Update it as the project evolves.*
