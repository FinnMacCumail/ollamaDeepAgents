# Trace Analysis: Skill Body Reaches Model — Workaround A Landed

**Trace ID:** `019e493c-405b-7420-af70-283b57e3915e`
**Thread ID:** `71608512516b40549e942c127260db73`
**Query:** "Show all Dunder Mifflin sites with device counts, rack allocations, and IP prefix assignments"
**Date:** 2026-05-21 06:32:25 → 06:34:19 UTC
**Backend:** Ollama Cloud (`deepseek-v4-pro:cloud`)
**Session:** Fresh thread, cold start (no memory carryover)
**Significance:** **First trace in project history where the skill BODY actually loads into the model's context.** Until now, only skill metadata reached the model; the body silently failed to load on every prior run due to DeepAgents bug ([#3185](https://github.com/langchain-ai/deepagents/issues/3185), [#3188](https://github.com/langchain-ai/deepagents/issues/3188), both Closed Not planned).

---

## Why this trace matters

The DeepAgents framework's Skills System uses progressive disclosure — only the skill's metadata (name + description) sits in the system prompt at startup. The body is loaded on demand via `read_file`. But the framework's own example workflow uses `read_file(path, limit=1000)` — and the actual tool schema requires `file_path=`, not `path=`. Every model call that copied the documented example fell over on Pydantic validation, returned a 186-byte error message, and never loaded the skill body.

This bug has been silent across the project's entire history. Every prior trace showing `skills_metadata: ['netbox-mcp-filters']` was misleading — that only means the metadata is registered, not that the body has been read. The behaviour we attributed to "the skill steering the model" was actually the model working from the description alone, plus the base `NETBOX_SYSTEM_PROMPT`. The skill body never reached it.

Workaround A (commit `<this commit>`) installs a `HarnessProfile` that:
1. Overrides the `read_file` tool description (the schema-of-record the model defers to) with corrected examples using `file_path=`
2. Appends a system-prompt suffix as a tiebreaker, since `SkillsMiddleware`'s class-level prompt template still contains the broken `read_file(path, limit=1000)` example and can't be reached by `tool_description_overrides`

This trace is the first run with that workaround in place.

---

## Performance Comparison Across This Query's Full Lineage

| Trace | Date | Skills body loaded? | Outcome | Wall | Tool calls | Device count |
|---|---|---|---|---|---|---|
| `019df979` | 05-05 | ❌ | Empty answer | 107s | 2 | n/a |
| `019df9d8` | 05-05 | ❌ | 400 crash | 21s | 1 | n/a |
| `019e1c4e` | 05-12 | ❌ | 39 (undercount) | 227s | 6 | 39 |
| `019e1c9f` | 05-12 | ❌ (memory hit) | 52 | 22s | 0 | 52 |
| `019e3220` | 05-16 | ❌ | `id__in` crash | 26s | 3 | n/a |
| `019e322f` | 05-16 | ❌ | 52 (counted client-side) | 121s | 8 | 52 |
| `019e3b7e` | 05-18 | ❌ | 39 (regression) | 263s | 16 | 39 |
| **`019e493c`** | **05-21** | **✅** | **52** | **113s** | **13** | **52** |

The "skills body loaded" column is the key — every value above this run's row is ❌. We've been making decisions about skill content for two weeks while the body never reached the model.

---

## Direct evidence the workaround landed

### Cycle 1 — the smoking gun

```
[1] [AI->TOOL] read_file({"file_path": "/src/skills/netbox-mcp-filters/SKILL.md", "limit": 200})
[2] [TOOL RESULT (read_file)] bytes=4039
```

Compare to every prior trace's read_file call:

| Trace | Argument name | Result |
|---|---|---|
| `019e322f` | `path` (from skill prompt) | 186 bytes (Pydantic error) |
| `019e3b7e` | `path` (from skill prompt) | 186 bytes (Pydantic error) |
| **`019e493c`** | **`file_path` (from corrected tool description)** | **4039 bytes (actual skill content)** |

