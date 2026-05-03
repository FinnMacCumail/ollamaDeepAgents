# DeepAgents Skills System

This directory contains skills for the NetBox DeepAgents system. Skills provide progressive disclosure of domain-specific knowledge, allowing the agent to load relevant information just-in-time rather than keeping everything in context.

## What are Skills?

Skills are folders containing a `SKILL.md` file that provides:
- YAML frontmatter with metadata (loaded at startup)
- Markdown content with detailed instructions (loaded on-demand)
- Associated files with examples and additional context

## Benefits

1. **Token Efficiency**: Only loads full content when needed
2. **Progressive Disclosure**: Agent discovers capabilities as required
3. **Maintainability**: Knowledge organized in modular units
4. **Scalability**: Can add many skills without context bloat

## Current Skills

### netbox-mcp-filters
**Priority**: High
**Trigger**: NetBox queries with filtering
**Purpose**: Provides critical knowledge about MCP filter constraints and workarounds

This skill helps the agent:
- Avoid filter patterns that will fail
- Use two-step queries for relationships
- Choose between filters and search appropriately
- Recover from filter errors gracefully

## Creating New Skills

To add a new skill:

1. Create a folder under `src/skills/` with a descriptive name
2. Add a `SKILL.md` file with proper frontmatter:

```markdown
---
title: Your Skill Title
description: Brief description of what this skill provides
version: 1.0.0
tags: [relevant, tags, here]
priority: high|medium|low
trigger: when this skill should be activated
---

# Skill Content

Detailed instructions and knowledge here...
```

3. Optionally add supporting files (examples.md, patterns.json, etc.)

## Skill Guidelines

### Structure
- **Frontmatter**: Keep concise (< 10 lines)
- **Content**: Keep under 500 lines for efficiency
- **Examples**: Use concrete, working examples
- **Decisions**: Provide clear decision trees

### Best Practices
1. **Be Specific**: Clear, actionable instructions
2. **Show Don't Tell**: Include working code examples
3. **Highlight Critical Info**: Use formatting to emphasize important points
4. **Provide Alternatives**: Show multiple approaches when applicable
5. **Include Anti-Patterns**: Show what NOT to do

### Priority Levels
- **High**: Critical for core functionality (e.g., filter constraints)
- **Medium**: Important but not essential (e.g., optimization tips)
- **Low**: Nice-to-have knowledge (e.g., advanced features)

## How Skills are Loaded

1. **Startup**: Only YAML frontmatter is loaded
2. **Trigger Detection**: Agent identifies when a skill might be relevant
3. **Just-in-Time Loading**: Full SKILL.md content loaded when needed
4. **Context Integration**: Skill knowledge applied to current task
5. **Reference Caching**: Recently used skills may be kept in context

## Testing Skills

To test a skill:

1. Create queries that should trigger the skill
2. Verify the agent loads the skill appropriately
3. Check that the skill's guidance is followed
4. Measure impact on success rate and token usage

Example test:
```python
# This query should trigger the netbox-mcp-filters skill
query = "Show cables connected to device router01"

# Agent should:
# 1. Detect filter constraint issue
# 2. Load netbox-mcp-filters skill
# 3. Apply two-step query pattern
# 4. Successfully retrieve cables
```

## Monitoring Skill Usage

The system logs when skills are loaded:
- Which skills are triggered
- How often each skill is used
- Impact on query success rate
- Token usage with/without skills

This helps identify:
- Most valuable skills
- Skills that need improvement
- Opportunities for new skills

## Future Skills

Potential skills to add:
- `netbox-optimization`: Query performance optimization
- `netbox-bulk-operations`: Handling large datasets efficiently
- `error-recovery-advanced`: Complex error scenarios
- `netbox-relationships`: Understanding NetBox data relationships
- `query-composition`: Building complex multi-step queries

## Contributing

When contributing new skills:
1. Follow the structure guidelines above
2. Test with real queries
3. Document trigger conditions clearly
4. Measure impact on success metrics
5. Update this README with skill details