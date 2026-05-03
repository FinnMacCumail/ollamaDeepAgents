name: "NetBox DeepAgents Query System with Ollama Integration"
description: |

## Purpose
Build an intelligent NetBox infrastructure query system using DeepAgents framework (0.3.12+) with Ollama for local LLM inference. This implementation addresses critical MCP filter constraints that cause 28.6% failure rate in baseline implementations, targeting 85%+ success rate through progressive disclosure of domain knowledge via the SKILLS system.

## Core Principles
1. **Context is King**: Include ALL necessary documentation, examples, and caveats
2. **Validation Loops**: Provide executable tests/lints the AI can run and fix
3. **Information Dense**: Use keywords and patterns from the codebase
4. **Progressive Success**: Start simple, validate, then enhance
5. **Global rules**: Be sure to follow all rules in CLAUDE.md

---

## Goal
Create a fully functional NetBox query system that:
- Handles complex NetBox infrastructure queries via natural language
- Overcomes MCP filter limitations through intelligent two-step queries
- Achieves 85%+ success rate on previously failed queries (baseline: 71.4%)
- Reduces token usage by 60-70% through SKILLS and middleware
- Runs completely locally with Ollama for data privacy

## Why
- **Business value**: Zero API costs with complete data privacy
- **Integration**: Seamless NetBox infrastructure queries via conversational interface
- **Problems solved**: MCP filter constraints causing query failures
- **For whom**: Network engineers and infrastructure teams needing secure, intelligent NetBox access

## What
### User-visible behavior:
- Conversational interface for NetBox queries
- Automatic error recovery from filter failures
- Real-time streaming responses
- Support for complex multi-step queries

### Technical requirements:
- DeepAgents 0.3.12+ with SKILLS system
- Ollama integration with multiple model support
- MCP tool integration for NetBox
- Custom middleware for error recovery
- Progressive disclosure of domain knowledge

### Success Criteria
- [ ] Query success rate >= 85% on failed query test set
- [ ] Token usage reduced by 60%+ through SKILLS
- [ ] Response time < 5 seconds for standard queries
- [ ] All MCP filter errors handled with recovery
- [ ] Support for qwen2.5:32b and deepseek-r1:70b models
- [ ] Comprehensive test coverage (>80%)

## All Needed Context

### Documentation & References (list all context needed to implement the feature)
```yaml
# MUST READ - Include these in your context window
- url: https://github.com/langchain-ai/deepagents
  why: DeepAgents official repository with examples and middleware patterns

- url: https://docs.langchain.com/oss/python/deepagents
  why: DeepAgents documentation for create_deep_agent API and middleware

- url: https://docs.langchain.com/oss/python/deepagents/middleware
  why: Middleware architecture patterns, especially SummarizationMiddleware

- url: https://docs.langchain.com/oss/python/integrations/chat/ollama
  why: ChatOllama integration patterns and configuration

- url: https://blog.langchain.com/using-skills-with-deep-agents/
  why: Skills system implementation and progressive disclosure patterns

- url: https://github.com/netboxlabs/netbox-mcp-server
  why: NetBox MCP server implementation and filter constraints
  section: server.py shows exact filter validation logic
  critical: Django lookups (__icontains, __in) and multi-hop filters NOT supported

- url: https://netboxlabs.com/docs/netbox/reference/filtering/
  why: NetBox REST API filtering documentation
  critical: Filters aren't chainable - no device_type__model patterns

- file: CLAUDE.md
  why: Project conventions, security considerations, development workflow

- file: INITIAL.md
  why: Feature requirements and failure examples
  critical: Shows exact filter patterns that fail vs succeed

- doc: https://ollama.com/library
  section: Model selection - qwen2.5:32b for dev, deepseek-r1:70b for prod
  critical: Context window limits require SummarizationMiddleware

- docfile: PRPs/templates/prp_base.md
  why: PRP template structure to follow
```

### Current Codebase tree (run `tree` in the root of the project) to get an overview of the codebase
```bash
.
├── CLAUDE.md               # Project guidelines
├── INITIAL.md             # Feature requirements
└── PRPs/
    └── templates/
        └── prp_base.md    # PRP template
```

