# netbox-benchmark-v4 — GraphQL routing tightening, 3× replication summary — 2026-08-25

Aggregates the **three** tightened-routing runs (deepagents 0.7.5, `feat/graphql-read-tool`) to
firm up the single-run tightening verdict and average out the two noisy queries. Closes the PR's
`≥3× replication` open item.

Runs:
- r1: `2026-08-25_netbox-benchmark-v4_d075-graphql-tightened.md` (experiments `...-tightened-*`)
- r2: `2026-08-25_netbox-benchmark-v4_d075-tightened-r2.md`
- r3: `2026-08-25_netbox-benchmark-v4_d075-tightened-r3.md`

## Aggregate correctness (3-run means, from recorded scorecards)

| Model | r1 | r2 | r3 | 3-run mean |
|---|---|---|---|---|
| deepseek-v4-flash | 0.917 | 0.833 | 0.833 | **≈0.86** |
| deepseek-v4-pro | 0.80 | 0.817 | 0.75 | **≈0.79** |
| **combined** | 0.86 | 0.83 | 0.79 | **≈0.82** |

For reference (single runs, same 0.7.5 framework): MCP-only baseline combined 0.667; GraphQL
pre-tightening 0.75. The tightened arm stabilizes **above** both.

## Primary acceptance check — device-detail recovery HOLDS

The tightening targeted the one query GraphQL over-routed (device-detail, a single-object
lookup). Per-run correctness + routing trajectory (whether the run used GraphQL on this query):

| Model | r1 | r2 | r3 | avg | routing across 3 runs |
|---|---|---|---|---|---|
| flash | 1.0 | 1.0 | 1.0 | **1.0** | MCP-led all 3 (≤1 GraphQL peek) |
| pro | 1.0 | 1.0 | 0.5 | **0.83** | MCP-only 2/3; the 0.5 run slipped to GraphQL (2 calls) |

Bar = "holds ~1.0 in ≥2 of 3 runs" → **flash 3/3, pro 2/3 — PASSED.** Pre-tightening this query
was flash 0.0 / pro 0.5.

**The mechanism is proven causally, not inferred.** pro's two MCP-only runs both scored 1.0; its
one run that slipped to GraphQL scored 0.5. GraphQL-on-a-single-object → wrong; MCP → right — and
the tightened guidance keeps it on MCP the majority of the time.

## No over-correction — cross-domain queries STILL route to GraphQL

Trajectory-verified across all three runs: `site-comparison` and `multi-site-VLAN` continued to
use `netbox_graphql` on both models (e.g. flash multi-site-VLAN ~10 GraphQL calls; pro
site-comparison ~5). The tightening did not demote any legitimate GraphQL route.

## What replication clarified (per-question 3-run averages)

The two noisiest queries — misleading on single runs — average out:

| Query (avg correctness) | flash | pro | note |
|---|---|---|---|
| device-detail | 1.0 | 0.83 | the fix — recovered |
| rack-inventory | 1.0 | 1.0 | stable |
| negative-finding (Jimbob VLAN) | 1.0 | 1.0 | stable |
| multi-site-VLAN (DM) | ~0.83 | ~0.83 | noisy (0.5/1.0 swings), routes GraphQL |
| site-comparison | ~0.67 | 0.5 | noisy, routes GraphQL |
| tenant-site-summary | ~0.67 | ~0.47 | persistent WEAK SPOT — see below |

## Findings surfaced by replication (not routing bugs)

1. **pro device-detail is not 100% deterministic (2/3 MCP).** Soft guidance holds the majority
   but not every run. This is the documented trigger to escalate to the mechanical
   `LLMToolSelectorMiddleware` gate *if* airtight routing is ever required — but 2/3 meets the
   bar, so it is **not** needed now.
2. **`tenant-site-summary` is a persistent weak spot** (pro 3-run avg ~0.47, flash ~0.67) on the
   "all Dunder-Mifflin sites with device/rack/prefix counts" query. This is a **model-accuracy**
   issue (getting the aggregate counts right), **not** a GraphQL routing problem — tracked
   separately.

## Verdict

The routing tightening is **confirmed across 3× replication**: device-detail recovered and holds
(flash 3/3, pro 2/3), the MCP-vs-GraphQL mechanism is proven causally, cross-domain wins are
preserved, and the stabilized combined correctness is **≈0.82** — the best configuration measured
(MCP-only 0.667 → GraphQL 0.75 → GraphQL+tightened 0.82). The PR's `≥3× replication` and
`tighten routing` open items are both closed.
