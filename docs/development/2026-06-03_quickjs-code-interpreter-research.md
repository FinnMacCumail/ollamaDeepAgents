# DeepAgents 0.6 Code Interpreter Middleware (QuickJS) — Research

**Date:** 2026-06-03
**Status:** Research complete, validation spike pending
**Purpose:** Investigate whether the QuickJS-based Code Interpreter middleware shipping in DeepAgents 0.6 can materially reduce wall time on multi-call NetBox query classes (specifically the ~70-second VLAN-deployment-across-tenant-sites query), and document the integration shape + verification gates needed before adopting it
**Related:** `2026-06-03_langsmith-evaluation-research.md` (broader LangChain ecosystem research — this doc drills into one specific feature flagged there as worth investigating)

---

## Context

Trace report `2026-05-26_019e63e1_two-queries-baseline-floor.md` and the postscripts that followed it established two query-class baselines for this project's NetBox agent on `deepseek-v4-pro:cloud`:

- Device-detail lookup (e.g. `dmi01-nashua-rtr01`): **29.5s** — beat Claude SDK's 36.2s
- Cross-relationship multi-step (e.g. "VLAN 100 across Jimbob's Banking sites"): **70.6s** — slower than Claude SDK's 38.7s

The decomposition of the slow case is informative. The 70s breaks down approximately as:

- 4 model turns × (~10-15s prompt + decode to emit one tool call + ~1-2s tool execution)
- Plus the final synthesis turn that streams the answer (~10-15s on top of the 4)
- Plus per-turn prompt growth as the conversation accumulates 4 tool messages of NetBox JSON (5-20 KB each), which slows the *later* model turns more than the early ones

**Most of the 70s is model prompt-and-decode latency, not NetBox API latency.** Each NetBox call itself is 1-2s; the cycles of "model reads result → plans → emits next call" are what dominates.

The earlier LangSmith research flagged DeepAgents 0.6's Code Interpreter middleware as the only new feature that targets this root cause (the other 0.6 features address quality, context-window, or quite-different latency axes). This document captures the focused research on what the middleware actually is, how it would integrate, and what verification gates are necessary before adopting it.

---

## 1. What QuickJS is and why this exists

QuickJS is a small, embeddable JavaScript engine originally written by Fabrice Bellard. It ships as ~200 KB of native code, supports most of ES2023 including top-level `await`, and is designed for host-controlled embedding — the host process controls memory limits, execution time, and what capabilities are bridged in. It has **no ambient capabilities by default** — no DOM, no `fetch`, no filesystem, no timers, no subprocess.

The DeepAgents partner package `langchain-quickjs` uses a Rust binding (`quickjs-rs >=0.1.2,<0.2.0`), which gives the Python process a deterministic VM with a hard memory ceiling and an interruptible execution loop.

### Why a JS engine inside an LLM agent loop

The LangChain blog's framing is that this is a **code-first orchestration substrate for the agent loop**, not a sandbox for the user's domain code.

- **Models are more fluent in JS than in typed Python tool calls.** Frontier and mid-tier models emit syntactically correct JavaScript at far higher rates than they emit valid Python with typed kwargs against arbitrary tool schemas.
- **QuickJS has no ambient capabilities to leak.** Python's `exec` and subprocess-based Python sandboxes leak filesystem, env, and network unless aggressively stripped. QuickJS starts with nothing — the host opts-in every bridge function.
- **Top-level `await` matches tool semantics.** Every MCP/LangChain tool is async; QuickJS supporting `await` at top level means the model can write the obvious `const x = await tools.foo(); const y = await tools.bar(x);` without any wrapper IIFE.
- **Snapshot/restore.** quickjs-rs exposes serializable VM state, which is what makes the cross-turn persistence model work without a long-running process.

### Alternatives the team plausibly considered

