# DeepAgents 0.6 Code Interpreter Middleware (QuickJS) — Research

**Date:** 2026-06-03 (research) · 2026-06-15 (spikes executed) · 2026-06-22 (decision recorded)
**Status:** ✅ Spikes complete — **DECISION: defer adoption** (mechanism works, but no benefit for the current single-source NetBox workload). Re-trigger conditions documented in §15.
**Purpose:** Investigate whether the QuickJS-based Code Interpreter middleware shipping in DeepAgents 0.6 can materially reduce wall time on multi-call NetBox query classes (specifically the ~70-second VLAN-deployment-across-tenant-sites query), and document the integration shape + verification gates needed before adopting it
**Related:** `2026-06-03_langsmith-evaluation-research.md` (broader LangChain ecosystem research — this doc drills into one specific feature flagged there as worth investigating); `2026-06-14_deepagents-0.6-upgrade.md` (the upgrade that unblocked these spikes)

---

## TL;DR — Spike results (2026-06-15)

Three verification spikes were run against the real NetBox MCP server on `deepseek-v4-flash:cloud` (DeepAgents 0.6.10 + `langchain-quickjs` 0.2.0). Scripts live in `tests/spike/`.

| Spike | Question | Result |
|---|---|---|
| **1 — MCP→PTC bridge** | Do MCP BaseTools auto-bridge into the JS `tools.*` namespace? | ✅ **YES.** `netbox_get_objects` → `tools.netboxGetObjects(...)` (auto camelCase), full round-trip to the real MCP server, returns real NetBox data. Counts as **one** outer tool call from the agent's perspective. |
| **2 — Error recovery** | Does `FilterErrorRecoveryMiddleware` see PTC-invoked tool errors? | ✅ **YES — unexpectedly.** Prior research predicted PTC would bypass it. It does not: the middleware wraps the tool's `_arun()` itself, and the PTC bridge calls that wrapped method. A deliberate bad filter surfaced as a `TOOL_VALIDATION_ERROR` string in the eval result, and the model recovered identically to the direct-call path. No skill-content `try/catch` rewrite needed. |
| **3 — Wall-time delta** | Does PTC reduce wall time on the VLAN 100 multi-call query? | ❌ **NO. The model never invoked `eval` at all** (0 eval calls, 21 direct `netbox_*` calls) and the variant *with* PTC available was **+13.7% slower** (103.0s vs 90.6s) purely from the prompt-bloat tax of having `eval` in the tool surface. |

**Decision: do not adopt CodeInterpreterMiddleware for the current agent.** The mechanism is sound and error semantics are preserved — but PTC's value comes from fan-out / parallelism / large-result-filtering, none of which the single-source sequential NetBox workload has. This empirically confirms Anthropic's own τ²-bench finding ("sequential single-call workflows do not benefit; ~8% more cost"). See §15 for the re-trigger conditions that would make a future re-investigation worthwhile, and §16 for what to do *instead* about the residual VLAN-100 latency.

The original projection in this doc (70s → 20-30s, §6.6) is **not supported** by the empirical data and should be read as a pre-spike hypothesis, not a finding.

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

## 14. Uncertainty register — RESOLVED (2026-06-15 spikes)

| Item | Pre-spike confidence | Spike outcome |
|---|---|---|
| MCP-adapter `BaseTool` instances bridge through PTC automatically | Medium | ✅ **CONFIRMED** (Spike 1) — auto camelCase naming, no adapter needed, real MCP round-trip |
| `FilterErrorRecoveryMiddleware` observes PTC-invoked tool errors | Low (predicted NO) | ✅ **CONFIRMED YES** (Spike 2) — prediction was wrong; middleware wraps `_arun()`, which PTC calls. No skill rewrite needed. |
| `deepseek-v4-flash:cloud` reliably emits valid JS against `tools.*` | Low | ◑ **MOOT** (Spike 3) — when *told* to (Spikes 1+2) it produced correct JS first try; but left to its own devices on a real query it **never chose `eval`**, so JS-fluency was never the bottleneck. The bottleneck is "the model has no reason to use PTC for this workload shape." |
| `RubricMiddleware`, sandbox middlewares could substitute for PTC | High | Unchanged — §9 comparison stands |
| QuickJS heap default (64 MB) sufficient for NetBox JSON | High | Unchanged — never approached the limit |
| Snapshot-restore preserves NetBox JSON across turns | High | Untested — irrelevant once adoption deferred |

New uncertainty surfaced during spikes:

| Item | Status |
|---|---|
| `langchain-quickjs` 0.2.0 (2026-06-12) dropped `skills_backend`, added `subagents: bool = True` default `task` bridge | Confirmed by installed-package inspection. The `subagents` param auto-exposes `task(...)` in JS when a `task` tool exists — set `subagents=False` to suppress (the spike scripts do). |
| Open issue #3926: PTC calls with `{ field: undefined }` fail Pydantic validation | Not hit in spikes (the model omitted keys rather than setting them `undefined`), but a real risk for MCP tools with optional fields if PTC is adopted later. Skill content would need to teach "omit, don't `undefined`." |

