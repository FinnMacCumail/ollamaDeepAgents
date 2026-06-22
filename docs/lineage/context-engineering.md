<!--
PROVENANCE: Harvested 2026-06-22 from the ancestor repo FinnMacCumail/deepagents
(docs/guides/context-engineering-report.md). Preserved here because the design
principles it documents carried forward into ollamaDeepAgents:
  - "Generic > Specialized" (3-4 generic NetBox tools, not 62) — STILL the design.
  - "No subagents for NetBox" — STILL the design (see no-subagents-rationale.md).
  - Offload via MCP + virtual filesystem — STILL the design.
SUPERSEDED parts (kept for lineage, not current practice):
  - The hand-rolled MessageTrimmingMiddleware → replaced by DeepAgents 0.6's built-in
    SummarizationMiddleware.
  - Anthropic-only prompt caching / monkeypatched CachedChatAnthropic → ollamaDeepAgents
    uses a dual Ollama/llama.cpp + Ollama Cloud backend; caching is provider-native.
See docs/development/2026-06-22_multi-repo-update-plan.md for the full lineage.
-->

# Context Engineering in Production: Lessons from Building a NetBox Infrastructure Agent

## The Challenge

We built an AI agent to query and analyze infrastructure data from NetBox (a data center infrastructure management platform). Initial implementation worked but faced a critical problem: **token usage spiraled out of control**. We observed:

- **40,000+ prompt tokens per LLM call** (99.1% of total token usage)
- **Context accumulation** causing unbounded growth across multi-step queries
- **Cost inefficiency** from repeatedly sending full conversation history

The solution required applying five complementary context management strategies: **Offload, Reduce, Retrieve, Isolate, and Cache**.

---

## 1️⃣ Offload Context: Store State Outside Primary Context

**Implementation:**
- **MCP (Model Context Protocol) Server**: The NetBox API state lives in a separate MCP server process, not in agent context. The agent calls lightweight tools (`netbox_get_objects`, `netbox_get_object_by_id`, `netbox_get_changelogs`) that fetch data on demand.
- **File System Tools**: Built-in tools (`write_file`, `read_file`, `ls`, `edit_file`) use LangGraph's state as a virtual filesystem, enabling persistent memory across invocations without bloating prompt context.
- **External Memory Pattern**: Following Anthropic's research system approach, completed work phases are summarized and stored externally, allowing agents to "forget" details while retaining conclusions.

**Key Insight from Research:**
> "Context offloading stores information outside primary context using 'scratchpad' or note-taking tools." (dbreunig.com)

This aligns with Manus's principle: *"Treat the file system as unlimited and persistent memory."*

---

## 2️⃣ Reduce Context: Minimize Token Overhead

**Tool Reduction (800-1,600 tokens saved per request):**
- **Before**: 62 specialized NetBox tools (one per object type: `get_sites`, `get_devices`, `get_racks`, etc.)
- **After**: 3 generic tools with `object_type` parameter
- **Result**: Eliminated redundant tool schemas from prompt

**Message Trimming:**
Implemented `MessageTrimmingMiddleware` to address the 99.1% prompt token problem:
```python
# Two-stage token counting approach
# 1. Accurate threshold detection (model-based counting)
token_count = model.get_num_tokens_from_messages(messages)

if token_count > 30000:
    # 2. Fast trimming (approximate counting with compensation)
    adjusted_target = 30000 / UNDERESTIMATION_FACTOR
    trimmed = trim_messages(messages, max_tokens=adjusted_target)
```

**Migration to LangChain v1:**
Adopted `SummarizationMiddleware` for automatic context compression:
- Target: Reduce 40k → 15-20k prompt tokens
- Strategy: Keep recent tool results (last 2-3 calls), summarize older history
- Preserve: System prompt (cached), current query, recent context

**Key Finding:**
The problem was **not** high token generation (0.9% completion tokens) but **excessive input size** (99.1% prompt tokens). Solution: trim history, not responses.

---

## 3️⃣ Retrieve Context: Fetch Only What's Needed

**Generic Tool Pattern:**
Instead of loading all NetBox object schemas upfront:
```python
# Old approach: 62 specialized tools
get_sites(), get_devices(), get_racks(), get_interfaces()...

# New approach: 1 generic tool
netbox_get_objects(object_type="sites")
netbox_get_objects(object_type="devices")
```

