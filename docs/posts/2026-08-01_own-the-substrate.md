# Own the Substrate, Rent the Frontier — Telegram Post

**Date:** 2026-08-01
**Channel:** Telegram
**Status:** Draft
**Audience:** Tech / local-AI / network-automation (incl. research oversight)
**Length:** ~3200 chars (single message)

---

That "personal AI computer" video on local-first AI lands on a framing that maps almost exactly onto the NetBox agent I've been building — worth pulling the thread.

The idea: **the durable thing isn't the model — it's the stack.** Own the substrate (your runtime, your tools, your data) and *rent the frontier model as a visitor* for the rare, hard, high-value work. Not anti-cloud — anti-*dependence*.

That's more or less the architecture I ended up with, without having named it that way:

→ **Own the runtime.** One `.env` switch flips the agent between a fully-local llama.cpp backend (Qwen on my own GPUs, nothing leaves the network) and Ollama Cloud frontier models. The models are swappable; the harness, skills and tools stay put.

→ **Rent the frontier as a specialist.** `deepseek-v4-flash` handles the hard cross-domain queries; the local model covers the private path. The cloud model is hired for the job it's best at, not made the operating layer.

→ **Scope the tools.** One line stuck with me: an agent's access should be a permission, not a convenience — *"a meeting summariser doesn't need permission to delete files."* My NetBox agent is deliberately **read-only, no writes, ever** — enforced, not hoped. A query agent doesn't need the keys to the database.

Where I'd push the framing further: it stops at "own the stack and pick good models." But *"pick good models"* is usually an assertion. A big chunk of this project went into turning it into a measurement — a model-matrix eval, and a correctness judge that fact-checks answers against verified ground truth. It caught something a plain quality score never would: a model confidently hallucinating "7.7% IP utilisation" where the truth was **0%** — and scoring 0.9 on completeness for it. Owning the substrate is half the battle. Knowing which model is actually *right*, not just fluent, is the other half.

And this is where the piece I just wrapped up fits. **A read-only GraphQL path for the queries a single MCP call can't express** — the multi-hop, cross-domain ones ("which power feeds supply this rack, and from which panel", "circuits per provider and where they terminate"). It ships with a routing skill that decides *when* to reach for it, and in testing it fixed exactly the hallucination above — the cross-domain answer went from wrong to correct. It's up as a draft PR now.

The video calls the personal AI computer "a routing system," and that's the direction this points. Right now the routing is between *tools* inside one model. The next step is routing between *models*: **a fast local LLM fields the simple, private, everyday NetBox queries on its own — and only hands off to the GraphQL skill (and a heavier model) when a query goes genuinely multi-hop.** Local model as the daily driver; the cross-domain path invoked on demand, not by default.

Where this lands: local-first was never about beating the cloud. The frontier will keep mattering, maybe more. It's about not being *dependent* on it — frontier model as a hired specialist, owned substrate for the private, repetitive, context-heavy work. For infrastructure data that can't leave the network, that's not a nice-to-have. That's the whole game.

`#localai #agents #netbox #graphql #llamacpp #evaluation #privacy`