---

## 15. Decision and re-trigger conditions

**Decision (2026-06-22): defer adoption.** The mechanism works and is cheap to re-test later (Spikes 1+2 answered the structural "does it work" questions permanently — only Spike 3's "does it help *this* workload" is workload-dependent). For the current **single-source, sequential, 4-tool** NetBox agent, PTC adds latency (+13.7%) without the model even using it.

**Re-investigate PTC when any one of these becomes true** — each shifts the workload toward the fan-out / parallelism / large-result shapes where PTC's value actually lives:

| Trigger | Why it changes the math | Anchor |
|---|---|---|
| **Tool count crosses ~10** | Anthropic measured token savings of 20-40% starting at 10-49 tool definitions; below that, no benefit | Anthropic PTC docs (τ²-bench + production traffic) |
| **≥2 independent data sources queryable in parallel** | e.g. "check NetBox AND Grafana AND ServiceNow for device X" — PTC's `await Promise.all([...])` fan-out is the canonical win case. **This is the most likely trigger for a multi-source app.** | §3 (parallel decomposition pattern) |
| **Cross-source joins composed in code** | e.g. "correlate NetBox interfaces with Prometheus metrics" — stitch results in JS instead of round-tripping each intermediate through the model | §3 (recursive workflows) |
| **Large result sets needing pre-filtering** | filter/aggregate 100s of rows in JS before the model sees them — keeps fat payloads out of context | §1 (token-optimization rationale) |

**When a trigger fires, the re-investigation is ~½ day, not 1.5 days** — only a Spike-3-equivalent (does the model use it + is there a wall-time win) plus the steering work below. Spikes 1 and 2 do not need re-running.

**Critical caveat for any future adoption — the model must be *steered* to PTC.** In Spike 3 the model ignored `eval` entirely because nothing told it to prefer it: `NETBOX_SYSTEM_PROMPT` and the `netbox-mcp-filters` skill both teach direct `netbox_*` tool calls. Adoption is therefore not "drop in the middleware" — it requires:
1. A `netbox-mcp-ptc` skill (or system-prompt section) that explicitly tells the model: "for queries that fan out across ≥N independent lookups, use the `eval` tool to issue them in parallel via `Promise.all`."
2. Skill content teaching the `{ field: undefined }` avoidance pattern (issue #3926).
3. Re-running the model-matrix eval (per `2026-06-03_langsmith-evaluation-research.md`) with/without the middleware per model — smaller local models may regress where frontier models gain.

---

## 16. What to do *instead* about the residual VLAN-100 latency

Spike 3 confirmed PTC is **not** the fix for the slow VLAN-100 query (it ran at ~90s with PTC available and the model didn't use it; the 0.6 upgrade had already regressed this query class from a ~36s 0.5.6 baseline). The wall-time problem is real but unrelated to PTC. Better candidate levers, in order of cost:

1. **Suppress `SubAgentMiddleware`'s prompt addition (~½ day).** Workaround B (see `2026-06-14_deepagents-0.6-upgrade.md`) suppressed `BASE_AGENT_PROMPT` and removed `TodoListMiddleware`, but `SubAgentMiddleware`'s 2,144-char `TASK_SYSTEM_PROMPT` is **still appended** and may be feeding the over-exploration / search-hedging seen on negative-finding queries. Test: add `"SubAgentMiddleware"` to the `excluded_middleware` frozenset, re-run VLAN 100, measure. Cheap and user-facing.
2. **MCP-server-side composite query.** Add a NetBox MCP tool that performs "tenant → sites → VLANs → IP allocations" in one server-side round-trip. Collapses the whole multi-call decomposition into a single tool call — bigger win than PTC would have delivered, and no model-steering required.
3. **Teach parallel native tool calls in the skill.** The model already supports parallel tool calls when lookups are independent; the skill could explicitly instruct "fire independent lookups in the same turn." Achieves much of PTC's fan-out benefit without the middleware.

---

## 17. Spike artifacts

Reproducible scripts committed under `tests/spike/`:

- `spike1_mcp_ptc_bridge.py` — builds an agent with `CodeInterpreterMiddleware(ptc=<4 NetBox tools>)`, asks the model to make one trivial `eval` call, verifies the MCP round-trip.
- `spike2_ptc_error_recovery.py` — fires a deliberate invalid filter through PTC (naked + `try/catch` variants), verifies `FilterErrorRecoveryMiddleware` still produces a recoverable `TOOL_VALIDATION_ERROR`.
- `spike3_vlan_walltime.py` — runs the VLAN 100 query with and without the middleware on `deepseek-v4-flash:cloud`, reports wall-time delta and which mechanism (eval vs direct) the model chose.

Run any with `./venv/bin/python -m tests.spike.spike<N>_*`. They require the NetBox MCP server reachable at `localhost:8000` and `OLLAMA_*` / `NETBOX_*` env set (same as the app).