| Alternative | Why not (likely) |
|---|---|
| Pyodide / restricted Python `exec` | Model less fluent in Python tool-call syntax; harder to sandbox; much larger memory footprint |
| WASI / Wasmtime with JS runtime on top | Heavier setup, more moving parts |
| V8 isolates / isolated-vm | V8 is huge; Python binding story is bad |
| Subprocess sandboxes (E2B, Daytona, Modal, Runloop) | These exist too — but as `partners/sandboxes` for a different purpose: "code-first for *acting on environments*" vs interpreters being "code-first for *acting inside the agent loop*" |

The `deepagents/libs/partners/` tree contains both `quickjs` and `daytona`, `modal`, `runloop`. They're complementary.

---

## 2. What the middleware actually does

Two things, both important:

### 2.1 Adds a new tool to the agent's tool surface

Default name `eval` (configurable via `tool_name`). When the model calls `eval(code="<JS source>")`, the body is JavaScript/TypeScript that runs inside a persistent QuickJS VM.

### 2.2 Exposes selected existing tools INTO the JS sandbox

Via an opt-in allowlist called **PTC** (Programmatic Tool Calling). Tools listed in `ptc=[...]` become callable from inside the JS as async functions under a `tools.*` namespace.

Critical detail from the docs:

> "PTC calls currently execute through the interpreter bridge and do not go through the normal tool calling path. As a result, `interrupt_on` approval workflows are not enforced per PTC-invoked tool call."

The JS isn't writing strings that escape back through the LLM to fire another tool call. The JS calls the tool's underlying Python coroutine **directly through the bridge**. Only the final value the JS code returns (plus captured `console.log` output) flows back as the `eval` tool's `ToolMessage`.

### 2.3 State lifecycle

- **Per-call state:** Variables defined in one `eval` call are visible to the next `eval` call in the same turn ("repeated `eval` calls use the live interpreter context object").
- **Cross-turn state:** The middleware snapshots the VM after the turn and restores it before the next turn (`snapshot_between_turns=True` by default).
- **Caveat:** Snapshots only retain "values that can be reasonably serialized." Class instances and live host handles do NOT survive a snapshot/restore cycle.
- **VM scope:** One VM per agent thread (per LangGraph `thread_id`). Fresh per new thread.

---

## 3. Concrete interaction example

From the docs (Python and JS versions both use the same example — parallel sub-agent research):

```typescript
const reports = await Promise.all(
  topics.map((topic) =>
    tools.task({
      description: `Research ${topic} in Deep Agents and return three concise findings.`,
      subagent_type: "general-purpose",
    }),
  ),
);
```

Things this example shows:

- **Tool names get camelCased.** `web_search` → `tools.webSearch`. `netbox_get_objects` → `tools.netboxGetObjects`.
- **`Promise.all` across the JS event loop.** Independent calls run concurrently from the host's perspective. No LLM round-trip between them.
- **Intermediate results stay in JS variables.** `reports` exists only in the VM; the model never sees the intermediate array unless the code explicitly `console.log`s it or returns it.

Error handling stays local to the VM:

```typescript
try {
  const report = await tools.task({
    description: "Check the migration notes and return breaking changes.",
    subagent_type: "general-purpose",
  });
  console.log(report);
} catch (error) {
  console.log(`Subagent failed: ${error.message}`);
}
```

Tool-side exceptions surface as JS exceptions. The model can `try/catch` and decide programmatically whether to retry, fall back, or give up — without burning a model turn to read the error string and decide.

The framework is built around three named patterns:

1. **Programmatic Tool Calling** — the above
2. **Recursive Workflows** — JS-managed work queue popping items, calling a sub-agent on each, deciding what to feed back to the parent model
3. **Parallel decomposition** — `Promise.all` over independent calls

---

## 4. End-to-end agent loop with the middleware active

1. Model emits `tool_call(name="eval", args={"code": "<JS source>"})`.
2. Middleware intercepts. JS source goes into the persistent QuickJS VM. Before execution, the bridge installs (or refreshes) a `tools` global containing one async function per PTC-allowlisted tool.
3. JS runs to completion (or timeout / memory limit / PTC-call-cap). During execution, `console.log` is captured (default `capture_console=True`).
4. Final value + captured log are concatenated and truncated to `max_result_chars` (default 4000).
5. Result handed back as a single `ToolMessage` against the original `eval` call. **From the model's perspective, the entire JS block — including potentially dozens of internal PTC calls — counts as one outer tool call.**
6. At end of turn, VM snapshotted into agent state, persists into next turn via the checkpointer.

