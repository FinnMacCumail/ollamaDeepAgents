# How-to Guides

In-depth guides for specific tasks and features.

## Available Guides

### [LangSmith Tracing Guide](langsmith-tracing.md)
Complete guide to using LangSmith for observability and debugging:
- What gets traced
- Privacy considerations
- Analyzing traces
- Common patterns
- Troubleshooting

**When to use:** Understanding agent behavior, debugging issues, optimizing performance

### [LangSmith Skills Assessment](langsmith-skills-assessment.md)
Detailed assessment of LangSmith Skills capabilities:
- Three skills: trace, dataset, evaluator
- How they help with development
- Comparison to manual workflows
- Integration with Claude Code
- Use cases and examples

**When to use:** Deciding whether to install LangSmith Skills, understanding their value

### Model-Matrix Evaluation Harness (`tests/eval/`)

The primary quality gate — replaces the old "fetch trace, eyeball JSON, write a markdown report"
loop with automated scoring on a fixed dataset.

```bash
# Score the default model set against netbox-benchmark-v2
./venv/bin/python -m tests.eval.run_matrix

# Score specific models
EVAL_MODELS="ollama:deepseek-v4-flash:cloud,ollama:glm-5:cloud" \
  ./venv/bin/python -m tests.eval.run_matrix

# Regression check after an agent change (bypass skip-completed)
EVAL_FORCE_RERUN=1 EVAL_MODELS="ollama:deepseek-v4-flash:cloud" \
  ./venv/bin/python -m tests.eval.run_matrix
```

Components: `dataset.py` (the `netbox-benchmark-v2` queries + ground-truth entities),
`evaluators.py` (`entity_coverage`, `completeness_judge`, `tool_call_efficiency`),
`run_matrix.py` (per-model runner with skip-completed + fail-fast-on-429). Results land as
LangSmith experiments; compare them in the LangSmith UI. Background:
`docs/development/2026-06-03_langsmith-evaluation-research.md`.

**When to use:** After any framework, middleware, skill, prompt, or validator change — confirm
quality holds vs the baseline before merging.

## Common Tasks

### Analyzing Performance

1. Enable LangSmith tracing (see [Setup](../setup/langsmith.md))
2. Run your query
3. In a Claude Code session opened in this repo, invoke the `trace-analysis` skill
   (lives at `.claude/skills/trace-analysis/`) to analyse the resulting trace
4. Compare traces in [traces/](../traces/)

### Debugging Failed Queries

1. Check [MCP Constraints](../reference/mcp-constraints.md) for filter limitations
2. Review the error message for filter patterns
3. The `netbox-mcp-filters` skill provides automatic recovery
4. Use two-step query pattern if needed

### Optimizing Token Usage

1. Enable metrics tracking in the agent
2. Review token usage in LangSmith traces
3. Consider using smaller models for simple queries
4. Leverage prompt caching (automatic in llama.cpp)

### Comparing Backends / Models

1. Configure the backend(s) (see [Setup](../setup/README.md))
2. Run the eval harness across the models you want to compare
   (`EVAL_MODELS="ollama:model-a,ollama:model-b" ./venv/bin/python -m tests.eval.run_matrix`)
3. Compare the resulting experiments in the LangSmith UI (leaderboard view)
4. See [Model Compatibility](../reference/model-compatibility.md) for the validator allow-list

## Advanced Topics

### Custom Skills

Create custom skills in `src/skills/`:
1. Create a directory with `SKILL.md`
2. Add YAML frontmatter with metadata
3. Write detailed instructions and examples
4. Test with relevant queries

See `src/skills/README.md` for details.

### Middleware Customization

Add custom middleware for specific needs:
```python
class CustomMiddleware:
    async def __call__(self, state, next_fn):
        # Pre-processing
        result = await next_fn(state)
        # Post-processing
        return result

agent = create_deep_agent(
    middleware=[CustomMiddleware(), ...],
    ...
)
```

### Performance Tuning

Optimize for your use case:
- Model selection (see [Model Compatibility](../reference/model-compatibility.md))
- GPU configuration
- Prompt caching strategies
- Batch query optimization

## Contributing Guides

When adding new guides:
1. Focus on a specific task or feature
2. Include working examples
3. Link to relevant reference docs
4. Add troubleshooting section
5. Update this README

## Getting Help

- Check [Development Notes](../development/) for similar issues
- Review [Trace Analysis](../traces/) for performance patterns
- See [Reference](../reference/) for technical details

---

**Last Updated:** 2026-06-22
