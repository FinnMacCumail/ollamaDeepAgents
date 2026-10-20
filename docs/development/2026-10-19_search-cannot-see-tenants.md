# 2026-10-19: The search tool could not see tenants, and a count question fetched the children

**Trigger.** Web-chat thread `70a4c0891d4c43a4ae6c4c4f184d8502`, one turn, 17:39 local:
*"How many power outlets does each Halvorsen Logistics PDU provide, and how many PDUs are
there?"* Correct answer (12 PDUs, 8 outlets each), zero errors, **377 s and 9 tool calls** for
a question NetBox answers in one call of 2.7 KB. LangSmith run `7743a8f5-e902-4de3-a675-2ba539302924`.

## Where the 377 seconds went

| phase | tool calls | model calls | time | what happened |
|---|---|---|---|---|
| cold start | — | 1 | 48 s | 8.8k-token prefix at 223 tok/s; expected |
| working out what "Halvorsen Logistics" is | 6 | 5 | ~100 s | `netbox_search_objects` twice → eight empty lists; then tried it as a `dcim.manufacturer`, a `dcim.devicetype` model, listed all manufacturers, searched "PDU"; seventh call: `tenancy.tenant name__ic` → id 14 |
| fetching the data | 2 | 2 | 227 s | all 68 tenant devices with `device_type` expanded (72,945 chars → 32k-token prompt, 117 s), then all 96 outlets (46,443 chars → 49k-token prompt, 110 s) |

Model time 364 s of 377; tools 15 s. Per-call numbers from the web layer's usage ledger:
prefill 223 tok/s cold, 55–57 tok/s on the small follow-ups (cache-dominated), decode 14.6.

## Root cause one: `netbox_search_objects` searched a fixed list that had no tenants

The MCP server's `DEFAULT_SEARCH_TYPES` was devices, sites, IP addresses, interfaces, racks,
VLANs, circuits and VMs. An organisation name matches none of them, so the search returns a
row of empty lists with HTTP 200 — which the model reads as "no such object" and starts
guessing object classes. Not specific to this thread:

| run | search calls | returned nothing | questions affected | top empty queries |
|---|---|---|---|---|
| 2026-10-17 full v5 | 35 | **26** | 16 | "Halvorsen" ×9, "Halvorsen Logistics" ×5, "Halvorsen" as provider ×2 |
| 2026-10-18 full v5 | 24 | **18** | 14 | "Halvorsen Logistics" ×7, "Halvorsen" ×5 |

That is the largest remaining wasted-call category — bigger than the GraphQL grammar errors
fixed on 2026-10-18 — and it was invisible to that analysis because an empty search is a
*successful* call that sat in the "empty result" bucket.

## Root cause two: the child list instead of the parent's count

The filters skill's parent-count table already lists `power_outlet_count` on `dcim.device`.
Verified live: `dcim/devices/?tenant_id=14&role=pdu&fields=id,name,site,power_outlet_count`
→ 12 rows, 2,746 chars, both halves of the question. The model fetched 120 KB of children
instead; the two prefills that followed cost more than everything else in the turn.

## Changes

1. **MCP server (local copy, commit `d7809d9`)**: `DEFAULT_SEARCH_TYPES` gains
   `tenancy.tenant`, `circuits.provider`, `dcim.manufacturer`; the server's own test updated and
   one added; diff saved as `2026-10-19_netbox-mcp-server-search-default-types.patch` beside
   the `__in` and change-log ones for the upstream report. Verified through the wrapped tool:
   a default search for "Halvorsen Logistics" now returns the tenant (id 14) first.
2. **Filters skill**: new *RESOLVING A TENANT, PROVIDER OR MANUFACTURER NAME* (one
   `tenancy.tenant name__ic` call, then `tenant_id`; an empty global search is not evidence of
   absence; never guess another object class) and *PER-PARENT COUNTS: FILTER THE PARENT, READ
   THE COUNT* (the PDU example, right and wrong, with the measured cost).
3. **System prompt**: one line for each.

## Gate: the session harness, same 11 questions and order as 2026-10-06 and 2026-10-18

`docs/traces/2026-10-19_netbox-session_search-types.{md,json}`. Seconds / tool calls / score:

| turn | 2026-10-06 | 2026-10-18 | 2026-10-19 (this change) |
|---|---|---|---|
| 1 devices at HVL-SEA-DC1 | 132 / 2 / 1.0 | 73 / 2 / 1.0 | 74 / 2 / 1.0 |
| 2 racks | 34 / 1 / 1.0 | 24 / 1 / 1.0 | 25 / 1 / 1.0 |
| 3 rack with most devices | 87 / 1 / 1.0 | 55 / 4 / 1.0 | 37 / **1** / 1.0 |
| 4 outlets per PDU | 131 / 7 / 0.0 | 240 / 7 / 1.0 | 221 / **4** / 1.0 |
| 5 outlets in use | 177 / 1 / 0.5 | 171 / 2 / 1.0 | 168 / 1 / 1.0 |
| 6 PDUs with any outlet in use | 27 / 0 / 0.5 | 117 / 12 / 0.5 | **22 / 0 / 1.0** |
| 7 feeds not active | 72 / 1 / 1.0 | 210 / 3 / 1.0 | 139 / 1 / 1.0 |
| 8 PDUs fed by a modelled feed | 76 / 1 / 0.0 | 84 / 1 / 1.0 | 75 / 1 / 1.0 |
| 9 hypervisor power supplies | 124 / 1 / 1.0 | 132 / 3 / 1.0 | 99 / 1 / 1.0 |
| 10 feeds DC vs branch | 303 / 4 / 1.0 | 212 / 1 / 1.0 | 232 / 4 / 0.5 |
| 11 summary | 150 / 0 | 126 / 0 | 156 / 0 |
| **total** | 1,312 s / 20 / 7.0 | 1,444 s / 36 / 9.5 | **1,248 s / 16 / 9.5** |
| context at turn 10 · decode | 54k · 12.1 | 77k · 14.0 | 88k · 13.3 |

