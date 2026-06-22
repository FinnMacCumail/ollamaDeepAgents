# System Architecture

## Overview

The NetBox DeepAgents Query System is built on a modular architecture that combines local LLM inference, intelligent error recovery, and progressive knowledge disclosure to overcome MCP filter constraints.

```
┌─────────────────────────────────────────────────────────┐
│                      User Interface                      │
│                    (CLI / Python API)                    │
└─────────────────┬───────────────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────────────┐
│                   NetBox DeepAgent                      │
│  ┌─────────────────────────────────────────────────┐   │
│  │              DeepAgents Framework               │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────────┐   │   │
│  │  │  Skills  │ │Middleware│ │    Tools      │   │   │
│  │  │  System  │ │  Stack   │ │   Wrapper     │   │   │
│  │  └──────────┘ └──────────┘ └──────────────┘   │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────┬───────────────────────────────────────┘
                  │
        ┌─────────┴─────────┬──────────────────┐
        │                   │                  │
┌───────▼────────┐ ┌────────▼────────┐ ┌──────▼──────┐
│  Ollama Model  │ │   MCP Client    │ │   NetBox    │
│  (Local LLM)   │ │  (Tool Bridge)  │ │   Server    │
└────────────────┘ └─────────────────┘ └─────────────┘
```

## Core Components

### 1. NetBox DeepAgent

The main orchestrator that coordinates all components:

- **Initialization**: Sets up connections to Ollama, MCP, and loads skills
- **Query Processing**: Handles user queries with streaming support
- **Error Recovery**: Automatically recovers from filter failures
- **Metrics Tracking**: Monitors performance and success rates

### 2. DeepAgents Framework

Provides the intelligent agent capabilities:

- **Planning**: Breaks complex queries into steps
- **Tool Calling**: Executes NetBox operations via MCP
- **Context Management**: Handles conversation history
- **Middleware System**: Extensible processing pipeline

### 3. Ollama Integration

Local LLM inference for privacy and control:

- **Model Management**: Supports multiple models with fallback
- **Context Window**: 8192 tokens with optimization
- **Temperature Control**: Deterministic (0.0) for consistency
- **Streaming**: Real-time response generation

### 4. Skills System

Progressive disclosure of domain knowledge:

```
skills/
└── netbox-mcp-filters/
    ├── SKILL.md        # Filter constraints and patterns
    └── examples.md     # Concrete working examples
```

**Loading Strategy:**
1. Only frontmatter loaded at startup (minimal tokens)
2. Full content loaded when skill triggered
3. Provides targeted guidance for specific patterns

### 5. Middleware Stack

Processing pipeline for requests and responses:

1. **FilterErrorRecoveryMiddleware**
   - Catches MCP filter errors
   - Generates recovery strategies
   - Implements two-step queries

2. **MetricsMiddleware**
   - Tracks query performance
   - Monitors success rates
   - Records token usage

3. **QueryMetricsMiddleware**
   - Per-query metrics capture

4. **SummarizationMiddleware** (built-in, auto-added)
   - Manages conversation history
   - Offloads old messages
   - Prevents context overflow

> **Removed:** `TokenOptimizationMiddleware` (commit `01df4e9`) — it head-truncated tool
> results and skill bodies to ~4000 chars, silently breaking skill loading. The built-in
> `SummarizationMiddleware` handles real context overflow correctly.

**HarnessProfile (Workaround B, added on the 0.6.10 upgrade)** — registered for the
`ollama` and `openai` providers. Suppresses two pieces of 0.6's default behaviour that
regress quality on negative-finding queries: `base_system_prompt=""` (overrides
`BASE_AGENT_PROMPT`) and `excluded_middleware={"TodoListMiddleware"}`. See
`docs/development/2026-06-14_deepagents-0.6-upgrade.md`.

### 6. MCP Tools

NetBox operations via Model Context Protocol:

```python
Available Tools:
- netbox_get_objects      # List/filter objects
- netbox_get_object_by_id # Get specific object
- netbox_search_objects   # Global search
- netbox_get_changelogs  # Audit logs
```

**Filter Validation:**
- Pre-validates filters before MCP execution
- Suggests alternatives for invalid patterns
- Prevents runtime errors