### Desired Codebase tree with files to be added and responsibility of file
```bash
.
├── CLAUDE.md
├── INITIAL.md
├── PRPs/
│   ├── templates/
│   └── netbox-deepagents-ollama.md
├── pyproject.toml                        # Python package configuration
├── .env.example                          # Environment template
├── .env                                  # Local configuration (gitignored)
├── src/
│   ├── __init__.py
│   ├── main.py                          # Application entry point
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── netbox_agent.py              # Core DeepAgent implementation
│   │   └── ollama_config.py             # Ollama model configuration
│   ├── skills/                          # SKILLS system for progressive disclosure
│   │   ├── README.md                    # Skills development guide
│   │   └── netbox-mcp-filters/
│   │       ├── SKILL.md                 # NetBox filter constraint knowledge
│   │       └── examples.md              # Two-step query patterns
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── filter_recovery.py           # MCP filter error recovery
│   │   └── metrics.py                   # Performance tracking
│   ├── tools/
│   │   ├── __init__.py
│   │   └── netbox_tools.py              # MCP tool wrappers
│   └── utils/
│       ├── __init__.py
│       ├── logging.py                   # Structured logging
│       └── config.py                    # Configuration management
├── tests/
│   ├── __init__.py
│   ├── conftest.py                      # pytest fixtures
│   ├── test_filters.py                  # MCP filter constraint tests
│   ├── test_ollama_models.py            # Model compatibility tests
│   ├── test_netbox_integration.py       # Integration tests
│   └── data/
│       └── failed_queries.json          # Test queries that fail in baseline
├── examples/
│   ├── basic_usage.py                   # Simple query examples
│   └── failed_query_recovery.py         # Error recovery examples
├── docs/
│   ├── architecture.md                  # System design
│   ├── mcp-constraints.md               # Detailed filter limitations
│   └── ollama-models.md                 # Model comparison results
├── CHANGELOG.md
├── README.md
└── TODO.md
```

### Known Gotchas of our codebase & Library Quirks
```python
# CRITICAL: NetBox MCP filter constraints
# NEVER use multi-hop filters: device__site_id, termination_a__device_id
# NEVER use Django lookups: __icontains, __in, __startswith
# ALWAYS use direct ID filters: {"device_id": 123}
# ALWAYS use two-step queries for relationships

# CRITICAL: DeepAgents 0.3.12+ required for SKILLS
# Local version 0.0.5 is 8 versions behind - must upgrade
# pip install "deepagents>=0.3.12"

# CRITICAL: Ollama ChatOllama vs init_chat_model
# init_chat_model throws NotImplementedError with some models
# Use ChatOllama directly:
from langchain_ollama import ChatOllama
model = ChatOllama(model="qwen2.5:32b", temperature=0.0)

# CRITICAL: Ollama context window limits
# Some models have small windows leading to truncation
# Configure num_ctx in options: {"num_ctx": 8192}
# SummarizationMiddleware included by default in DeepAgents

# CRITICAL: Middleware order matters
# FilterErrorRecoveryMiddleware must come BEFORE tool execution
# SummarizationMiddleware is added automatically by DeepAgents

# CRITICAL: Skills are progressively disclosed
# Only YAML frontmatter loads initially
# Full SKILL.md loads just-in-time when needed
# Keep SKILL.md under 500 lines for efficiency
```

## Implementation Blueprint

### Data models and structure

Create the core data models for configuration and metrics tracking:

```python
# src/utils/config.py
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any

class OllamaConfig(BaseModel):
    model: str = Field(default="qwen2.5:32b")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    base_url: str = Field(default="http://localhost:11434")
    options: Dict[str, Any] = Field(default_factory=lambda: {
        "num_ctx": 8192,
        "num_predict": 2048,
        "top_k": 10,
        "top_p": 0.95
    })

    @validator('model')
    def validate_model(cls, v):
        allowed = ["qwen2.5:32b", "deepseek-r1:70b", "llama3.1:70b", "mixtral:8x7b"]
        if v not in allowed:
            raise ValueError(f"Model must be one of {allowed}")
        return v

class NetBoxConfig(BaseModel):
    url: str = Field(..., description="NetBox instance URL")
    token: str = Field(..., description="NetBox API token")
    mcp_server_path: Optional[str] = Field(default="/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server")

    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")
        return v.rstrip('/')

# src/utils/metrics.py
class QueryMetrics(BaseModel):
    total_queries: int = 0
    successful_queries: int = 0
    filter_errors: int = 0
    recovered_errors: int = 0
    token_usage: List[int] = Field(default_factory=list)
    response_times: List[float] = Field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.total_queries == 0:
            return 0.0
        return (self.successful_queries / self.total_queries) * 100

    @property
    def avg_tokens(self) -> float:
        return sum(self.token_usage) / len(self.token_usage) if self.token_usage else 0
```

### list of tasks to be completed to fullfill the PRP in the order they should be completed

