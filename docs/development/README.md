# Development Notes

Development decisions, session summaries, and implementation notes.

## Purpose

This directory contains:
- Development session summaries
- Implementation decisions and rationale
- Bug fixes and their analysis
- Planning documents
- Chronological development history

## Available Documents

### [2026-05-04: Streaming Fix](2026-05-04_streaming-fix.md)
**Problem:** Messy output with 7+ chunks for simple queries
**Solution:** Filter streaming to only yield final AI responses
**Impact:** Clean single-chunk output, 11% faster performance

Key insights:
- `stream_mode="values"` yields all message types
- Filter logic: only AI messages with content, no tool_calls
- Full tracing still preserved in LangSmith

### [2026-02-09: Session Summary](2026-02-09_session-summary.md)
**Problem:** Tool wrapper signature errors, model compatibility
**Solutions:**
- Fixed wrapper to accept positional arguments
- Identified model compatibility issues
- Tested multiple Ollama models

Key insights:
- LangChain invokes tools with positional args
- Some models require specific prompting patterns
- Validation middleware catches filter errors early

### [Initial Planning](initial-planning.md)
Original feature specification and architecture planning:
- Requirements and goals
- DeepAgents framework selection
- Skills system design
- MCP integration approach

## Development Timeline

| Date | Topic | Document |
|------|-------|----------|
| 2026-05-04 | Streaming output fix | [2026-05-04_streaming-fix.md](2026-05-04_streaming-fix.md) |
| 2026-02-09 | Tool wrapper & model testing | [2026-02-09_session-summary.md](2026-02-09_session-summary.md) |
| Initial | Project planning | [initial-planning.md](initial-planning.md) |

## Key Learnings

### Framework Integration

**DeepAgents 0.5.6 vs 0.3.12:**
- Significant improvements in summarization
- Better async support
- More reliable streaming
- Worth upgrading

**llama.cpp vs Ollama:**
- llama.cpp: Better for production (more control)
- Ollama: Easier for development (simpler setup)
- Both work well with OpenAI-compatible API

### Performance Patterns

**Typical Query Flow:**
1. LLM Call 1: Tool selection (~20s)
2. Tool Execution: NetBox MCP (~1-2s)
3. LLM Call 2: Response formatting (~13-20s)

**Optimization Opportunities:**
- Prompt caching saves ~20K tokens per query
- Smaller models for simple queries
- GPU acceleration for faster inference

### Common Issues

**Filter Constraints:**
- Django ORM patterns don't work
- Multi-hop relationships require two-step queries
- Skills system provides automatic recovery

**Streaming:**
- `stream_mode="values"` shows all internal state
- Filter message types before yielding to users
- Preserves full tracing in LangSmith

**Model Selection:**
- 7B models: Fast but lower quality
- 14B models: Best balance
- 32B+ models: Best quality, slower

## Contributing

When adding development notes:

### File Naming
Use format: `YYYY-MM-DD_<topic>.md`

Examples:
- `2026-05-04_streaming-fix.md`
- `2026-05-10_gpu-optimization.md`
- `2026-06-01_new-middleware.md`

### Document Structure
```markdown
# Title: Brief Description

**Date:** YYYY-MM-DD
**Status:** ✅ Completed / 🚧 In Progress / ❌ Failed

## Problem

[Clear description of the issue]

## Investigation

[What was explored and discovered]

## Solution

[What was implemented]

## Impact

[Results and metrics]

## Lessons Learned

[Key takeaways]
```

### What to Document

**Do document:**
- Non-obvious solutions
- Performance improvements
- Bug fixes with analysis
- Architecture decisions
- Failed approaches (what NOT to do)

**Don't document:**
- Routine updates
- Trivial bug fixes
- Changes already in git commits

## Cross-References

Development notes often reference:
- [Trace Analysis](../traces/) - Performance data
- [Reference](../reference/) - Technical specs
- [Guides](../guides/) - Implementation details
- [Setup](../setup/) - Configuration changes

## Archive Policy

Documents are moved to [Archive](../archive/) when:
- No longer relevant to current implementation
- Superseded by newer approaches
- Historical interest only

Currently active documents stay here for easy reference.

---

**Maintained by:** Development team
**Last Updated:** 2026-05-05