### What the JS can NOT do

No `fetch`, no filesystem, no `process`, no `setTimeout` against wall-clock unless host bridge provides it, no subprocess. The docs explicitly list "Filesystem access," "Network access," "Wall-clock/datetime access," and "Shell commands or OS-level execution" as not-available-by-default. **The only escape from the VM is via the `tools.*` allowlist** — that's the entire attack surface.

---

## 5. Limits / safety / cost model

Documented defaults from the Python interpreters page:

| Option | Default | Bounds |
|---|---|---|
| `memory_limit` | 64 MB | QuickJS heap |
| `timeout` | 5.0 s | Wall time per `eval` call |
| `max_ptc_calls` | 256 | Hard cap on `tools.*` invocations from one `eval` |
| `max_result_chars` | 4000 | Truncation applied to returned ToolMessage body |
| `tool_name` | `"eval"` | Tool the model sees |
| `capture_console` | `True` | `console.log` becomes part of result |
| `snapshot_between_turns` | `True` | Persist VM state across turns |

### Cost accounting

From the model's perspective, an `eval` block that internally fans out to 10 tool calls counts as **one outer tool call** in the conversation transcript. The model sees one `assistant → tool_call(eval)` and one `tool → ToolMessage(result)`.

Token spend on the outer loop is dramatically lower than 10 sequential tool turns. But the *underlying* tools still actually execute 10 times (with whatever cost they carry — NetBox API calls in our case).

### Safety boundary

The docs are explicit: **this is "a scoped interpreter runtime, not a full production sandbox."** If a model can call `tools.shell` via PTC, it can shell out. The security model IS the PTC allowlist — `ptc=[...]` is the only knob.

---

## 6. Application to ollamaDeepAgents — integration shape

### 6.1 Prerequisite: DeepAgents 0.6 upgrade

`pyproject.toml` currently pins `deepagents>=0.5.6`. `langchain-quickjs 0.1.3` requires `deepagents>=0.6.0,<0.7.0`. Upgrade is gating.

(The 0.6 upgrade also removes the need for our `HarnessProfile.tool_description_overrides` Workaround A in commit `3b65e0c`, since the `read_file(path=)` framework bug is fixed on main. Worth doing on its own merits.)

### 6.2 Pyproject change

```toml
"deepagents[quickjs]>=0.6.5,<0.7",
```

(0.6.5 is when `RubricMiddleware` landed; 0.6.8 is current per PyPI.)

### 6.3 Single file change in `src/agents/netbox_agent.py`

One import and one entry in the middleware list around line 282:

```python
from langchain_quickjs import CodeInterpreterMiddleware

middleware.append(
    CodeInterpreterMiddleware(
        ptc=[
            "netbox_get_objects",
            "netbox_get_object_by_id",
            "netbox_search_objects",
            "netbox_get_changelogs",
        ],
        timeout=30.0,           # default 5.0 is too low for 4-6 chained NetBox calls
        max_ptc_calls=64,       # tighter than default 256, still generous for pagination
        max_result_chars=8000,  # NetBox JSON is verbose; default 4000 truncates often
    )
)
```

Placement: **after** `FilterErrorRecoveryMiddleware` in the list so non-PTC NetBox calls still flow through recovery normally.

### 6.4 PTC opt-in is by name, not auto-wholesale

Per the docs, MCP tools are NOT auto-exposed wholesale. You list them in `ptc=[...]` explicitly. This is good — it's the safety boundary.

### 6.5 What an `eval`-orchestrated VLAN query would look like

The current 70s VLAN query (4 sequential model turns + synthesis) could collapse to one `eval` block:

```javascript
const tenant = await tools.netboxSearchObjects({
  query: "Jimbob's Banking", object_types: ["tenancy.tenant"]
});
const tenantId = tenant.results[0].id;

const [sites, vlans] = await Promise.all([
  tools.netboxGetObjects({
    object_type: "dcim.site",
    filters: { tenant_id: tenantId },
    fields: ["id", "name"], limit: 100
  }),
  tools.netboxGetObjects({
    object_type: "ipam.vlan",
    filters: { tenant_id: tenantId, vid: 100 },
    fields: ["id", "site"], limit: 100
  })
]);

const prefixes = await tools.netboxGetObjects({
  object_type: "ipam.prefix",
  filters: { vlan_id: vlans.results.map(v => v.id) },
  fields: ["id", "prefix", "vlan", "site"], limit: 100
});

return { tenant: tenant.results[0], sites, vlans, prefixes };
```

### 6.6 Realistic wall-time projection

| Phase | Today (4 sequential turns) | With `eval` PTC |
|---|---|---|
| Plan + emit first tool call | ~10-15s | ~10-15s (slightly longer to author full JS up front) |
| Sequential turns 2-4 | ~30-45s | 0 |
| Underlying NetBox API time | ~5-10s (4 calls × 1-2s each, serial) | ~2-6s (calls back-to-back inside JS; can use `Promise.all` for independent fan-out) |
| Final synthesis turn | ~15-20s (reads 4 fat tool messages) | ~5-10s (reads compact pre-aggregated summary) |
| **Total** | **~70s** | **~20-30s** |

**Defensible projection: roughly halving wall time on this query class.** Most of the win is removing 3 prompt-decode cycles. Secondary win is the synthesis turn sees a compact summary instead of fat NetBox JSON.

The gain compounds the larger the conversation history grows, because the prompt-decode cycle cost scales with conversation length.

---

## 7. Three critical uncertainties — verification gates

These need verification spikes BEFORE adopting in production. None individually large; together they bound the risk.

### 7.1 MCP tools may need adapter shim for PTC

Docs say "selected agent tools become callable" via PTC. Examples show native LangChain `BaseTool` instances. They do NOT explicitly confirm that MCP-derived tools (from `langchain-mcp-adapters`) auto-bridge.

Shape strongly suggests yes — they're all `BaseTool` instances at the langgraph layer — but unverified.

**Verification:** ~10 lines of test code that builds the middleware with `ptc=["netbox_get_objects"]` and invokes a trivial JS call. **Half day max.**

### 7.2 `FilterErrorRecoveryMiddleware` likely does NOT see PTC tool errors

This is the bigger architectural concern. Docs explicit:

> "PTC calls currently execute through the interpreter bridge and do not go through the normal tool calling path."

The existing `FilterErrorRecoveryMiddleware` (and the architectural insurance from commit `34585be` that converts `ToolException` to structured `TOOL_API_ERROR` ToolMessages) **may never be invoked** for tool calls fired from inside `eval`. Failures surface as JS exceptions inside the VM, and only escape if the JS code has `try/catch` and chooses to surface them.

**Implications:**
- Architectural insurance from `34585be` becomes inoperative for the PTC path
- Skill content has to teach the model to write `try/catch` around tool calls inside JS, OR accept errors propagating as a single "JS execution failed" message
- Validator errors get re-routed similarly

**Verification + mitigation:** test what happens when a JS block triggers a NetBox 400. If the model can't see and recover, port recovery hints into skill content as JS `try/catch` patterns. **Half day.**

### 7.3 Local Ollama models may not emit reliable JS

The LangChain example uses `baseten:zai-org/GLM-5` and `openai:gpt-5.4` — both frontier-tier. Our stack runs `deepseek-v4-pro:cloud` (frontier, fine) AND smaller local models (Qwen3-14B, Qwen2.5-32B — which are first-class citizens in the planned model-matrix eval).

Smaller models often produce JS with subtle issues:
- Wrong arg-object shape
- `tools.netbox_get_objects` instead of `tools.netboxGetObjects` (camelCase confusion)
- Forgetting `await`
- Returning a Promise instead of awaiting it

