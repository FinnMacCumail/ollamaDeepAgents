# PRPs — Product Requirement Prompts (harvested methodology)

Harvested 2026-06-22 from the ancestor repo **FinnMacCumail/deepagents**.

A **PRP (Product Requirement Prompt)** is a context-rich planning/spec document written *for an
AI agent to implement a feature*, with embedded validation loops. The format (see
`templates/prp_base.md`) is: Goal → Why → What → Success Criteria → All-Needed-Context (docs,
files, gotchas) → Implementation Blueprint (tasks + pseudocode) → Validation Loop (lint, tests,
integration) → Anti-Patterns.

The companion slash commands live in `.claude/commands/`:
- `generate-prp.md` — research a feature and produce a PRP from the template.
- `execute-prp.md` — implement a PRP and run its validation loop.

This is a reusable planning workflow kept for methodology. The dated decision records under
`docs/development/` are this project's actual planning trail; PRPs are an alternative,
more-structured format for larger features.
