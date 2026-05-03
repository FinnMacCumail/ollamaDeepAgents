## FEATURE:

We want to create an intelligent NetBox infrastructure query system using the DeepAgents framework (0.3.12+) with Ollama for local LLM inference. The application will provide a conversational interface to interact with NetBox infrastructure data while addressing critical MCP filter constraints that cause failures in simpler implementations.

**Key Differentiator**: This implementation uses DeepAgents' SKILLS system to progressively disclose domain-specific knowledge about NetBox MCP filter limitations, improving query success rates from a baseline of 71.4% to a target of 85%+.

## Architecture Components

### 1. LLM Provider: Ollama
- **URL**: http://localhost:11434/
- **Purpose**: Local LLM inference for privacy and cost-efficiency
- **Recommended Models**:
  - `qwen2.5:32b` - Best balance of speed and accuracy (recommended for development)
  - `deepseek-r1:70b` - Superior reasoning for complex queries (production)
  - `llama3.1:70b` - Good general performance
  - `mixtral:8x7b` - Fast with decent accuracy
- **Configuration**: Temperature 0.0, context window 8192 tokens

### 2. Framework: DeepAgents 0.3.12+
- **Base**: LangChain + LangGraph agent harness
- **Key Components**:
  - `create_deep_agent` - Main agent creation API
  - **SKILLS System** - Progressive disclosure of domain knowledge
  - `SummarizationMiddleware` - Token optimization (-60% to -70% reduction)
  - `SubAgentMiddleware` - Multi-agent coordination
  - `TodoListMiddleware` - Task tracking
  - `FilesystemMiddleware` - File operations
- **Python Version**: 3.11+

### 3. Skills System (NEW in 0.3.x)
- **Purpose**: Progressive disclosure of NetBox MCP filter constraints
- **Location**: `src/skills/netbox-mcp-filters/SKILL.md`
- **Key Skills**:
  - NetBox MCP Filter Constraints (high priority)
  - Two-step query patterns for relationship traversal
  - Error recovery strategies
- **Benefits**:
  - Reduces token usage by loading knowledge only when needed
  - Provides targeted guidance for specific query patterns
  - Enables automatic error recovery with corrected approaches

### 4. Custom Middleware
- **FilterErrorRecoveryMiddleware**: Catches and recovers from MCP filter errors
- **SummarizationMiddleware**: Reduces context size for Ollama models
- **Performance Monitoring**: Track success rates and token usage

### 5. NetBox MCP Server
- **Location**: `/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server`
- **NetBox Instance**: http://localhost:8000/
- **Protocol**: Model Context Protocol (MCP)
- **Tools Available**:
  - `netbox_get_objects`: List/search any NetBox object type
  - `netbox_get_object_by_id`: Get detailed object information
  - `netbox_get_changelogs`: Query change audit logs
  - `netbox_search_objects`: Global search across object types

**Critical MCP Constraints**:
- ❌ NO multi-hop filters: `device__site_id`, `termination_a__device_id`
- ❌ NO Django lookups: `__icontains`, `__in`, `__startswith`
- ✅ YES direct ID filters: `{"device_id": 123}`, `{"site_id": 5}`
- ✅ YES two-step queries for relationships
- ✅ YES search tool for pattern matching

## EXAMPLES:

### Example 1: Failed Query Pattern (Baseline)
**Query**: "Show cables connected to device dmi01-nashua-pdu01"

**Baseline Approach** (fails):
```python
# ❌ This fails with "Invalid filter: termination_a__device_id"
cables = netbox_get_objects("dcim.cable", {"termination_a__device_id": 19})
```

**DeepAgents + SKILLS Approach** (succeeds):
```python
# ✅ Two-step query using SKILLS guidance
# Step 1: Get device by name
device = netbox_get_objects("dcim.device", {"name": "dmi01-nashua-pdu01"})
# Step 2: Use device ID in filter
cables = netbox_get_objects("dcim.cable", {"device_id": device['id']})
```

### Example 2: Site Search Pattern
**Query**: "Show all Dunder-Mifflin sites with device counts"

**Baseline Approach** (fails):
```python
# ❌ This fails with "Invalid filter: name__icontains"
sites = netbox_get_objects("dcim.site", {"name__icontains": "dunder"})
```

**DeepAgents + SKILLS Approach** (succeeds):
```python
# ✅ Use search tool instead of filtered query
sites = netbox_search_objects(query="Dunder-Mifflin")
```

### Example 3: Ollama Model Configuration
```python
from langchain_ollama import ChatOllama
from deepagents import create_deep_agent

# Create Ollama model with optimized settings
model = ChatOllama(
    model="qwen2.5:32b",
    temperature=0.0,
    validate_model_on_init=True,
    options={
        "num_ctx": 8192,
        "num_predict": 2048,
        "top_k": 10,
        "top_p": 0.95,
    }
)

# Create DeepAgent with SKILLS
agent = create_deep_agent(
    model=model,
    tools=netbox_tools,
    system_prompt=NETBOX_PROMPT,
    middleware=[
        FilterErrorRecoveryMiddleware(),
        # SummarizationMiddleware is included by default
    ]
)
```

