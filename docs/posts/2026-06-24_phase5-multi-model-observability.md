# Phase 5 — Local + cloud LLMs, and why you have to evaluate them (Telegram Post)

**Date:** 2026-06-24
**Channel:** Telegram
**Status:** Draft
**Audience:** Tech-savvy / local-AI / agents — not assumed to know the specifics of the app
**Length:** ~4500 chars (two messages)
**Links:**
- Code: https://github.com/FinnMacCumail/ollamaDeepAgents
- Live writeup: https://finnmaccumail.github.io/rtf-research/phases/phase-5-production-deepagents/overview/

---

## POST 1

**Phase 5 is done: an AI agent that answers plain-English questions about infrastructure data — now running on a mix of local and cloud open models, and benchmarked properly across ten of them.**

First, context. This is one phase of a longer, fully-documented research programme on a single question: **how do you stop LLMs hallucinating in domain-specific applications** — where a confident wrong answer is worse than no answer? The whole thing lives here, written up phase by phase:

👉 **https://finnmaccumail.github.io/rtf-research/**

The arc so far: a natural-language movie/TV query system (Phase 1), an infrastructure data layer (Phase 2), a multi-agent orchestration attempt that failed outright and is documented *as* a failure (Phase 3), a head-to-head of two agent frameworks (Phase 4), and now Phase 5 — taking the best of that forward into a production agent with proper multi-model evaluation. If you only read one page, the site's overview ties the whole story together.

Quick framing for this phase specifically: it's an agent that takes a natural-language question ("where is VLAN 100 deployed across these sites, and what's using it?") and works out which tools to call, in what order, to answer it from a live data source. The interesting part isn't the app — it's two findings that generalise to almost any LLM agent you might build.

**Finding 1: a frontier *open/cloud* model now matches Claude — and the smaller sibling wins.**

I ran the same agent over a matrix of models through one inference backend (local models and cloud frontier models, no proxy layer in between). The standout: DeepSeek's V4-Flash — the *smaller, cheaper* cloud model — scored identically to its 1.6-trillion-parameter big brother on answer quality, at ~36% lower latency. For read-only Q&A work, the giant model was simply overkill. That's the new default.

The honest other half: small *local* models (14B–32B, running on your own box) still aren't there for the hard multi-step queries. A 32B model hallucinated answers and mangled its tool calls; a 14B "reasoning" model couldn't call tools at all. So the picture is nuanced — frontier-tier open models are genuinely production-ready, local small models are not *yet*. The bottleneck is model scale, not "local vs cloud" as a category. Six months ago the assumption was "local = compromise." Today it's "frontier-open = competitive, small-local = wait."

**Finding 2: you cannot eyeball this. You have to measure it.**

Which brings me to the actual point of the phase.

---

## POST 2

The only reason I can make confident claims like "Flash matches Pro at 36% less latency" or "this 32B model isn't ready" is that I stopped eyeballing outputs and built an **evaluation harness**.

The setup: a fixed set of benchmark questions with known-correct answers, run automatically across all ten models, each scored on three axes — did it state the right facts (deterministic check), did a *judge model* rate it complete, and how many tool calls it burned getting there. The result is a sortable leaderboard instead of ten hand-written "this felt good" reports — capability and cost per query class, not vibes.

Two things this surfaced that I'd never have caught by reading answers:

→ One model reached top-quality answers but used **3× the tool calls** of the best — it kept emitting a malformed argument shape, getting rejected, and retrying. Invisible in the final answer; obvious in the trajectory metric.

→ A framework upgrade silently **regressed** the agent — the one that sold me on observability. A correct, complete answer was being *overwritten* by an "All done!" filler in a post-processing step. At the answer level it just looked like the model got dumber. Only by reading the **trace** — the record of every step — could you see that the *previous* step already had the perfect answer, and a new default behaviour clobbered it.

Here's the mental model I'd hand anyone building with LLMs right now: **an agent isn't "a model" — it's a stack.** Your prompt sits on the framework's *hidden* default prompts, which sit on your tool layer, which sits on the model. When the output gets worse, everyone blames the model. But the model is usually the one piece you *didn't* touch — a rented black box you swap whole, can't see inside, can't tune. The layers *around* it are what quietly drift: a framework upgrade injects new default instructions, a tool schema changes, a dependency bumps.

That regression above is the perfect example — the model was byte-for-byte identical; a new framework default did all the damage. So "the model got worse" is usually "something around the model changed," and you only find out which by measuring. An eval harness re-scored against a fixed baseline turns every model swap, prompt tweak and dependency bump into a measured pass/fail; the trace tells you which layer actually moved. That's the difference between an agent you *hope* works and one you can actually maintain.

Phase 5 also closed an old loop: an earlier attempt to add local models had failed on a different stack — an architecture mismatch (a proxy in the middle), not a verdict on local models. Here, on a flexible framework with a native backend, it just worked.

And here's *why I keep investing in the local path even though cloud currently wins on quality* — **data**. This agent reads infrastructure data: topology, device inventories, IP allocations — exactly what many organisations can't ship to a third-party API. The Claude-SDK route is foundation-models-only: every query leaves your network for the provider, full stop. Open weights break that lock — you can run the *same* frontier model yourself. The honest nuance: "yourself" is a spectrum, and a *plain* rented GPU is still someone else's datacenter — your data is processed on their silicon. Real privacy means one of two things: a **confidential-compute GPU** (rented, but the memory is hardware-encrypted and attested, so the host physically *can't* read it) or your **own hardware** (nothing leaves the building). Neither is cheap or casual — it's an always-on commitment. But that's the door open weights unlock and closed foundation-model APIs keep shut: frontier-grade answers *and* genuine data privacy in one system.

**Code:** https://github.com/FinnMacCumail/ollamaDeepAgents
**Full writeup (with the leaderboard + the regression case study):** https://finnmaccumail.github.io/rtf-research/phases/phase-5-production-deepagents/overview/

`#localai #llm #agents #ollama #deepseek #evaluation #observability #langsmith`