If a 14B model needs 3 rounds of error-recovery to get the JS right, **the interpreter could INCREASE latency** instead of reducing it.

**Verification:** part of the planned model-matrix evaluation harness (from `2026-06-03_langsmith-evaluation-research.md`). Run with and without `CodeInterpreterMiddleware` enabled per model. The matrix surfaces which models benefit vs which regress. **No extra cost** beyond what the eval harness already covers.

---

## 8. Failure modes specific to NetBox workload

Beyond the three gating uncertainties above:

| Failure | Mitigation |
|---|---|
| HTTP 400 inside JS block — error recovery middleware bypassed | See §7.2 — `try/catch` in skill content patterns |
| Silent partial pages — `netbox_get_objects` default `limit=5` | Skill must teach `limit: 100` up-front since intermediate results aren't visible to the model |
| Default `max_result_chars=4000` truncates NetBox JSON debug | Set 8000+, prefer to return summaries not raw rows |
| PTC call cap on heavy pagination | Default 256 is generous but set explicitly |
| Default `timeout=5.0` far too short | Raise to 30s for NetBox workloads (multi-call queries) |
| Snapshot non-roundtrip-ability | Don't put class instances or live host handles into JS scope expecting them to persist |

---

## 9. Comparison vs other 0.6 features

| Feature | Addresses 70s VLAN-query bottleneck? |
|---|---|
| **CodeInterpreterMiddleware (QuickJS)** | **Yes** — directly removes 3 of 4 prompt-decode cycles |
| `RubricMiddleware` (0.6.5+) | No — addresses output quality, adds latency rather than reducing it |
| `SubAgentMiddleware` (built-in) | Partial — addresses context-window bloat but not round-trips (sub-agent still does N sequential turns internally) |
| Daytona / Modal / Runloop sandbox middleware | No — overkill for "compose 4 tool calls"; adds container startup overhead |
| Anthropic prompt caching | Helps but additive; doesn't apply to non-Anthropic models anyway |

**For this specific latency bottleneck, the QuickJS interpreter is the right answer in 0.6** and the only feature that targets the root cause.

---

## 10. Skill content implications

Current `src/skills/netbox-mcp-filters/SKILL.md` teaches multi-call decomposition in Python-flavored pseudocode (lines 40-104). Three options if PTC becomes the orchestration substrate:

| Option | Cost | Benefit |
|---|---|---|
| **Dual examples in one skill** | Skill doubles in size; model has to choose pattern | Backwards-compatible — model can still do sequential calls if it prefers |
| **Replace pseudocode with JS** | One-time port; cleaner | Forces every multi-step query through `eval` |
| **Separate `netbox-mcp-ptc` skill** | One new file; progressive disclosure means no cost until referenced | Cleanest separation; lowest baseline token cost |

**Recommendation: option 3** — new `netbox-mcp-ptc` skill, plus a one-line pointer in `netbox-mcp-filters` saying "if you intend to do >2 chained NetBox lookups, prefer the `eval` tool — see the `netbox-mcp-ptc` skill."

`CodeInterpreterMiddleware` adds its own tool description telling the model "you can write JS that calls these tools." That covers existence. The skill's job is teaching domain-specific orchestration patterns (pagination, batching, decomposition) in JS form.

---

## 11. Open architectural concern — dual error-recovery paths

If we adopt PTC, the codebase will have **two parallel error-recovery paths**:

1. **Existing one (sequential tool calls):** intercept `ValueError` + `ToolException` at the wrapper level, convert to structured `TOOL_API_ERROR` / `TOOL_VALIDATION_ERROR` ToolMessages, agent loop continues
2. **New JS-side one (PTC):** `try/catch` in the JS, model authors recovery inline

The skill content has to know which path applies based on orchestration mode. That's an extra dimension of complexity in the skill file that doesn't exist today.

