# 2026-10-06: `__in` is silently ignored by NetBox — removed from the validator and the skill

**Status:** implemented (validator, skill, docs, local MCP server copy); session harness re-run
recorded below. Related: `2026-10-05_web-chat-persistence.md` (the thread that exposed it).

## What was observed

In the web chat, thread `3528fa85-c311-423c-a4f2-526fee3be904`, turn 3
(*"Across all Halvorsen Logistics PDUs, how many of the available power outlets are actually in
use?"*) took 283 s on a single model call. The call was slow because the preceding tool result
was 52,721 characters: `netbox_get_objects("dcim.poweroutlet", filters={"device_id__in": [...12
PDU ids...]})` had returned the first 200 power outlets **of every tenant**. NetBox had not
rejected the filter; it had dropped it. The model noticed the tenant mismatch, fell back to 12
per-device calls, and still answered 17/96 (the per-PDU totals were right; the sum was not).

The September run of the same ladder (`01a0e942-…`) never hit this because the model used the
list form `{"device_id": [...]}` there. Same question, two syntaxes, one of them a silent no-op.

## Live verification (NetBox 4.3.3, read-only `llm-agent` token, via the MCP tools)

| Object | `__in` filter | Returned | Bare-key list | Returned (correct) |
|---|---|---|---|---|
| `dcim.poweroutlet` | `device_id__in=[149,150]` | 200 (page 1 of all) | `device_id=[149,150]` | 16 |
| `dcim.device` | `id__in=[...]` | 141 (all devices) | `id=[...]` | 2 |
| `dcim.device` | `site_id__in=[25]` | 141 | `site_id=25` | 30 |
| `dcim.device` | `name__in=[...]` | 141 | `name=[...]` | 2 |
| `ipam.vlan` | `vid__in=[100,200]` | 94 (all VLANs) | `vid=[100,200]` | 26 |

No field class honours `__in`: not primary keys, not relational ids, not plain strings or
integers. NetBox's filtersets implement multi-value with `MultiValue*Filter` on the bare name
(repeated query parameters, `?device_id=149&device_id=150`); the MCP client produces exactly
that when the filter value is a list. Unknown query parameters are ignored by DRF, hence no 400.

## Why the wrong guidance existed

Trace `019e63c0` (earlier this year) showed the validator rejecting `__in`, `__regex`,
`__gt/gte/lt/lte` while the skill allowed them, costing a recovery cycle per attempt. The fix
then replaced the blacklist with a copy of the MCP server's `VALID_SUFFIXES`, which lists `in`,
and the skill was rewritten to call `__in` the canonical batch form because the MCP server's
tool description shows `{'id__in': [1,2,3]}` as a valid example. The comparison suffixes were
genuinely mis-blacklisted; `in` was not. Nobody checked the result set, only the status code.
Two places in the repo already had it right and were ignored: the system prompt line
*"NEVER use Django ORM lookups (e.g., __icontains, __in, __startswith)"* and
`FilterErrorRecoveryMiddleware`, whose `__in` branch already says "pass a Python list as the
value of the bare key".

## Changes

1. **Validator** (`src/tools/netbox_tools.py`): `in` removed from `VALID_SUFFIXES`; the comment
   now records the live evidence instead of the trace-019e63c0 rationale. `suggest_alternative`
   has an explicit `__in` branch: *"silently ignored by NetBox … pass a list as the value of the
   bare key"*. The `TOOL_API_ERROR` hint no longer says "even `__in` fails" on GFK fields.
   `device_id__in` now fails fast as a `TOOL_VALIDATION_ERROR` before reaching NetBox, and the
   recovery middleware's existing `list_form_filter` strategy applies.
2. **Skill** (`src/skills/netbox-mcp-filters/SKILL.md`, `examples.md`): the "BATCHING MULTIPLE
   IDs" section makes the list form the only form, shows the verification table, and says NEVER
   `__in`. The GFK section no longer claims the validator accepts `__in`. The suffix table drops
   the `in` row. The aggregate-pattern step 4 uses `{"<parent>_id": [ids]}`.
3. **Docs**: `AGENTS.md` §2 and `CLAUDE.md` suffix lists no longer end in `in` and say why.
4. **Tests**: `tests/test_filters.py` asserts `device_id__in` is rejected with the list-form hint
   and that `{"device_id": [149, 150]}` passes; `tests/conftest.py` sample filters drop `id__in`.
   `tests/test_filters.py`: 14 pass, 1 pre-existing failure (`test_recovery_attempt_tracking`,
   identical on master).
5. **MCP server (local copy only)**, `/home/ola/dev/rnd/mcp/testmcp/netbox-mcp-server`
   (upstream `netboxlabs/netbox-mcp-server` 1.0.0): tool description now shows the list form as
   valid and `id__in` as invalid; `in` removed from its `VALID_SUFFIXES`; its test updated (8
   pass). The diff is saved as `2026-10-06_netbox-mcp-server-in-suffix.patch` beside this note
   for an upstream report. The tool description matters because the model reads it on every call.

**Not changed:** `NETBOX_SYSTEM_PROMPT` (already correct), `FilterErrorRecoveryMiddleware`
(already correct), `src/agents/netbox_agent.py`.

## Session harness re-run (AGENTS.md convention after a skill/validator change)

Run: `SESSION_LABEL=in-lookup-fix ./venv/bin/python -m tests.eval.run_session`, default
11-turn Halvorsen ladder (turn 5 is the October outlets question verbatim), llama-server log
attached for context/decode. Output: `docs/traces/2026-10-06_netbox-session_in-lookup-fix.{md,json}`.

Like-for-like baseline: `2026-09-24_netbox-session_kvvram` (same 11 questions, same order, same
model and server flags). The `reorder` run of the same day used a different order and is not
comparable turn-by-turn.

| turn | question (short) | 2026-10-06 secs / tools / score | 2026-09-24 kvvram secs / tools / score |
|---|---|---|---|
| 1 | devices at HVL-SEA-DC1 | 132 / 2 / 1.0 | 130 / 2 / 1.0 |
| 2 | racks at HVL-SEA-DC1 | 34 / 1 / 1.0 | 32 / 1 / 1.0 |
| 3 | rack with most devices | 87 / 1 / 1.0 | 91 / 1 / 1.0 |
| 4 | outlets per PDU, PDU count | 131 / 7 / 0.0 | 127 / 3 / 0.0 |
| 5 | **outlets in use across all PDUs** | **177 / 1 / 0.5** | **195 / 9 / 0.5** |
| 6 | PDUs with any outlet in use | 27 / 0 / 0.5 | 32 / 0 / 0.5 |
| 7 | non-active power feeds | 72 / 1 / 1.0 | 57 / 1 / 1.0 |
| 8 | PDUs fed from a modelled feed? | 76 / 1 / 0.0 | 113 / 6 / 0.5 |
| 9 | host with one of two PSUs connected | 124 / 1 / 1.0 | 184 / 9 / 1.0 |
| 10 | HVL vs NC State feeds | 303 / 4 / 1.0 | 377 / 7 / 1.0 |
| 11 | summarise (unscored) | 150 / 0 / — | 213 / 0 / — |
| **total** | | **1,312 s / 20 tools** | **1,552 s / 39 tools** |

Context 9,353 → 55,426 tokens, decode 14.9 → 11.1 tok/s, no compaction, no truncation.

What the run shows about this change:

- **Zero `__in` attempts, zero `TOOL_VALIDATION_ERROR`, zero `TOOL_API_ERROR`** in 20 tool calls.
  The model used the list form four times unprompted (`device_id: [131..136]` twice,
  `device_id: [119..130]`, `site_id: [21, 22, 23, 24]`), each returning the correctly filtered set.
- **The October outlets question (turn 5) is now one tool call**: the list-form
  `dcim.poweroutlet` query with `fields=[id, name, device, cable]`, 177 s. In the web thread on
  2026-10-05 the same question cost a 52,721-char unfiltered page, a 283 s model call and 12
  per-device follow-up calls; in the September baseline it cost 9 calls. The per-PDU breakdown
  (8 / 8 / 1 in use, nine PDUs empty) matches the reference.
- **The scores did not move, and the misses are not filter misses.** Turns 4, 5, 6 and 8 lose
  points because the model scoped "Halvorsen Logistics PDUs" to **site HVL-SEA-DC1 (6 PDUs,
  48 outlets)** instead of the **tenant (12 PDUs, 96 outlets)**: turn 4 answered "6 PDUs", turn 5
  "17 of 48", turn 8 "all 6 PDUs uncabled" (substantively right, wrong population; the baseline's
  0.5 vs today's 0.0 is the judge's call on the same kind of answer). The three dcim openers
  anchor the conversation on the site, and every later turn inherits that scope. The identical
  pattern in the September baseline (0.0 / 0.5 / 0.5 on turns 4–6) confirms it is the
  question-order confound the harness docstring warns about, not a regression. The `reorder` run,
  which asks the PDU question first, scored turn 1 at 1.0 with all 12 PDUs.
- Net effect of the change on this ladder: same correctness, **half the tool calls (20 vs 39)**,
  **15% less wall time**, and the failure mode that produced the 283 s call can no longer occur
  silently.

**Not run:** the AGENTS.md §6 matrix convention (`EVAL_FORCE_RERUN=1` on `deepseek-v4-flash:cloud`)
needs Ollama Cloud quota and several hours; it is still owed before merge if the project wants
the single-question numbers re-baselined for the `__in` rejection.