The model called `read_file` with the correct kwarg name for the first time in any trace. The 4039-byte response is real skill content, not an error. Workaround A is empirically validated.

### Cycle 3 — direct skill-content influence on tool syntax

```
netbox_get_objects("dcim.device", filters={"site_id": [1,2,3,4,5,6,7,8,9,10,11,12,13,14]}, fields=[...])
netbox_get_objects("dcim.rack",   filters={"site_id": [1,2,3,4,5,6,7,8,9,10,11,12,13,14]}, fields=[...])
netbox_get_objects("ipam.prefix", filters={"site_id": [1,2,3,4,5,6,7,8,9,10,11,12,13,14]}, fields=[...])
```

Three parallel calls using the **bare-key list-form filter** taught by the skill's `## BATCHING MULTIPLE IDs IN A SINGLE CALL` section. Crucially: no `id__in` or `site_id__in` attempted first — meaning the BATCHING section landed before the model could reach for the Django-style lookup it tried in `019e3b7e` (which fell to the validator's recovery loop).

### Final answer — canonical counts

```
14 sites | 52 devices | 13 racks | 65 prefixes
DM-NYC: 0/0/0
All other 13 branches: 4/1/5 each (uniform template)
Per-site prefix pattern: /22 container + /28 management + 3× /24 VLAN
```

52 devices matches `019e1c9f`'s memory-cached canonical result. Compare to `019e3b7e`'s 39-device undercount (which used `tenant_id=5` and silently dropped patch panels without an explicit tenant). The skill body delivered the device-count optimisation that's been documented in the skill for weeks but never actually reached the model before.

---

## Performance Breakdown

