# NetBox AI Assistant — Six Weeks Later (Telegram Post)

**Date:** 2026-06-02
**Channel:** Telegram
**Status:** Draft
**Audience:** Tech / local-AI / network-automation
**Length:** ~5400 chars (intended as two messages; the original 2026-05-05 was posted in two parts too)
**Follow-up to:** `2026-05-05_local-netbox-ai-assistant.md`

---

## POST 1

So that "cloud as a feasibility lab" idea I mentioned at the end of the last post — six weeks in, here's where it landed.

The basic move was a one-line `.env` change: swap local llama.cpp / Qwen3-14B for `deepseek-v4-pro:cloud` via Ollama Cloud ($20/month subscription, 1.6T-parameter MoE, runs on someone else's hardware). Same DeepAgents framework, same NetBox MCP server, same skill files. Just point inference at a frontier-scale model instead.

The hypothesis was simple. If the queries that defeated the 14B work cleanly against a larger model, the architecture is sound and the model was the bottleneck. The question becomes whether the hardware to run something comparable locally is worth the spend.

What I underestimated was how much of the "architecture is sound" part was wishful thinking. Six weeks went into a long string of "the model is wrong" findings that turned out to be "the model never saw the right information in the first place." Skills I'd authored that had never actually loaded — wrong YAML frontmatter field, loader silently skipped them, every "the skill helped here" claim in my own trace reports retroactively turned out to be wrong. A DeepAgents framework bug where the skill-loading example uses the wrong argument name for its own tool, declined for fix upstream, requiring a workaround. My own custom truncation middleware quietly eating the first 4000 characters of any tool result. A local filter validator that had been actively lying to the model about which lookups were allowed. None of this was inference cost or model capability — it was plumbing on my side, hiding for weeks.

That stuff is worth its own post if anyone's curious about the specifics. The short version: a lot of "the model is being unreliable" was actually "the model is being asked to do impossible work on misleading inputs." Same underlying lesson as the anonymization branch from six weeks ago — different failure mode, same warning about understanding the substrate before piling architecture on top of it.

---

## POST 2

What does the comparison against Claude SDK look like now?

Two benchmark queries, fresh-start, run yesterday.

The first: *"for device dmi01-nashua-rtr01, show location details, assigned IP addresses, and tenant ownership."* A device-detail lookup with three aspects that traverse different parts of the schema. Claude SDK on Anthropic's hosted infrastructure: **36 seconds**. Our deepseek-v4-pro:cloud build: **29.5 seconds**. We won.

The second: *"show where VLAN 100 is deployed across Jimbob's Banking sites, including devices using this VLAN and IP allocations."* Multi-step, cross-relationship — tenant → sites → VLANs → prefixes. Claude SDK: **38.7s**. Our build: **70.6s**. SDK won.

So one each. Not a clean inversion, but the gap that previously made local-AI feel third-tier — the "Claude SDK chews this in 10 seconds, mine takes 30-100" line from the last post — has essentially closed for individual queries.

Then I noticed something. Looked at the SDK traces in LangSmith and every "fresh conversation" query had 180-210K input tokens. The user prompts were 30 tokens. System prompt is around 600. The rest — 200,000+ tokens of "fresh" — was accumulated tenant lookups, site data, VLAN inventory, all carried forward from prior conversations. The SDK web UI's "new conversation" button creates a new visual thread but doesn't reset the backend agent. Every comparison I'd been running was a cold-start of ours against a warm-cache of theirs.

Which makes the 29.5s win more meaningful than the raw number suggests, and the 70.6s loss more forgivable. Both numbers are still measuring different things though, and I should have spotted it earlier instead of writing celebratory trace reports.

One more data point worth landing before the closing thoughts.

Quick sanity check before posting this: switched the `.env` back to local llama.cpp/Qwen3-14B and re-ran the same multi-aspect Dunder Mifflin query. The 14B now has access to the same loaded skills, the same validator, the same architectural insurance the cloud model gets. Does it still defeat the model?

Yes, but differently. The 14B doesn't crash anymore. It used field projection, two-step patterns, no display-name-as-filter mistakes — all the architectural fixes carried over cleanly. Wall time was 60 seconds, essentially identical to the cloud model on the same query. But where the cloud model returned 52 devices across all 14 DM sites, the 14B returned 4 devices for just DM-Scranton. The first `netbox_search_objects("Dunder Mifflin")` came back empty; the 14B's response was to stop and ask me a clarifying question. The cloud model's response in the same spot was to keep trying alternative formulations. Different planning depth.

So the original "model is the bottleneck" hypothesis from the May post — confirmed for this query class, with the architecture variable now controlled. The architecture made the 14B runnable. It didn't make it capable.

A few honest observations about where this leaves things.

The `deepseek-v4-pro:cloud` subscription path is functional. ~$20/month is cheap insurance against unpredictable token costs during agent debugging — an agent in a tool-call loop can burn tokens fast on metered APIs. It's not local and it's not free, but it's accessible.

Claude SDK has been at this longer, and Anthropic has shipped purpose-built inference hardware tuned for low-latency interactive chat. Ollama Cloud's preview deepseek deployment hasn't matched that latency yet — when both models have similar work to do, Anthropic's per-token speed still shows up. But the answer-quality and reasoning-capability gap is now essentially closed.

The framework, skill, and validator layers are solid enough that swapping back to a local frontier model would be a one-line `.env` change. The privacy thesis from the original post is on hold pending hardware that could run a 600B+ MoE locally — multi-H100, ~$250K+ capex territory. Cloud-as-feasibility-lab confirmed there IS something worth running locally if the hardware ever becomes accessible.

Next phase is observability and evaluation, properly this time. The homegrown "fetch trace, eyeball JSON, write a markdown comparison" loop has hit its ceiling. Plan is a LangSmith evaluation harness — fixed benchmark dataset run across a model matrix (frontier cloud Ollama, smaller cloud variants, local Ollama models, Claude SDK as occasional reference), scored automatically rather than by manual reading. Same skill content and same MCP for every variant, so the comparison surface becomes "capability and cost per query class" rather than "framework A vs framework B." Also upgrading to Deep Agents 0.6, which among other things fixes the framework bug that ate two weeks of debugging earlier in this arc.

Six weeks. Not a small bet, but the trade-off space is much clearer now than when I started.

`#netbox #localai #ollamacloud #deepseek #langgraph #mcp`
