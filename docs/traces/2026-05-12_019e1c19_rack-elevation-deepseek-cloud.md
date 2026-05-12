# Trace Analysis: Rack Elevation on deepseek-v4-pro:cloud

**Trace ID:** `019e1c19-f6c5-7480-8e1b-28c03578de33`
**Query:** "Get rack elevation for rack Comms closet in site DM-Akron"
**Date:** 2026-05-12 12:12:04 → 12:16:08
**Backend:** Ollama Cloud (`deepseek-v4-pro:cloud`, 1.6T MoE / 49B active / 1M ctx)
**Comparison targets:**
- DeepAgents + llama.cpp (Qwen3-14B) — trace `019df947` (2026-05-05)
- Claude SDK (Anthropic API) — reference output captured 2026-04-20

---

## Overview

This trace is the first run of the same rack-elevation query against `deepseek-v4-pro:cloud` after the backend switch (commit history: `b922dd4`, `63f1fb3`, plus the cloud-switch wiring landed today). The point of the run is to test the "is the model the bottleneck?" hypothesis raised in the post-mortem of trace `019df9d8` (where the local 14B regressed and crashed on a relational filter, and trace `019df979` where it stalled on a multi-aspect query producing an empty answer).

---

## Performance Metrics

| Metric | DeepAgents 14B (`019df947`) | DeepAgents + deepseek-cloud (`019e1c19`) | Claude SDK |
|---|---|---|---|
| Total wall time | ~32s | **~244s (4 min)** | ~10s |
| LLM calls | 3 | **5** | ~2 |
| Tool calls | 2 | **8** | 2 |
| Cumulative tokens | ~12K | **~15K** | unknown |
| Final-call output tokens | ~360 | **681** | ~600 |
| Patch panel 2U handled | ❌ no diagram | **✅ correct** | ❌ shows U12 empty |
| Utilization math | n/a | **5U occupied / 7U free** | 4U / 8U (off by 1) |

---

## Execution Pattern

### Tool-call sequence

1. **LLM 1 → Tool 1** (21s): `dcim.site` lookup — `filters={name: 'DM-Akron'}, fields=['id', 'name', 'slug']` → returns `id=2`. Two-step pattern textbook.
2. **LLM 2 → Tool 2** (27s): `dcim.rack` lookup — `filters={name: 'Comms closet', site_id: 2}, fields=['id', 'name', 'site', 'u_height', 'width', 'facility_id', 'status']` → returns rack id=1, u_height=12, width=19".
3. **LLM 3 → Tools 3+4 (parallel)** (58s):
   - `dcim.device` filter `rack_id: 1`, fields include `position`, `face`, `device_type`, `role` (limit=50) → 4 devices
   - `dcim.rack` `get_by_id(1)` → full rack metadata (tenant=Dunder-Mifflin, role, location, etc.)
4. **LLM 4 → Tools 5–8 (parallel 4-way)** (29s): `dcim.devicetype` `get_by_id` for each of the 4 device-type IDs (8, 6, 7, 10) → returns `u_height` per type. **This is the step Claude SDK skipped.**
5. **LLM 5 → final response** (96s): formatted markdown tables + ASCII rack diagram, 681 output tokens.

**Total LLM time:** ~231s (matches ~244s overall). The final formatting call alone is 96s = ~7 tok/s — generation is the bottleneck, not tool calls.

### Pattern observations

- 🟢 **Two parallel tool batches.** Steps 3 and 4 each fan out concurrent tool calls. The local 14B has never done this in any prior trace. This is a model-tier capability difference, not a prompt change.
- 🟢 **Targeted device-type lookups.** The model recognised that to render an accurate elevation diagram it needed each device's u_height — not just the rack's u_height. It dispatched all 4 lookups in parallel rather than serialising.
- 🟡 **Wall time dominated by generation.** Cloud network round-trips on the tool calls are negligible vs the 96s spent generating the final response.

---

## Output Quality Comparison

### deepseek-v4-pro:cloud final answer

```
## Rack Elevation: Comms closet — DM-Akron

| Rack | Site | Height | Width | Status | Tenant |
|------|------|--------|-------|--------|--------|
| Comms closet | DM-Akron | 12U | 19" | Active | Dunder-Mifflin, Inc. |

┌─────────────────────────────────────────────┐
│ U  │ Device                    │ Type              │
├─────────────────────────────────────────────┤
│ 12 │ ─── Patch Panel ───────── │ Panduit 48-Port   │
│ 11 │ ─── (2U) ──────────────── │ Patch Panel       │
│ 10 │ dmi01-akron-sw01          │ Cisco C9200-48P   │
│  9 │                           │                   │
│  …                                                  │
│  4 │ dmi01-akron-rtr01         │ Cisco ISR 1111-8P │
│  …                                                  │
│  1 │ dmi01-akron-pdu01         │ APC AP7901        │
└─────────────────────────────────────────────┘

Summary: 4 devices installed across 12U (5U occupied, 7U free)

| U     | Device            | Role          | Model              | Height |
|-------|-------------------|---------------|--------------------|--------|
| 1     | dmi01-akron-pdu01 | PDU           | APC AP7901         | 1U     |
| 4     | dmi01-akron-rtr01 | Router        | Cisco ISR 1111-8P  | 1U     |
| 10    | dmi01-akron-sw01  | Access Switch | Cisco C9200-48P    | 1U     |
| 11–12 | *(unnamed)*       | Patch Panel   | Panduit 48-Port    | 2U     |
```