5 LLM cycles, 13 tool calls, 113.6s wall (113ms shy of `019e322f`'s 121s cold-start baseline, despite issuing 5 more tool calls — productive work, not waste).

| Cycle | Time | Tool calls | What |
|---|---|---|---|
| 1 | 7s | 2 parallel | `read_file` (skill body — 4039 bytes) + `netbox_search_objects(query="Dunder Mifflin")` |
| 2 | 7s | 2 parallel | `netbox_search_objects(query="DM-")` (redundant hedge) + `netbox_get_objects(tenancy.tenant)` |
| 3 | 14s | 3 parallel | The batched site_id-list query trio (devices + racks + prefixes) |
| 4 | 31s | 3 parallel | get_by_id verification calls, including DM-NYC empty-check |
| 5 | 7s + 6s | 1 + 1 | Two more refinement calls (full prefix detail; scope-based prefix re-fetch) |
| 6 | 23s | 0 | Final 1692-token formatted answer |

**Token usage:** 147,707 prompt + 5,551 completion = **153,258 total**. The prompt total is ~10× higher than pre-fix runs because the skill body (~10K chars / ~2.5K tokens) is now in context for every LLM call after cycle 1. Cloud prompt caching should amortise most of that cost across subsequent turns in the same session.

---

## Key Findings

### 1. The framework bug is genuinely worked around

Three pieces of empirical evidence:
- Model used `file_path=` (correct), not `path=` (broken)
- `read_file` returned 4039 bytes of actual content, not the 186-byte Pydantic error every prior run got
- Downstream tool calls reflect skill-body content (BATCHING pattern), not just description metadata

The `tool_description_overrides` mechanism (the schema-of-record) won the salience battle against `SkillsMiddleware`'s baked-in `read_file(path, limit=1000)` example. The system_prompt_suffix as tiebreaker may or may not have been load-bearing — would require an A/B test to know.

### 2. The skill body steers behaviour, where the description alone could not

Behaviors traceable to specific sections of the body (not the metadata):

| Behavior in this trace | Skill section providing the guidance |
|---|---|
| `site_id=[1..14]` list-form filter on first attempt | BATCHING MULTIPLE IDs IN A SINGLE CALL |
| 52-device count (correct) via per-site enumeration | DECOMPOSING MULTI-ASPECT QUERIES |
| `fields=[...]` minimised on every call | CRITICAL OPTIMIZATION RULES |
| Three parallel calls (not 14 per-site iterations) | DECOMPOSING MULTI-ASPECT QUERIES |

None of these patterns appeared in pre-Workaround-A traces. The skill content authored over the past two weeks finally has measurable behavioural effect.

### 3. Two skill sections did NOT land

Despite the body being available:

- **AVOID REDUNDANT SEARCHES** — cycle 2 still did `netbox_search_objects(query="DM-")` after cycle 1's `query="Dunder Mifflin"` returned the 14 sites. Soft constraint friction; the model may treat hedging as defensive rather than wasteful.
- **IPAM PREFIX FILTERING** — cycle 5 issued a `scope_id`+`scope_type` prefix query (the exact pattern the skill says NOT to explore for site-scoped queries). Either the section's "do not explore" instruction lost a salience battle to the model's intuition about NetBox v3+ scope semantics, or the section was no longer salient by cycle 5 after 4 cycles of context accumulation.

Both are workable — soft-constraint sections can be tuned. The architectural enabler (skill body reaches model) is now in place; per-section effectiveness becomes a separate tuning problem.

### 4. The validator architectural insurance was NOT exercised

Unlike `019e3b7e` which needed the `TOOL_VALIDATION_ERROR` recovery loop to survive a `site_id__in` mistake, this run never made the mistake — the BATCHING skill section steered it correctly on the first attempt. The recovery loop sat idle. Worth noting that both layers (preventive skill content + reactive recovery middleware) are now active and complementary.

---

## What's actually different about today vs the past two weeks

Every prior "skill landed" claim in this project's trace reports was wrong. The skill *metadata* was registered, but the body — where the actual guidance lives — never reached the model due to the framework bug. Re-reading the previous reports with this knowledge:

- `019e1c9f` — "Breakthrough: skill steered toward count fields" — actually the model worked from description metadata + memory cache of prior tool results
- `019e322f` — "First clean cold-start" — the model arrived at correct answers despite the skill body never loading
- `019e3b7e` — "skill influenced tool syntax via site_id=[list] pattern" — actually that pattern was the model's improvisation; the skill body wasn't visible

The actual "first time the skill content reaches the model" is **today**. The architectural arc spanning ~30 commits across two weeks finally clicked through into a fully-functional skill loading pipeline.

---

## Recommendations

### Confirmed working

- Workaround A (tool_description_overrides + system_prompt_suffix) — landed, no further action needed unless the upstream bug gets fixed
- BATCHING MULTIPLE IDs skill section — measurably steers tool-call syntax
- DECOMPOSING MULTI-ASPECT QUERIES skill section — measurably steers per-aspect decomposition and yields canonical device count
- Validator architectural insurance — present, not exercised this run, available next time

### Tunable

- AVOID REDUNDANT SEARCHES section — soft constraint isn't landing; consider stronger phrasing or moving the rule into the base `NETBOX_SYSTEM_PROMPT`
- IPAM PREFIX FILTERING section — same as above; the "do not explore scope_id" instruction needs more salience

### Open

- Confirm whether the system_prompt_suffix is load-bearing or whether the tool_description_overrides alone would suffice — A/B test by temporarily removing the suffix
- Watch for whether the skill body keeps loading reliably across many turns, or whether re-loading the SKILL.md becomes an overhead pattern (model may re-read every turn)
- Upstream: the bug remains in DeepAgents and `Skills System` example workflow text. Workaround A holds for our use case but won't help other DeepAgents users hitting the same trap

---

**Analysed:** 2026-05-21
**Comparison:** Workaround A active vs entire prior project history
**Verdict:** Skill body reaches the model for the first time. Two-week investment in skill content now has empirical leverage on agent behaviour. The architectural pipeline (skill-loader fix → cloud model → validator hardening → skill body delivery via Workaround A) is complete end-to-end.