**On-Demand Data Fetching:**
- MCP server fetches from NetBox API only when called
- 60-second tool result caching reduces redundant API calls
- Agent receives focused, relevant data vs. comprehensive object dumps

**RAG-Inspired Selection:**
Following the principle: *"Selectively add relevant information to improve response quality"* (dbreunig.com), we dynamically choose which NetBox objects to query based on the user's question, rather than pre-loading all infrastructure data.

---

## 4️⃣ Isolate Context: Quarantine When Beneficial

**Sub-Agent Evaluation:**
Initially considered sub-agents for context isolation but discovered they were **unnecessary** for NetBox queries:
- NetBox queries are self-contained (no long-horizon dependencies)
- No benefit from parallel exploration (linear data retrieval)
- Context pollution not occurring (tool results naturally focused)

**When We Use Isolation:**
Following Cognition's guidance (*"Share full context... agents working in isolation can produce conflicting results"*), we reserve sub-agents for:
- Research tasks requiring deep, independent exploration (e.g., access other data sources - monday.com, wiki's ect)
- Parallel processing of independent subtasks (LangChain's Open Deep Research pattern)

**Clean Session Management:**
MCP session uses singleton pattern with stdio communication, ensuring:
- One persistent connection per agent lifecycle
- No context leakage between queries
- Proper cleanup on exit

**Key Decision:**
*"Don't build multi-agents just because you can."* For NetBox, a single agent with proper context management outperformed a multi-agent architecture.

---

## 5️⃣ Cache Context: Maximize Reusability

**Anthropic Prompt Caching:**
- **System prompt** (~1,693 tokens): Cached with 1-hour TTL
- **Tool schemas** (8.7k tokens): Automatically cached by provider
- **Cache hit rate**: 84%+ on validation queries
- **Cost savings**: ~70% reduction on cached portions

**Cache-Aware Prompt Design:**
Following Cursor team's insight (*"Keep prompt prefixes stable to maximize cache hit rates"*), we:
- Keep system prompt deterministic (no dynamic timestamps)
- Append-only context pattern (prevents cache invalidation)
- Stable tool ordering (consistent serialization)

**KV-Cache Optimization:**
The Cursor team's approach inspired our strategy: *"Warm cache while user is typing to reduce latency."* Similarly, our MCP server maintains warm connections to NetBox, reducing first-call overhead.


### 1. **Context Is Not Free** (dbreunig.com)
Every token influences model behavior. Our 99.1% prompt / 0.9% completion split validated this—the bottleneck was context accumulation, not generation.

### 2. **Multi-Agent ≠ Multi-Step** (Anthropic Research System)
*"Multi-agent systems work mainly because they help spend enough tokens to solve the problem."* We spend tokens on iteration within a single agent rather than spawning multiple agents.

### 3. **File System as Memory** (Manus)
*"Design compression strategies that are restorable."* Our virtual filesystem enables agents to write structured outputs (reports, intermediate findings) that persist across queries without bloating prompt context.

### 4. **Caching as Infrastructure** (Cursor Team)
Prompt caching isn't optional—it's foundational. We achieve 84%+ hit rates by designing for cache stability (deterministic prompts, append-only context).

### 5. **Generic > Specialized** (Our Finding)
Three generic tools with parameters outperform 62 specialized tools. Reduces token overhead and improves model reasoning (fewer choices, clearer purpose).

---

## Future Directions

1. **Dynamic Trimming**: Implement content-aware thresholds that adjust based on query complexity (inspired by attention-based selection research)

2. **Tool Result Compression**: Address cases where single verbose API responses dominate token count (e.g., 28k tokens from one NetBox interface object)

3. **Adaptive Context Windows**: Following LangChain's Open Deep Research pattern, dynamically scale context budget based on task complexity

4. **Error Context Learning**: Per Manus's insight (*"Keep the wrong stuff in... allow models to see and learn from failed actions"*), experiment with retaining error context to improve recovery

---

## Conclusion

Building the NetBox agent validated a core principle: **context engineering is the primary optimization lever for production AI systems**. The five strategies—Offload, Reduce, Retrieve, Isolate, Cache—aren't theoretical; they're essential for cost-effective, performant agents.