### Claude SDK final answer (reference, 2026-04-20)

```
Rack Elevation: Comms closet (DM-Akron)

Rack Details:
    Site: DM-Akron
    Rack ID: 1
    Status: Active
    Height: 12U

Device Layout (Top to Bottom):
U12 [  EMPTY  ]                       ← INCORRECT (patch panel spans U11–U12)
U11 [█] 48-Port Patch Panel (Panduit) - Front
U10 [█] dmi01-akron-sw01 (Cisco C9200-48P) - Front
U09 [  EMPTY  ]
…
U04 [█] dmi01-akron-rtr01 (Cisco ISR 1111-8P) - Front
…
U01 [█] dmi01-akron-pdu01 (APC AP7901) - Front

Summary:
    Total devices: 4
    Occupied rack units: 4U                ← INCORRECT (should be 5U)
    Available rack units: 8U               ← INCORRECT (should be 7U)
    Utilization: 33%                       ← INCORRECT (should be 41.7%)
```

### Local 14B (Qwen3) final answer

> "The rack 'Comms closet' in site DM-Akron has an elevation of **12U** (rack units). Status: Active. Facility ID: Not assigned (null). Rack ID: 1."

No device list, no diagram, no positions. The model stopped at rack metadata.

---

## Key Findings

### 1. Quality: cloud beats both prior baselines

deepseek-v4-pro:cloud is the only run of the three to:
- Render a true rack elevation (the 14B never even tried)
- Correctly handle the multi-U patch panel (Claude SDK got this wrong)
- Produce internally consistent occupancy math (5U occupied / 7U free / 41.7% utilisation)

The "is the model the bottleneck?" hypothesis holds for output quality. The architecture (two-step pattern, field projection, conversation memory, skills) was working — what was missing was a model with the planning depth to chain `device → device_type → u_height` lookups.

### 2. Tool-calling sophistication is a model-tier capability

Parallel tool batching (two batches of 2 and 4 in this run) is an emergent capability not exhibited by the 14B at all. Same prompt, same DeepAgents framework, same MCP tools — only the model changed.

### 3. Speed is the new tradeoff

| | Local 14B | Claude SDK | deepseek-cloud |
|---|---|---|---|
| Wall time | ~32s | ~10s | **~244s** |

Cloud frontier models are not necessarily fast. The 96s final formatting call (~7 tok/s) is the dominant cost. Claude SDK's API is in a different latency tier — Anthropic ships dedicated inference hardware tuned for low-latency interactive chat; Ollama Cloud's deepseek deployment is preview-grade.

### 4. Skills still not loading

`outputs.skills_metadata` is `[]` despite the `title:` → `name:` frontmatter fix landing in commit `63f1fb3`. The agent's correct behaviour in this trace comes from the system prompt alone, not the loadable skill. Worth a separate investigation — likely a `skills_path` resolution issue when running from the repo root (`src/skills` is a relative path passed to `create_deep_agent`).

---

## Recommendations

### Confirmed

- **Cloud frontier model resolves the 14B's correctness regressions.** Continue using `deepseek-v4-pro:cloud` for testing complex queries.
- **Architectural work was not wasted.** Two-step pattern, field projection, memory, middleware all carry over and work cleanly with the larger model.

### Open questions

- **Latency budget.** ~4 minutes for an interactive query is too long for production use. Worth profiling whether `num_predict` reduction, `temperature` tuning, or a smaller cloud model (e.g. `gpt-oss:120b-cloud`) gets to a usable wall time.
- **Hybrid routing.** The local 14B was 7× faster than the cloud model on this query, even if its answer was much weaker. A `--cloud` flag selecting per-query (or by query-complexity heuristic) gives the best of both. Out of scope for this trace, but the obvious next architectural step.
- **Skills loader gap.** Root-cause why `skills_metadata` is still empty post-fix.

### Hardware planning input

If a local equivalent were available (e.g. multi-H100 setup capable of running a 600B+ MoE), the wall-time gap would invert: local would beat cloud on latency. This trace is direct evidence supporting the "feasibility lab" rationale in the Telegram post — the model class is what unlocks the quality, and once that's confirmed, the question becomes whether on-prem hardware investment is justified.

---

## Conclusion

The cloud-model switch produces qualitatively better output than both prior baselines on a non-trivial query. It also exposes a new bottleneck (cloud generation latency) that the local stack didn't have. The 14B was failing on capability; the cloud is succeeding on capability but failing on responsiveness. Hybrid routing or larger local hardware are the two paths forward.

---

**Analysed:** 2026-05-12
**Comparison:** deepseek-v4-pro:cloud vs DeepAgents llama.cpp 14B vs Claude SDK
**Verdict:** Architecture validated; model class drives quality; cloud latency is the new constraint
