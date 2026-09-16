# netbox-benchmark-v5 — Dataset Expansion Design (sizing + difficulty taxonomy + coverage)

**Date:** 2026-09-15
**Status:** 🟡 Design — spec for building `netbox-benchmark-v5`; not yet built
**Purpose:** Decide how far to expand the evaluation dataset (currently **6 examples**), on what statistical
basis, covering what query taxonomy — so the benchmark can (a) produce trustworthy A/B numbers and
(b) serve the upcoming **model-handoff routing** feature, which needs difficulty-graded examples.
**Related:** `2026-08-10_langchain-ecosystem-vs-netbox-cloud-platform.md` (§6 routing is the consumer of this
dataset); `tests/eval/dataset_v4.py` (current 6-example set); `docs/traces/2026-08-25_*` (the replication
that exposed the small-n variance); rtf-research `docs/methods/benchmarking.md`.

---

## TL;DR

**6 examples is too small on three independent grounds** — statistical (n=6 → 95% CI **±0.32–0.40**),
coverage (whole NetBox domains untested), and stratification (one example per category = no per-tier signal
for routing). **Target: ~90–150 examples, stratified 30–50 per difficulty tier (simple/medium/advanced),**
built from a ~22-archetype coverage checklist. Two "free" power levers to adopt alongside: a **paired test**
(same questions across arms) and **breadth-over-replication** (more questions beats more repeat runs). One
hard prerequisite: **the demo data is too thin for the advanced tier** — dataset expansion and data
enrichment go together.

---

## Why 6 is too small

| Problem | Evidence |
|---|---|
| **Statistical** | Correctness is a proportion; 95% CI half-width = z·√(p(1−p)/n). At **n=6 → ±0.32–0.40**; n=30 → ±0.18; n=100 → ±0.08–0.10; n=385 → ±0.05. This is *exactly* the ±0.15–0.25 swing we saw all session, and why everything needed 3× replication. |
| **Coverage** | The 6 queries touch DCIM/IPAM/Tenancy but miss whole operational domains: **circuits, cable-tracing/connectivity, capacity (free IPs / free rack units / next-available), change-history, wireless, VMs, power**. |
| **Stratification** | **Exactly one example per category** — so every category is a single data point. No per-domain and no per-difficulty signal, which is precisely what model-handoff routing must be evaluated on. |

## Part 1 — Sizing (statistical rationale)

Correctness = fraction correct = a proportion → CI half-width **E = z·√(p(1−p)/n)** (z=1.96);
sample size **n = z²·p(1−p)/E²**.

**Single-arm confidence (worst case p=0.5 / realistic p=0.8):**

| n | ±CI @ p=0.5 | ±CI @ p=0.8 |
|---|---|---|
| 6 | ±0.40 | ±0.32 |
| 30 | ±0.18 | ±0.14 |
| 50 | ±0.14 | ±0.11 |
| 100 | ±0.10 | ±0.08 |
| 200 | ±0.07 | ±0.055 |
| 385 | ±0.05 | ±0.04 |

**Detecting a difference between two arms** (two-proportion, α=0.05, power=0.80), N **per arm**: a **0.20**
gap needs **~60–100/arm**; a **0.10** gap needs **~200–400/arm**. With 6 questions nothing short of a
near-total blowout is detectable.

**Two free power levers (adopt both):**
1. **Paired test (McNemar), not two independent proportions.** Arms answer the *same* questions, so pairing
   eliminates question-difficulty variance — reclaims substantial power at zero cost. (Anthropic's
   recommended technique for model evals.)
2. **Breadth beats replication.** Repeat runs cap at reducing estimator variance by only **2/3**; adding
   distinct questions has no ceiling (SEM falls as 1/√n). Keep replication to *clean each question's score*
   (question-level mean over ~2–3 runs), but spend the growth budget on **more questions**.

**Sizing targets:**

| Tier | Size | Buys |
|---|---|---|
| Dev / iteration | ~30–50 | Fast error analysis, catch big breakage (CI ±0.14–0.18, directional) |
| **Confident claim / regression gating** | **~100 min; 200–400 to gate a ~0.10 gap** | n=100 → CI ±0.08–0.10; detect 0.20 gap ~60–100/arm |
| **Per-difficulty stratum (routing)** | **30/tier floor; 50–100/tier to gate a routing decision** | 30 → ±0.14–0.18 directional; 50–100 → ±0.08–0.11 |

**Recommendation: ~90–150 total, stratified 30–50 × {simple, medium, advanced}.** Enough for real per-tier
routing signal, affordable to run, clean growth path to 200–400 if gating small gaps later.

## Part 2 — Difficulty taxonomy (the core of model-handoff routing)

Grading axis: **how many anchor objects / joins / computations does the answer require, and does it reason
about absence?** This *is* the routing decision.

