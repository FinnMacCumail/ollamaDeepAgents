# DeepSeek's cloud frontier model matches Claude on NetBox queries — moving to LangChain's evaluation tools next (LangChain Post)

**Date:** 2026-06-03
**Channel:** LangChain community (LinkedIn / Slack / X)
**Status:** Draft
**Audience:** Tech-savvy readers familiar with agentic workflows and MCP servers, not necessarily the specifics of LangChain's product suite
**Length:** ~3000 chars (single post)
**Related drafts:** `2026-05-28_six-weeks-later.md` (longer narrative version)

---

**A locally-orchestrated agent running DeepSeek's frontier cloud model now matches Anthropic's Claude on NetBox infrastructure queries. Moving to LangChain's evaluation tooling for the next phase.**

Spent the last six weeks building a NetBox query agent on a LangChain-based agent harness, hooked up to NetBox via an MCP server, with DeepSeek's v4-pro model behind it (~$20/month subscription, runs in the cloud). Comparing the result against a parallel Anthropic Claude reference app running over the same MCP server.

After running a number of NetBox test queries through both stacks, the results came out roughly even — sometimes faster than Claude, sometimes slower, with answer quality consistently in the same ballpark.

| Query type | Claude (Anthropic) | DeepSeek (Ollama Cloud) |
|---|---|---|
| Device detail lookup | 36.2s | **29.5s** |
| Cross-relationship multi-step | 38.7s | 70.6s |

One useful calibration finding worth flagging for anyone running similar dual-stack benchmarks: Anthropic's web UI "new conversation" button doesn't actually reset the backend agent's context. Each "fresh" query was carrying 180-200K input tokens of accumulated history from prior conversations. The apparent Anthropic latency advantage was less clean than surface numbers suggested.

Most of the six weeks went into framework plumbing rather than model selection. A handful of architecture flaws were hiding bugs that don't show up in any model-level evaluation — skills the agent was supposed to load were silently being skipped because of a small frontmatter inconsistency; an example in the framework's own documentation referenced a tool argument name that didn't match the actual tool schema, so the skill body never reached the model at all; a custom-built middleware was head-truncating tool results and eating most of what skill content did get loaded; a local filter validator was actively rejecting query forms that the upstream MCP server perfectly well allowed. Worth its own writeup.

**Next phase: systematic evaluation across a matrix of models, using LangChain's evaluation suite.**

The homegrown "fetch traces, eyeball JSON, write a comparison report" loop has hit its ceiling. Plan:

- A proper benchmark dataset of NetBox queries, run through a matrix of models — frontier cloud (DeepSeek v4-pro, gpt-oss 120b, Qwen3-Coder 480b), smaller cloud variants, local Ollama models (Qwen3 14b, Qwen2.5 32b), with Claude as occasional reference. Same skill content, same MCP, same validator across all variants. The comparison surface becomes "capability and cost per query class" rather than "framework A vs framework B."
- Automated scoring via LangChain's evaluation tooling — LLM-as-judge for correctness, code-based checks for specific structural requirements, pairwise scoring for direct A-vs-B comparisons. Leaderboard view instead of N separate hand-written reports.
- Upgrading to the latest version of the agent harness — among other things it fixes the framework bug that ate two weeks of debugging earlier in this arc, and ships a built-in code interpreter for chaining tool calls more efficiently.
- A shared, versioned store for the NetBox-specific instructions the agent uses — eliminates drift between matrix runs and between repos when both stacks need to read the same skill content.
- LangChain's recently-released agent for auto-clustering recurring failure patterns across traces, feeding regression entries back into the eval dataset.

The whole arc has been a slow shift from "is my custom code correct?" to "is the model picking the right path?" — and LangChain's evaluation suite is exactly what makes the latter quantifiable at scale.

`#langchain #ai #agents #netbox #evaluation`