**What the change did, visibly.** Turn 4 opened with one `netbox_search_objects("Halvorsen")`
that returned the tenant, and the next call used `tenant_id: 14` — one call to resolve the
name where the web-chat turn needed six and yesterday's run needed several. Turn 10 searched
with `object_types=["tenancy.tenant", "dcim.site"]`, the form the skill now recommends. The
ladder's fastest total and fewest calls of the three runs, at the same correctness as
yesterday. Turn 6 answered from context in 22 s where yesterday's run re-queried twelve times
— that is the planning variance the harness documents, in this run's favour.

**What it did not do.** Turn 4 still fetched the tenant's 68 devices (context 10.6k → 31.7k)
rather than filtering by `role=pdu` and reading `power_outlet_count`; it then read the
outlet count off the device type's outlet templates, which is correct and cheap, but the
device list before it was the expensive step. The per-parent-count guidance is in the skill;
the model applied the first half (count field, not child list) and not the second (filter
the parent). Turn 10 scored 0.5 against 1.0 yesterday on the same four-call plan; judge
noise on a comparison question, left as measured. One run; the full harness is the
measurement for the call count.

## Full 90-question v5 run on this change (2026-10-20)

Experiment `llamacpp-qwen3.8-flash-next-UD-Q4_K_XL-v5-search-types-full-ba60270e`, trace
`docs/traces/2026-10-20_netbox-benchmark-v5_search-types-full.md`. Same server, harness,
dataset, evaluators and judge as the 17 and 18 October runs.

| | 2026-09-23 | 2026-10-17 server | 2026-10-18 filters | **2026-10-20 search** |
|---|---|---|---|---|
| wall, first question to last | 6.78 h | 5.30 h | 5.26 h | **5.14 h** |
| agent time, sum of 90 | 19,345 s | 14,396 s | 14,248 s | **13,782 s** |
| mean / median per question | 215 / 153 s | 160 / 120 s | 158 / 113 s | **153 / 97 s** |
| simple / medium / advanced mean | 109 / 206 / 331 | 97 / 168 / 216 | 91 / 173 / 211 | **77** / 163 / 220 |
| questions faster than the previous run | — | 73 of 90 | 48 of 90 | 54 of 90 |
| correctness | 0.906 | 0.922 | 0.928 | 0.917 |
| completeness | 0.944 | 0.944 | 0.978 | 0.972 |
| tool calls per question | 5.52 | 4.88 | 4.99 | **4.49** |
| errors | 0 | 0 | 0 | 0 |

**Where the calls went** (every tool call classified, 18 vs 20 October):

| category | 18 Oct | 20 Oct |
|---|---|---|
| tool calls in total | 449 | **404** |
| searches · returned nothing · of those with default types | 24 · 18 · 12 | 17 · **6** · **0** |
| searches that found something | 6 | **11** |
| tenant resolved via `tenancy.tenant` | 48 | 46 |
| tenant looked up as provider / manufacturer / device type | 4 | 1 |
| GraphQL queries · schema introspections | 53 · 30 | **17 · 6** |
| GraphQL rejected by NetBox · caught by the pre-check | 25 · 7 | **4** · 7 |
| `_id: null` used · REST validation errors · REST 400s | 13 · 0 · 0 | 15 · 2 · 1 (`role=hypervisor`, slug is `hypervisor-host`) |
| `power_outlet_count` used | 0 | 2 |
| tool results over 20k characters · total chars | 59 · 5.0M | 58 · 4.9M |

**Reading.** The targeted pattern is gone: no default-type search came back empty, and the
provider/manufacturer guessing fell from 4 calls to 1. The run is the fastest of the four on
every aggregate — wall, sum, mean, median, simple tier, calls per question — with correctness
and completeness inside the day-to-day judge spread of the two previous runs (five and nine
questions moved in each direction). The simple tier gained most (91 → 77 s mean) because its
questions are one lookup after a name resolution, and the resolution is now one call.

The unexpected part is GraphQL: usage fell from 53 queries and 30 introspections to 17 and 6,
and NetBox-side rejections from 25 to 4. With the tenant resolvable in one call the model
mostly stayed on the REST path, which is the cheaper one for these questions; the GraphQL
expansion the 18 October change had triggered reversed itself. Tool-result size did not move
(58 results over 20k characters, 4.9M characters in total): the per-parent-count guidance was
followed twice and the whole-list habit remains the next lever.

**Four runs in sequence, same questions.** Agent time 19,345 → 14,396 → 14,248 → 13,782 s;
calls per question 5.52 → 4.88 → 4.99 → 4.49; correctness 0.906 → 0.922 → 0.928 → 0.917. The
server change bought the first 26%; the two guidance changes together another 4% of time and
8% of calls, with the second one doing the work the first one's call-count projection had
promised.