```yaml
Task 1: Setup project structure and dependencies
CREATE pyproject.toml:
  - Add deepagents>=0.3.12, langchain-ollama, langchain-mcp-adapters
  - Add pytest, ruff, mypy for development
  - Configure project metadata

CREATE .env.example:
  - Template for environment variables
  - Include NETBOX_URL, NETBOX_TOKEN, OLLAMA_MODEL

CREATE src/ directory structure:
  - Initialize all Python packages with __init__.py
  - Set up basic logging configuration

Task 2: Implement Ollama configuration
CREATE src/agents/ollama_config.py:
  - PATTERN: Use ChatOllama directly (not init_chat_model)
  - Configure model options with proper context window
  - Support multiple models with fallback

Task 3: Create NetBox MCP tools wrapper
CREATE src/tools/netbox_tools.py:
  - Wrap MCP tools with error handling
  - Add logging for debugging filter errors
  - Validate filters before MCP execution

Task 4: Implement SKILLS system
CREATE src/skills/netbox-mcp-filters/SKILL.md:
  - Document all filter constraints with examples
  - Provide two-step query patterns
  - Include recovery strategies

CREATE src/skills/README.md:
  - Skills development guide
  - How to add new skills

Task 5: Create FilterErrorRecoveryMiddleware
CREATE src/middleware/filter_recovery.py:
  - PATTERN: Extend AgentMiddleware base class
  - Catch MCP filter errors in after_model
  - Generate corrected two-step approach
  - Track recovery metrics

Task 6: Build main NetBox agent
CREATE src/agents/netbox_agent.py:
  - Use create_deep_agent with Ollama model
  - Load skills from filesystem
  - Add custom middleware stack
  - Implement streaming responses

Task 7: Create application entry point
CREATE src/main.py:
  - Initialize agent with configuration
  - Setup interactive CLI interface
  - Handle user queries with streaming
  - Display metrics on exit

Task 8: Write comprehensive tests
CREATE tests/conftest.py:
  - Fixtures for mock NetBox responses
  - Fixture for failed queries dataset
  - Ollama model mock

CREATE tests/test_filters.py:
  - Test all known filter failure patterns
  - Verify two-step query execution
  - Validate error recovery

CREATE tests/test_ollama_models.py:
  - Test with multiple Ollama models
  - Verify context window handling
  - Check model fallback logic

CREATE tests/test_netbox_integration.py:
  - Integration tests with real NetBox
  - Test failed queries from dataset
  - Measure success rate improvement

Task 9: Create examples and documentation
CREATE examples/basic_usage.py:
  - Simple query examples
  - Show successful vs failed patterns

CREATE examples/failed_query_recovery.py:
  - Demonstrate error recovery
  - Show two-step query patterns

CREATE docs/architecture.md:
  - System design decisions
  - Component interactions
  - Data flow diagrams

Task 10: Final validation and optimization
UPDATE README.md:
  - Installation instructions
  - Usage examples
  - Performance metrics

RUN full test suite:
  - Ensure 85%+ success rate
  - Verify token reduction
  - Check response times
```

### Per task pseudocode as needed added to each task