## DOCUMENTATION:

### DeepAgents Framework
- [DeepAgents GitHub Repository](https://github.com/langchain-ai/deepagents)
- [DeepAgents Documentation](https://docs.langchain.com/oss/python/deepagents)
- [SKILLS System Documentation](https://docs.langchain.com/oss/python/deepagents#skills)
- [DeepAgents Changelog](https://github.com/langchain-ai/deepagents/blob/main/CHANGELOG.md)

### LangChain Core
- [LangChain Documentation](https://python.langchain.com/)
- [LangChain Agents Reference](https://reference.langchain.com/python/langchain/agents/)
- [Middleware Documentation](https://docs.langchain.com/oss/python/langchain/agents#middleware)

### Ollama Integration
- [Ollama Documentation](https://ollama.ai/docs)
- [Ollama Model Library](https://ollama.com/library)
- [langchain-ollama Package](https://python.langchain.com/docs/integrations/chat/ollama/)

### MCP & NetBox
- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [NetBox API Documentation](https://docs.netbox.dev/en/stable/rest-api/)
- [NetBox MCP Server](https://github.com/modelcontextprotocol/servers/tree/main/src/netbox)

### Internal Documentation
- `CLAUDE.md` - Project context and development guidelines
- `docs/architecture.md` - System design decisions
- `docs/mcp-constraints.md` - Detailed filter limitations
- `docs/ollama-models.md` - Model comparison results
- `skills/README.md` - Skills development guide

## OTHER CONSIDERATIONS:

### 1. Version Compatibility Issues
**Problem**: DeepAgents 0.0.5 (local) vs 0.3.12 (latest) - 8 versions behind
**Solution**: Ensure installation of DeepAgents 0.3.12+ to access SKILLS system

### 2. Ollama Model Context Window Limits
**Problem**: Some Ollama models have small context windows leading to truncation
**Solution**:
- Use SummarizationMiddleware (included by default in DeepAgents)
- Configure appropriate `num_ctx` in model options (8192 recommended)
- Target 60-70% token reduction through SKILLS

### 3. Tool Binding with init_chat_model
**Problem**: NotImplementedError with some Ollama models when using init_chat_model
**Solution**: Use ChatOllama directly instead of init_chat_model wrapper

### 4. Slow Response Times with Large Models
**Problem**: deepseek-r1:70b can take 10+ seconds per query
**Solution**:
- Use qwen2.5:32b for development/testing
- Reserve larger models for production where accuracy is critical
- Implement streaming responses for real-time feedback

### 5. MCP Filter Error Recovery
**Gotcha**: AI assistants often attempt multi-hop filters despite documentation warnings
**Solution**:
- Implement FilterErrorRecoveryMiddleware to catch and retry with corrected approach
- Use SKILLS system to provide just-in-time guidance when filter errors occur
- Validate filter patterns before MCP tool execution

### 6. Success Metrics & Testing
**Target Performance**:
- Query Success Rate: 71.4% (baseline) → 85% (target) → 95% (stretch)
- Filter Errors: 28.6% → <10% (target) → <5% (stretch)
- Token Usage: High → -60% (target) → -70% (stretch)
- Response Time: Variable → <5s (target) → <3s (stretch)

**Test with Failed Queries**:
- "Show cables connected to device dmi01-nashua-pdu01" (termination_a__device_id error)
- "Show all Dunder-Mifflin sites with device counts" (name__icontains error)

### 7. Security & Privacy Considerations
**Benefits of Local Models**:
- Zero API costs - all inference is local
- Complete privacy - data never leaves your infrastructure
- No rate limits - process unlimited queries
- Compliance ready - meets data residency requirements

**Security Best Practices**:
- Validate NETBOX_TOKEN environment variable
- Never log sensitive data (tokens, credentials)
- Use `.env` for configuration management

### 8. Development Workflow
**Recommended Approach**:
1. Start with test-driven development using failed queries
2. Implement SKILLS for NetBox MCP constraints first
3. Add FilterErrorRecoveryMiddleware for automatic retry
4. Test with multiple Ollama models (qwen2.5:32b, deepseek-r1:70b)
5. Verify filter constraint compliance in all queries
6. Monitor success rates and token usage metrics

### 9. Definition of Done
A feature is complete when:
- [ ] All tests pass (unit, integration, e2e)
- [ ] Documentation is updated
- [ ] Code follows project conventions
- [ ] Filter constraints are validated
- [ ] Success rate meets or exceeds target (85%+)
- [ ] Changes are logged in CHANGELOG.md
- [ ] Code review completed