## Data Flow

### Successful Query Flow

```
User Query
    ↓
Agent Processes Query
    ↓
Skills Consulted (if needed)
    ↓
Tools Called via MCP
    ↓
NetBox Returns Data
    ↓
Response Formatted
    ↓
User Receives Answer
```

### Error Recovery Flow

```
User Query
    ↓
Agent Attempts Query
    ↓
MCP Filter Error!
    ↓
FilterErrorRecoveryMiddleware Catches
    ↓
Analyzes Error Pattern
    ↓
Generates Recovery Strategy
    ↓
Loads Relevant Skill
    ↓
Retries with Two-Step Query
    ↓
Success! Returns Data
```

## Design Decisions

### Why DeepAgents?

- **Planning Capabilities**: Handles complex multi-step queries
- **Middleware Architecture**: Extensible and maintainable
- **Skills System**: Progressive knowledge disclosure
- **Production Ready**: Built-in streaming, persistence, checkpointing

### Why Ollama?

- **Privacy**: Data never leaves infrastructure
- **Cost**: Zero API fees
- **Control**: Choose and tune models
- **Speed**: Local inference with GPU acceleration

### Why Two-Step Queries?

MCP server limitations require workarounds:

```python
# This fails (relationship traversal)
{"device__site_id": 5}

# This works (two steps)
site = get_site(id=5)
devices = get_devices(site_id=site.id)
```

### Why Skills Instead of Prompts?

- **Token Efficiency**: Load only when needed
- **Maintainability**: Organized knowledge modules
- **Scalability**: Add skills without bloating context
- **Testability**: Validate skills independently

## Performance Characteristics

### Token Usage

| Component | Tokens (Approx) | When Loaded |
|-----------|----------------|-------------|
| System Prompt | 300 | Always |
| Skills Metadata | 50 | Always |
| Full Skill | 500 | On trigger |
| Tool Definitions | 200 | Always |
| Conversation | Variable | Managed |

### Measured Performance

Performance is measured empirically by the model-matrix eval harness (`tests/eval/`) against
the fixed `netbox-benchmark-v2` dataset, not estimated. Representative wall times for the default
`deepseek-v4-flash:cloud` (these are model- and load-dependent — re-run the harness for current
figures):

| Query class | Wall time (approx) | Tool calls |
|---|---|---|
| Single-object (e.g. rack elevation) | ~15-35s | 4-6 |
| Device-detail (multi-aspect) | ~15-20s | 5-7 |
| Cross-relationship (VLAN across tenant sites) | ~55-90s | 8-21 |
| Multi-aspect tenant (14-site enumeration) | ~35-50s | 7-11 |

Quality (entity coverage / completeness) for the default model on these queries is ~0.95 / ~1.00.
See `docs/development/2026-06-14_deepagents-0.6-upgrade.md` for the latest baselines and the
LangSmith experiment IDs.

## Security Considerations

### Data Privacy

- **Local Processing**: LLM runs on-premises
- **No External APIs**: Except NetBox itself
- **Token Security**: Never logged or exposed
- **Audit Trail**: All queries logged locally

### Access Control

- NetBox API token required
- Respects NetBox permissions
- Read-only operations by default
- No credential storage in code

## Scalability

### Horizontal Scaling

- Multiple agent instances possible
- Shared Ollama server
- Load balancing via reverse proxy
- Stateless design

### Vertical Scaling

- Larger Ollama models for accuracy
- More GPU memory for speed
- Increased context window
- Parallel query execution

## Monitoring

### Key Metrics

- Query success rate
- Filter error rate
- Recovery success rate
- Average response time
- Token usage per query
- Model performance

### Health Checks

- Ollama connectivity
- MCP server status
- NetBox API availability
- Skill loading success
- Memory usage

## Future Enhancements

### Planned Improvements

1. **Caching Layer**: Reduce redundant queries
2. **Query Optimizer**: Minimize API calls
3. **Web Interface**: Browser-based UI
4. **Bulk Operations**: Efficient batch processing
5. **Custom Skills**: User-defined knowledge

### Research Areas

- Graph-based relationship modeling
- Semantic search with embeddings
- Predictive query completion
- Anomaly detection in results
- Natural language reporting