| Tier | Shape | Routes to | Examples |
|---|---|---|---|
| **SIMPLE** | one object, one field, one call | **local model** | "serial of dmi01-akron-rtr01?"; "what site is rack R1 in?" |
| **MEDIUM** | filtered list / one related summary / a simple count | **the ambiguous middle** (where routing accuracy is most testable) | "active devices in Akron"; "how many interfaces on X?"; "VLANs in site Y" |
| **ADVANCED** | multi-hop joins, aggregation, **negative-findings**, capacity math, cable trace | **always escalate** (heavier model + GraphQL subagent) | "active devices with no primary IP"; "IP utilization per prefix"; "trace this cable"; "IPs per tenant across sites" |

**Objective discriminator:** NetBox's MCP filter API **forbids multi-hop filters** (`device__site_id` fails →
must two-step). So any cross-model *filter* is inherently a multi-call plan — a clean, mechanical
SIMPLE-vs-ADVANCED label for ground truth. **Negative-finding and capacity-math queries are where cheap
models fail** (they hallucinate absence or skip enumeration) → weight these heavily in the escalation test.

## Part 3 — Coverage checklist (~22 archetypes × domains × tiers)

Build the set from these; use demo-dataset naming (Akron / DM) so answers are computable against the live
instance. (Anchor `<X>` placeholders to be filled with verified objects at build time.)

**SIMPLE (single-object lookup)**
1. DCIM: serial + asset tag of `dmi01-akron-rtr01`
2. IPAM: which device/interface is IP `<X>` assigned to (device-by-IP)
3. DCIM: rack + position of `dmi01-akron-sw01`
4. IPAM: description + status of prefix `<X>`
5. Circuits: provider + circuit-ID string for circuit `<X>`

**MEDIUM (filtered list / related summary / count)**
6. DCIM: list active devices at site Akron (two-step resolve → filter)
7. DCIM: interface count on `dmi01-akron-rtr01`, how many enabled
8. IPAM: VLANs in site DM-Akron (VID + name)
9. IPAM: IP addresses in prefix `<X>` with DNS names
10. Virtualization: VM count + statuses in cluster `<X>`
11. DCIM: all devices of device-type/model `<X>` across sites
12. Change/history: what changed on `dmi01-akron-rtr01` in last 7 days

**ADVANCED (join / aggregation / negative / capacity / trace)**
13. Audit (negative): active devices with no primary IP
14. Capacity: IP utilization % of prefix `<X>`
15. Capacity: free rack units per rack at Akron
16. Capacity: next available /27 in aggregate `<X>` (or next IP in a prefix)
17. Connectivity/trace: trace cable from `dmi01-akron-rtr01` `<iface>` to far-end device+port
18. Cross-domain: all IPs for tenant `<T>` across sites, grouped by site
19. Cross-domain: circuits per provider `<P>` and where each terminates
20. Aggregation: device counts per site, by device role
21. Audit: interfaces on Akron devices with no IP assigned (matches NetBox workshop demo)
22. Connectivity: devices+interfaces attached to VLAN `<N>`

*Stretch (optional):* power draw per panel; devices missing a module/inventory item; decommissioned-status audit.

## Part 4 — Data-enrichment prerequisite (gating for the advanced tier)

> **Detailed in `2026-09-15_netbox-v5-data-enrichment-research.md`.** A live audit refines the
> recommendation below: enrich **additively** (a new, fully-modelled tenant in unused address space with a
> planted-defect answer key) rather than modifying the demo objects. Mutating Dunder-Mifflin/NC State would
> invalidate 5 of the 6 v4 reference answers. The research also flags prerequisites: a queue Valkey repair,
> `CHANGELOG_RETENTION=0`, a baseline snapshot, and a read-only agent token.

