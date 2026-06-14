# Local NetBox AI Assistant — Telegram Post

**Date:** 2026-05-05
**Channel:** Telegram
**Status:** Draft
**Audience:** Tech / local-AI / network-automation
**Length:** ~2500 chars

---

I've subsequently spent the past few weeks devloping a fully local NetBox AI assistant using local models. Which brings privacy and no per-query bill - Using the two RTX 2080 Tis  and llama.cpp as the inference server. After experimenting with a handful of different local models I settled on Qwen3-14B-Q5_K_M for the deeper testing — best balance of tool-calling reliability and inference speed I've found on this hardware.

The plan: feed natural-language questions about my NetBox infrastructure (*"show me devices in the Akron site"*, *"what's in the Comms closet rack?"*) into an agent built on DeepAgents 0.5.6, which calls NetBox via MCP under the hood.

Several things have come together well. With a LangGraph checkpointer wired in, the agent now actually remembers conversations — I can ask about a rack, then say *"give me details of this rack"*, then *"list the devices"*, and it just works, reusing IDs from earlier turns. A skills system lets me give the agent loadable markdown playbooks — things like NetBox's filter constraints — that it pulls in on demand. LangSmith tracing has been invaluable; every "wait, why did the model do that?" question is one trace fetch away. Following the Claude SDK's (which I had previously devloped) system-prompt patterns (field projection, per-object-type templates), token usage on tool calls dropped roughly 90%.

However there are setbacks.

The 14B model is wonderfully unreliable about following its own instructions. One run, it perfectly resolves *"DM-Akron"* → tenant ID → site filter, two-step pattern textbook. Next run on the same query, it just throws `tenant=Dunder-Mifflin, Inc.` straight at the API and earns a 400. The prompt has imperative warnings in capital letters. The model nods along, then ignores them. Adding more capital letters has diminishing returns.

Complex multi-aspect queries still defeat it — *"show all sites with device counts and IP prefix assignments"* is enough planning to make it freeze partway through. Pagination handling is non-existent unless explicitly forced. And honestly? It's slow. A query Claude SDK chews through in 10 seconds takes me 30–100. Local and private isn't free.

Where this lands: for privacy-critical environments, air-gapped networks, or anywhere the answer to *"can we send this to Anthropic?"* is no — it works, and it's getting better. For a polished user-facing assistant, the gap is still real.

So I'm now running the same agent against frontier-scale models via Ollama Cloud — `deepseek-v4-pro` (1.6T params, 1M context) being the headline test bed. Yes, this breaks the privacy story for the moment. But the rationale is clean: if a query that defeats the 14B works cleanly against the cloud model, that's evidence the architecture is sound and the model is the bottleneck. Then the question becomes whether the local hardware is worth the spend. Cloud as a feasibility lab for what's worth bringing home.

`#llamacpp #langgraph #netbox #localai #mcp #ollamacloud`