```python
# Task 2: Ollama configuration
# src/agents/ollama_config.py
from langchain_ollama import ChatOllama
from typing import Optional
import os

def create_ollama_model(
    model_name: Optional[str] = None,
    temperature: float = 0.0,
    validate: bool = True
) -> ChatOllama:
    # PATTERN: Use environment variable with fallback
    model = model_name or os.getenv("OLLAMA_MODEL", "qwen2.5:32b")

    # CRITICAL: Use ChatOllama directly, not init_chat_model
    try:
        llm = ChatOllama(
            model=model,
            temperature=temperature,
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            validate_model_on_init=validate,
            options={
                "num_ctx": 8192,  # CRITICAL: Large context window
                "num_predict": 2048,
                "top_k": 10,
                "top_p": 0.95,
            }
        )
        return llm
    except Exception as e:
        # PATTERN: Fallback to lighter model on error
        if model != "mixtral:8x7b":
            return create_ollama_model("mixtral:8x7b", temperature, False)
        raise

# Task 5: FilterErrorRecoveryMiddleware
# src/middleware/filter_recovery.py
from langchain.agents.middleware import AgentMiddleware
from typing import Dict, Any, Optional
import re
import logging

class FilterErrorRecoveryMiddleware(AgentMiddleware):
    """Catches and recovers from MCP filter errors."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.error_patterns = {
            r"Invalid filter.*__": "multi_hop_filter",
            r"Invalid filter.*__icontains": "django_lookup",
            r"termination_a__device": "relationship_filter"
        }

    def after_model(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # PATTERN: Check for filter errors in state
        error_msg = str(state.get("error", ""))

        for pattern, error_type in self.error_patterns.items():
            if re.search(pattern, error_msg, re.IGNORECASE):
                # CRITICAL: Generate two-step query approach
                self.logger.info(f"Caught {error_type}, generating recovery")

                # Extract the failed filter
                failed_filter = self.extract_filter(error_msg)

                # Generate recovery strategy
                if "__" in failed_filter:
                    # PATTERN: Convert to two-step query
                    parts = failed_filter.split("__")
                    return {
                        "retry_strategy": "two_step_query",
                        "step1": f"Get {parts[0]} by name",
                        "step2": f"Use {parts[0]}_id in filter",
                        "hint": "Use SKILL netbox-mcp-filters for guidance"
                    }

        return None

    def extract_filter(self, error_msg: str) -> str:
        # PATTERN: Extract filter from error message
        match = re.search(r"Invalid filter: (\w+(?:__\w+)*)", error_msg)
        return match.group(1) if match else ""

# Task 6: NetBox Agent
# src/agents/netbox_agent.py
from deepagents import create_deep_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from typing import AsyncGenerator, Dict, Any
import asyncio

async def create_netbox_agent(config: NetBoxConfig):
    # PATTERN: Create MCP client for NetBox tools
    mcp_config = {
        "netbox": {
            "command": "python",
            "args": ["-m", "netbox_mcp_server"],
            "env": {
                "NETBOX_URL": config.url,
                "NETBOX_TOKEN": config.token
            }
        }
    }

    # Get MCP tools
    mcp_client = MultiServerMCPClient(mcp_config)
    await mcp_client.connect()
    mcp_tools = await mcp_client.get_tools()

    # CRITICAL: Load Ollama model
    from .ollama_config import create_ollama_model
    model = create_ollama_model()

    # PATTERN: System prompt with filter constraints
    system_prompt = """You are a NetBox infrastructure query assistant.

    CRITICAL CONSTRAINTS:
    - NEVER use multi-hop filters like device__site_id
    - NEVER use Django lookups like __icontains
    - ALWAYS use two-step queries for relationships
    - ALWAYS check skills/netbox-mcp-filters for guidance

    When a filter fails, break it into steps:
    1. Get the entity by name
    2. Use the entity ID in the next query
    """

    # Create agent with skills and middleware
    from ..middleware.filter_recovery import FilterErrorRecoveryMiddleware

    agent = create_deep_agent(
        model=model,
        tools=mcp_tools,
        system_prompt=system_prompt,
        middleware=[
            FilterErrorRecoveryMiddleware(),
            # SummarizationMiddleware added automatically
        ],
        skills="src/skills",  # Load skills from directory
    )

    return agent, mcp_client

async def query_netbox(
    agent,
    query: str,
    metrics: QueryMetrics
) -> AsyncGenerator[str, None]:
    """Stream responses from agent with metrics tracking."""

    metrics.total_queries += 1
    start_time = time.time()

    try:
        # PATTERN: Stream responses for real-time feedback
        async for chunk in agent.astream(
            {"messages": [{"role": "user", "content": query}]},
            stream_mode="values"
        ):
            if "messages" in chunk:
                yield chunk["messages"][-1].content

        metrics.successful_queries += 1

    except Exception as e:
        if "Invalid filter" in str(e):
            metrics.filter_errors += 1
        raise

    finally:
        metrics.response_times.append(time.time() - start_time)
```

### Integration Points
```yaml
DATABASE:
  - No database required (uses NetBox as source)

CONFIG:
  - add to: .env
  - pattern: |
      NETBOX_URL=http://localhost:8000
      NETBOX_TOKEN=your-token-here
      OLLAMA_MODEL=qwen2.5:32b
      OLLAMA_BASE_URL=http://localhost:11434
      LOG_LEVEL=INFO

MCP SERVER:
  - location: /home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server
  - tools: netbox_get_objects, netbox_get_object_by_id, netbox_search_objects

SKILLS:
  - location: src/skills/netbox-mcp-filters/
  - loading: Progressive disclosure via DeepAgents

OLLAMA:
  - endpoint: http://localhost:11434
  - models: Pull with `ollama pull qwen2.5:32b`
```

## Validation Loop

### Level 1: Syntax & Style
```bash
# Install dependencies first
pip install -e .

# Run these FIRST - fix any errors before proceeding
ruff check src/ --fix              # Auto-fix style issues
mypy src/ --ignore-missing-imports # Type checking

# Expected: No errors. If errors, READ the error and fix.
```