The NetBox **demo dataset** is thin: ~39–72 devices, **essentially no device-level IP assignments**, little
cable topology. Several ADVANCED archetypes (cable trace #17, IP-utilization #14, "no primary IP" #13,
"interfaces without IPs" #21) have **no rich, gradable answers** on it today. So *"test against a larger
NetBox sample"* is a **precursor**, not a nice-to-have. Two paths:
- **(A) Enrich the current instance** — script device-level IP assignments, a few cabled paths, richer
  prefixes, so the advanced archetypes have real answers. Keeps the standard demo naming (answers stay
  computable via MCP/GraphQL for ground truth).
- **(B) Point at a fuller instance** — more work to stand up; only if a realistically-sized fixture is wanted.

**Recommend (A):** targeted enrichment of the existing demo instance, scripted + reproducible, sized to make
the ~8 advanced archetypes answerable. Ground truth stays free (query the instance via MCP to compute
expected answers).

## Part 5 — Cost & runtime to build and run

**Dollar cost (running):** **≈$0 marginal** — Ollama Cloud **Pro is flat-rate**, not per-token. (For contrast,
on pay-per-token a 90-question pair run ≈ 25–30M tokens ≈ ~$15–30/run at flash-class rates — free here.)

**Runtime (MEASURED — timing probe, 2026-09-15):** the current 6-question set × production pair (flash + pro),
sequential (`EVAL_MAX_CONCURRENCY=1`), on master/0.7.5. Trace:
`docs/traces/2026-09-15_netbox-benchmark-v4_timing-probe.md`.

- **Total wall-clock: 12m44s (764s)** for 12 question-runs (6 questions × 2 models) → **~64s per
  question-run all-in** (includes agent/MCP startup, the two LLM judges, and sequencing overhead — ~31%
  above the root-run-only mean of ~44s).
- **Per-model wall-clock/question:** flash mean 59s (14s–209s), pro mean 29s (9s–59s).
- **Tokens/question-run: ~155K** (flash 165K, pro 145K) → **~1.86M tokens for the 6-q pair run**.
- **Huge per-question spread** — flash ranged 14s/61K tokens (simple) → **209s/330K tokens (advanced,
  GraphQL-heavy)**. Advanced queries dominate both time and tokens.

**Extrapolation (measured ~64s + ~155K tokens per question-run):**

| Dataset × arms × replication | Question-runs | Wall-clock (seq, conc=1) | Tokens | $ (flat-rate) | $ (pay-per-token ref) |
|---|---|---|---|---|---|
| 6 q × pair × 1 (the probe) | 12 | **12m44s (measured)** | 1.86M | $0 | ~$1–2 |
| **90 q × pair × 1** | 180 | **~3.2 hrs** | ~28M | **$0** | ~$14–28 |
| 90 q × pair × 2 | 360 | ~6.4 hrs | ~56M | $0 | ~$28–56 |
| 150 q × pair × 1 | 300 | ~5.3 hrs | ~46M | $0 | ~$23–46 |
| 30 q × 1 model × 1 (dev subset) | 30 | ~32 min | ~4.6M | $0 | ~$2–5 |

**This corrects the earlier estimate downward:** I'd guessed ~4–6 hrs for a 90-q pair run; measured is
**~3.2 hrs** (my ~100s/question guess was high — it's ~64s all-in). Caveat on the *mix*: the current 6-set
skews advanced, so its ~155K-token average is near the high end; a v5 with ~1/3 simple queries will likely be
**cheaper per question on average**, so these are conservative (upper-bound) extrapolations.

**Levers:** `EVAL_MAX_CONCURRENCY=2–3` would cut wall-clock roughly proportionally (untested — NetBox MCP is
stdio, may bottleneck); the local llama.cpp cheap tier is free + off-quota (slower).

**Quota:** the binding practical constraint. A 9-model × 6-question sweep (~54 question-runs) hit **429
exhaustion** this session; a 90-question × 2-model run is **~180 question-runs (>3×)** → will span multiple
rolling-quota windows. The runner's **skip-completed + resume** logic handles this (start it, let it resume
across windows), but a full sweep is not one clean shot. Two levers: raise `EVAL_MAX_CONCURRENCY` (currently
1 — NetBox MCP is stdio; test 2–3), and use the **local llama.cpp backend** for the cheap tier (free, no
quota, slower).

**The efficiency payoff of expanding:** at n=90 a *single* run already gives ~±0.10 CI, so replication drops
from 3× toward **1–2×**. Breadth substitutes for repetition — steady-state run cost stays comparable to today
while the numbers become trustworthy.

**Build effort:** each example needs question + `expected_entities` + a **ground-truth-verified**
`reference_answer` (queried against live NetBox) + category + difficulty tier. ~10–20 min/example by hand →
~15–30 h for 90; **but mostly agent-driftable** (batch-query NetBox via MCP to author + verify from the
checklist) → a few focused sessions, plus the Part-4 data enrichment.

## Part 6 — Proposed v5 shape + build plan

- **`tests/eval/dataset_v5.py`** — `BenchmarkExampleV5` adds a `difficulty: Literal["simple","medium","advanced"]`
  field (v4 has `category` only). ~90–150 examples, 30–50/tier, spanning the Part-3 checklist. Reuse the v4
  reference-answer discipline (verified, non-fabrication-hardened).
- **`tests/eval/run_matrix_v5.py`** — extends the v4 runner with **per-difficulty leaderboard breakdown**
  (mean correctness per tier per model) — the metric routing is judged on — and a **paired** model-vs-model
  comparison. Keep `EVAL_VARIANT` / resume / `EVAL_FORCE_RERUN`.
- **Data enrichment script** (Part 4A) — reproducible, applied before authoring advanced examples.
- **Sequencing:** (1) enrich data → (2) author + ground-truth examples by tier → (3) wire the per-tier runner
  → (4) baseline run → (5) this becomes the harness the model-handoff routing is evaluated on.

## Out of scope
- The model-handoff routing feature itself (separate PRP) — this dataset is its *evaluation substrate*.
- Retiring v4 — keep it; v5 is a superset with the difficulty axis.

## Sources
- Statistical sizing: two-proportion power + Wald/Wilson CI; Anthropic *A statistical approach to model evals*
  (paired test, 2/3 resampling ceiling); Hamel Husain evals FAQ; LangSmith evaluation-concepts; `evalstats`.
- NetBox taxonomy: NetBox features/models docs; NetBox Labs MCP + AI-agent-workshop + Reports blogs; GraphQL
  examples; `netbox-community/customizations`. Full citations in the research threads that produced this doc.