It's manageable, but worth flagging: adopting PTC isn't free. **It's a structurally different way of organizing the agent loop, and the existing failure-recovery scaffolding doesn't extend into it.**

This is the strongest argument for option 3 (separate skill) — keep the two orchestration modes' guidance separated, so the model knows it's choosing between two coherent systems rather than mixing patterns from each.

---

## 12. Recommended sequencing

Given the three uncertainties (§7), the safe path:

1. **Spike 1 (½ day):** validate MCP tools bridge through PTC. 10-line test against a single tool. If they need adapters, decide whether to write one or fall back to native tool wrappers.
2. **Spike 2 (½ day):** validate that NetBox 400 errors inside `eval` are recoverable from the model's perspective. If not, plan the skill-side `try/catch` content.
3. **Spike 3 (½ day):** run a single benchmark query (the VLAN one) on `deepseek-v4-pro:cloud` with and without the middleware. Measure actual wall-time delta. Confirm the 70 → 20-30s projection (or invalidate it).
4. **If all three pass:** integrate properly. Add the middleware, author the `netbox-mcp-ptc` skill, add the pointer to `netbox-mcp-filters`.
5. **Add to the model-matrix eval harness** (per `2026-06-03_langsmith-evaluation-research.md`) so each model variant is tested with and without `CodeInterpreterMiddleware`. Some models will benefit; some may regress.

Steps 1-3 are independent and parallelizable. Total **~1-2 days of validation work** before committing to integration.

---

## 13. Sources

- [Deep Agents v0.6 blog (Sydney Runkle, LangChain)](https://www.langchain.com/blog/deep-agents-0-6)
- [Interpreters docs (Python)](https://docs.langchain.com/oss/python/deepagents/interpreters)
- [Interpreters docs (JavaScript)](https://docs.langchain.com/oss/javascript/deepagents/interpreters)
- [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization)
- [Deep Agents middleware list](https://docs.langchain.com/oss/python/deepagents/middleware)
- [Introducing Rubrics for deepagents](https://www.langchain.com/blog/introducing-rubrics-for-deepagents)
- [deepagents on PyPI (versions 0.6.0–0.6.8)](https://pypi.org/project/deepagents/)
- [langchain-ai/deepagents GitHub](https://github.com/langchain-ai/deepagents)
- [QuickJS (Bellard)](https://bellard.org/quickjs/)
- [Empowering AI: The QuickJS Package for LLM Tool Calling (dev.to)](https://dev.to/sebastian_wessel/empowering-ai-the-quickjs-package-for-llm-tool-calling-n1o)

---

## 14. Uncertainty register

| Item | Confidence | How to resolve |
|---|---|---|
| MCP-adapter `BaseTool` instances bridge through PTC automatically | **Medium** (shape suggests yes; docs don't confirm) | Spike 1 |
| `FilterErrorRecoveryMiddleware` observes PTC-invoked tool errors | **Low** (docs explicitly say PTC bypasses normal tool path) | Spike 2 — likely answer is NO; mitigation is skill content |
| Our specific Ollama/llama.cpp models reliably emit valid JS against `tools.*` | **Low** (model-dependent; LangChain examples use frontier-only) | Spike 3 + ongoing eval-matrix data |
| `RubricMiddleware`, sandbox middlewares, etc. could substitute for PTC | **High** (they don't — they target different axes) | None — comparison already done in §9 |
| QuickJS heap default (64 MB) is sufficient for NetBox JSON payloads | **High** (NetBox responses are KB-scale; 64 MB is enormous) | None |
| Snapshot-restore preserves NetBox JSON values across turns | **High** (NetBox JSON is plain serializable) | None |

---

**Recommended next step:** sequence the three spikes (§12 steps 1-3) as a single ~1-2 day investigation block. The outcome of all three together determines whether to proceed with integration. If any one fails decisively, the decision becomes a defer rather than a no — the failures are technically resolvable (write an MCP adapter; rebuild error recovery for JS; route smaller models away from `eval`) but the cumulative cost may exceed the wall-time saving on the VLAN query class.