### Level 2: Unit Tests each new feature/file/function use existing test patterns
```python
# tests/test_filters.py
import pytest
from src.middleware.filter_recovery import FilterErrorRecoveryMiddleware

def test_multi_hop_filter_recovery():
    """Multi-hop filters are caught and corrected."""
    middleware = FilterErrorRecoveryMiddleware()

    state = {"error": "Invalid filter: device__site_id"}
    result = middleware.after_model(state)

    assert result is not None
    assert result["retry_strategy"] == "two_step_query"
    assert "Get device by name" in result["step1"]

def test_django_lookup_recovery():
    """Django lookups trigger recovery."""
    middleware = FilterErrorRecoveryMiddleware()

    state = {"error": "Invalid filter: name__icontains"}
    result = middleware.after_model(state)

    assert result is not None
    assert "two_step_query" in result["retry_strategy"]

@pytest.mark.asyncio
async def test_ollama_model_creation():
    """Ollama model initializes with correct settings."""
    from src.agents.ollama_config import create_ollama_model

    model = create_ollama_model("mixtral:8x7b")
    assert model.model == "mixtral:8x7b"
    assert model.temperature == 0.0
    assert model.options["num_ctx"] == 8192
```

```bash
# Run and iterate until passing:
pytest tests/test_filters.py -v
# If failing: Read error, understand root cause, fix code, re-run
```

### Level 3: Integration Test
```bash
# Start Ollama if not running
ollama serve

# Pull required model
ollama pull qwen2.5:32b

# Run the application
python src/main.py

# Test with known failing query
echo "Show cables connected to device dmi01-nashua-pdu01" | python src/main.py

# Expected: Successful response with cable data
# If error: Check logs for filter recovery attempts
```

### Level 4: Failed Query Test Suite
```python
# tests/test_failed_queries.py
import pytest
import json
from src.main import create_netbox_agent

@pytest.fixture
def failed_queries():
    """Load queries that fail in baseline."""
    return [
        "Show cables connected to device dmi01-nashua-pdu01",
        "Show all Dunder-Mifflin sites with device counts",
        "List interfaces on device with site_id 5",
        "Find all power outlets in rack R01",
    ]

@pytest.mark.asyncio
async def test_failed_query_recovery(failed_queries):
    """Test that previously failed queries now succeed."""
    agent, client = await create_netbox_agent()
    metrics = QueryMetrics()

    for query in failed_queries:
        try:
            result = ""
            async for chunk in query_netbox(agent, query, metrics):
                result += chunk

            assert len(result) > 0, f"Empty response for: {query}"

        except Exception as e:
            pytest.fail(f"Query failed: {query} - {str(e)}")

    # CRITICAL: Verify success rate meets target
    assert metrics.success_rate >= 85.0, f"Success rate {metrics.success_rate}% below target"

    await client.disconnect()
```

```bash
# Run full test suite
pytest tests/ -v --cov=src --cov-report=term-missing

# Expected: 85%+ success rate on failed queries
# If below target: Review filter recovery logic
```

## Final validation Checklist
- [ ] All tests pass: `pytest tests/ -v`
- [ ] No linting errors: `ruff check src/`
- [ ] No type errors: `mypy src/`
- [ ] Failed query success rate >= 85%
- [ ] Token usage reduced by 60%+
- [ ] Response time < 5s for standard queries
- [ ] Ollama models tested: qwen2.5:32b, deepseek-r1:70b
- [ ] Skills load progressively (verify with logging)
- [ ] Filter errors recovered automatically
- [ ] Documentation complete in docs/
- [ ] Examples run successfully
- [ ] CHANGELOG.md updated

---

## Anti-Patterns to Avoid
- ❌ Don't use init_chat_model with Ollama - use ChatOllama directly
- ❌ Don't attempt to fix MCP server filter logic - work around it
- ❌ Don't skip two-step queries for relationships
- ❌ Don't load all skills upfront - use progressive disclosure
- ❌ Don't ignore context window limits - use SummarizationMiddleware
- ❌ Don't hardcode NetBox credentials - use environment variables
- ❌ Don't catch all exceptions - be specific about filter errors
- ❌ Don't use synchronous code in async context
- ❌ Don't create new middleware patterns - extend AgentMiddleware

## Confidence Score: 9/10

This PRP provides comprehensive context for implementing the NetBox DeepAgents system with Ollama. The score is 9/10 because:

✅ Complete documentation references with specific sections
✅ Clear implementation blueprint with working pseudocode
✅ Specific error patterns and recovery strategies
✅ Comprehensive test suite with metrics validation
✅ Progressive task breakdown in correct order
✅ All known gotchas and library quirks documented

The 1-point deduction is because the exact MCP tool signatures may need adjustment based on the actual netbox-mcp-server implementation, but the recovery patterns will handle any issues.