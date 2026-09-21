# Week in Review — v5 Benchmark and Local Frontier Inference (15–21 Sep 2026)

**Date:** 2026-09-21
**Status:** ✅ Completed — both workstreams delivered; two published claims corrected in place
**Purpose:** Record what the week of 2026-09-15 → 2026-09-21 produced across both repos, and — the part
that is *not* recoverable from any single commit — the two claim-and-correction arcs that span multiple
runs, plus the process lessons they carry.
**Scope note:** this is deliberately not a commit digest (the README's own "What to Document" rules out
"changes already in git commits"). What earns a document is the cross-run synthesis: a finding published,
contradicted by the next run, and corrected.
**Related:** `2026-09-15_netbox-benchmark-v5-expansion-design.md` (sizing + taxonomy),
`2026-09-15_netbox-v5-data-enrichment-research.md` (the seeded data),
`2026-09-16_v5-question-authoring-plan.md` (authoring rules); `docs/traces/2026-09-1*` (the seven runs);
`scripts/serve_qwen4exp.sh` (the tuned server); rtf-research ADR-0037, ADR-0038.

---

## TL;DR

Two workstreams ran back to back: **scaling the evaluation harness from 6 to 90 questions** (15–18 Sep),
then **establishing that a 176B model runs locally on this hardware** (19–21 Sep).

**Both produced a headline finding, and both headline findings were published, contradicted by the next
run, and corrected in place.** That pattern — not either result on its own — is the week's main content.

| | |
|---|---|
| Period | 2026-09-15 19:35 → 2026-09-21 01:51 (six days) |
| Commits | **43** — `ollamaDeepAgents` 36, rtf-research 7 |
| Lines | ~**8,110** added, 7 deleted |
| Commit mix | 14 `feat`, 10 `fix`, 5 `docs`, 2 `ops`, 2 `eval`, 1 `security`, 1 `audit`, 1 `docs+feat` |
| llama.cpp | **zero** commits of ours — rebuilt and consumed as a dependency, not modified |

An unusually high share of the `fix` work corrects **my own prior claims**, not code.

---

## 1. Stratified benchmark v5 (15–18 Sep)

### The problem

The harness ran on **six** questions, where the 95% CI on a pass rate is ≈**±0.32–0.40** — wide enough to
swallow any routing-sized effect. Difficulty was not an axis at all, yet model-handoff routing rests on a
premise never tested: *that query difficulty predicts which model should handle a query.*

### What was built

**An additive data island.** A new tenant (Halvorsen Logistics) seeded beside the untouched demo instance —
70 devices, 42 prefixes, 31 VLANs, 14 circuits, 28 VMs, plus deliberately planted defects. No demo object
was mutated, so v4 reference answers stay true. Writes used a seeder token; the agent's token stayed
read-only. Ground truth was **computed from live data**, not from the blueprint's targets — a distinction
that immediately paid off: D1 diverged (3 active devices without a primary IP, but 4 across all statuses),
so the answer key records **both scopes** and requires the question to say which it means.

**A 90-question dataset**, verified from `tests/eval/dataset_v5.py` as exactly:

| Axis | Distribution |
|---|---|
| Tier | simple 30 / medium 30 / advanced 30 |
| Answer type | count 21 / list 21 / value 18 / boolean 12 / explanation 9 / absence 9 |
| Island | hvl 57 / demo 33 |
| Anchor | set 80 / single 10 |
| Domain | dcim 27 / ipam 12 / virt 12 / circuits 10 / power 10 / tenancy 10 / changelog 9 |

The binding design rule: **difficulty is the retrieval mechanism, never the subject matter** (simple = one
object/one filter; medium = one join or aggregation; advanced = ≥2 hops or absence reasoning). Every tenant
appears in every tier (19/19/19 and 11/11/11) — otherwise tenant name silently proxies for difficulty, which
would defeat the entire point of stratifying. Island balance was chosen **over** the raw 60/30 ratio for
that reason.

**Two harness fixes were prerequisites**, both silent-failure class: `ensure_dataset_*` was *create-only*,
so editing the source had no effect once the dataset existed; and the results reader could return before the
primary `correctness` score landed.

### Results — four model families, 90 items each, 0 errors across 540 runs

| Model | Correctness | Completeness | Entity cov. | Tool calls | Advanced tier |
|---|---|---|---|---|---|
| deepseek-v4-pro | **0.933** | 0.944 | 0.831 | **4.93** | 0.850 |
| kimi-k2.6 | 0.911 | 0.961 | 0.866 | 5.76 | **0.900** |
| deepseek-v4-flash | 0.906 | 0.956 | 0.885 | 6.27 | 0.800 |
| qwen3.5:397b | **0.817** | 0.889 | 0.761 | 7.42 | 0.667 |

### Arc 1 — the "ceiling" that wasn't

**The claim (17 Sep, commit `091bf12`, off the kimi run).** Three families inside a 2.7pp band, every
pairwise CI spanning zero (flash−pro −0.028 [−0.088, +0.033]; flash−kimi −0.006; pro−kimi +0.022), and
**69 of 90 items solved by all three** with only 3 defeating all three. Recorded in ADR-0037 as a ceiling.
I went further and predicted further runs would be **"uninformative by construction."**

**The retraction (19 Sep, commit `4bbc12c`, off the qwen3.5:397b run).** The very next run falsified both
statements, producing the **first significant results the benchmark has generated**:

```
pro   - qwen   +0.117  [+0.038, +0.196]   SIGNIFICANT
kimi  - qwen   +0.094  [+0.016, +0.173]   SIGNIFICANT
flash - qwen   +0.089  [-0.007, +0.185]   just short
```

Adding **one** unrelated family moved saturation from **69/90 (77%) to 59/90 (66%)** and the all-defeating
core from 3 items to 2. Ten questions that had looked inert — `vcpu-aggregation`, `ip-mask-mismatch`,
`orphaned-cable`, `prefixes-without-vlan`, `tenant-group-size`, `vms-without-primary-ip` among them — were
discriminating all along; the measurement simply lacked the model spread to reveal it.

> **Corrected claim:** the set resolves capability gaps of roughly **9pp and above** on 90 paired items, and
> cannot resolve the **~3pp** separating flash, pro and kimi. That is a sample-size limit behaving correctly
> — not a ceiling.

**The transferable lesson: saturation is a property of the models you test, not of the questions.** Read a
high saturation figure as a statement about your model sample, and test it with something unlike the rest
before declaring a set exhausted.

### What survives regardless: efficiency

Correctness could not separate the top three, but **tool calls did, cleanly** — pro 4.93 / kimi 5.76 /
flash 6.27, with pro inside the advanced budget **29/30 against flash's 21/30**. For routing, **cost per
query discriminates where correctness cannot.** `057bd35` then made `anchor` an *authored* field after a
regex-recovered version of the same claim failed: with authored labels the separation is ~6× (single-anchored
1/30 → 3% GraphQL use, set-anchored 41/240 → 17%), and 29 of 30 single-anchored model-items stayed on MCP.
The earlier null was a classifier artefact, not a property of the data.

### The defect class the audit could not catch

A full **90/90 factual audit** against live NetBox (`5433ea3`) found **zero** factual errors — preconditions
established first, with all ten object-type totals matching exactly so a mismatch would have been a real
error rather than data drift.

It could not have caught the **three reference-*wording* defects** found separately (`a4f0e49`, `9646ebf`),
each of which penalised a **correct** answer:

- `deletion-cascade` — all three models answered "7 request IDs" and were **literally correct**; the
  reference said only "one cascading removal". Three independent models converging was the tell.
- `tenantless-instance-wide` — the site is `name='MDF'` / `slug='ncsu-065'`; a model was penalised for using
  the display name.
- `cross-estate-power-compare` — the ANSWER dropped the "data centre" scope the QUESTION set.

Re-scoring raised flash to 0.911, kimi to 0.928, pro to 0.944 — which **widens** qwen's gap rather than
explaining it. **An ambiguous reference is more dangerous than a wrong one, because nothing in the harness
flags it.** All three were found by investigating model *disagreements*; the automated name/slug sweep found
nothing new.

### Runtime and cost

| Run | Scale | Wall clock |
|---|---|---|
| 09-15 timing-probe (v4) | 6 q × pair | 12m44s |
| 09-16 v5-smoke | 15 × flash | 3m45s |
| 09-17 v5-b2 | 30 × flash | 9m34s |
| 09-17 v5-b3 | 45 × flash | 21m32s |
| 09-17 v5-2model | 90 × 2 | ~40 min per model |
| 09-17 v5-distant (kimi) | 90 × 1 | 1h49m (~73s/item) |
| 09-18 v5-qwen | 90 × 1 | 51 min (~34s/item) |

**Marginal cost ≈ $0** — Ollama Cloud Pro is flat-rate. The $15–30/run figures in the design doc are
explicitly hypothetical pay-per-token contrasts.

One process note from `091bf12`: the early-abort rule said kill kimi at 126s/item on a 4-item sample. It was
overridden on quality grounds and the rate settled to ~73s/item, finishing in 1h49m against a projected
3.2h. **The 4-item projection was dominated by startup.**

---

## 2. Local frontier inference (19–21 Sep)

**Qwen3.8-Flash-Next** (`qwen4_exp`: 125B MoE, ~6B active per token, plus a **51B n-gram lookup table** — a
table, not a network, so it costs memory rather than computation; ~176B total) against the real NetBox agent
on 2× RTX 2080 Ti (21.1 GiB VRAM) + 376 GB RAM.

**The premise that changed.** Every prior local candidate had failed the **simple** tier, which made
model-handoff routing moot — there was nothing to hand off *from*. This one went 3/3 on one question per
tier, then **11/12** on a stratified 12-question sample. **Local capability is no longer the constraint;
cost is.**

### Three measured configuration wins

| Change | Effect | Why |
|---|---|---|
| `--numa isolate -t 10` | **+56%** decode (13.71 → 21.38 tok/s) | llama.cpp defaults `--numa` to *disabled*, so threads straddle both NUMA nodes. `-t 10` (one node's physical cores) beats `-t 20`; unpinned `-t 40` collapses to 5.89 |
| `-c 131072 --no-kv-offload` | **8/12 → 11/12** correct; **3 → 0** lost to context | Uses the resource in surplus — 376 GB RAM vs 21 GB VRAM. Costs ~37% decode, buys 4× context. Verified in 20 seconds |
| `-b 2048 -ub 2048` | **3.8×** prefill isolated; **1.23×** end-to-end | llama.cpp only copies CPU-resident experts to GPU once a microbatch amortises the PCIe transfer; default `-ub 512` never reaches it |

At `-c 32768` the run suffered two hard overflows and **one silent truncation** — the worse failure, because
the model then answers confidently from data it no longer has.

### Four documented dead ends

Recorded in the serve-script header so they are not rediscovered:

- **`--spec-type ngram-simple`** — **163 drafts proposed, ZERO accepted**, −24% decode. Mechanical, not a
  tuning failure: it needs an exactly-repeating 12-token run to draft the next 48, and a table of *distinct*
  device names has almost none. No `--spec-ngram-*-size-n` value fixes a 0% acceptance rate.
- **Draft-model speculation** — `common/speculative.cpp` throws on vocab mismatch; no qwen4exp-vocab draft
  model exists.
- **Prompt caching** — already working: median LCP similarity **0.956**, 75 of 76 requests warm, **~85%
  served from cache**. A research pass had been briefed on the opposite assumption.
- **Alternative runtimes** — MoE CPU decode runs at ~19% of STREAM bandwidth; `GGML_NUMA_STRATEGY_MIRROR`
  exists in ggml's enum *and nowhere else in the source*; KTransformers needs Ampere+ and AMX this Cascade
  Lake host lacks; vLLM/SGLang cannot host 112 GB on 21 GiB of VRAM.

### Final measured state

| | baseline (`ctx128k`) | `+ -b 2048 -ub 2048` |
|---|---|---|
| correct | 11/12 | 11/12 |
| context failures | 0 | 0 |
| wall time | 155.1 min | **126.3 min** (1.23×) |
| tool calls | 88 | 77 |
| full v5 extrapolation | ~19.4 h | **~15.8 h** |

**Decode is now the bottleneck** — roughly two thirds of the remaining 126 min is the model writing at
~4–5 tok/s, and nothing currently available moves it. **Reading is cheap; writing is the wall.**

### Arc 2 — a projection that was 20% optimistic

The 3.8× prefill gain was modelled to ~105 min / ~12.6 h by applying it to *all* 187,272 prompt tokens. But
~85% were already cache-served, so only the genuinely-new remainder and each question's cold first turn ever
accelerate. A 3.8× isolated measurement became **1.23× end-to-end**.

The figure was labelled "*modelled, not measured*" precisely because it accounted for ~100% of observed wall
time and was too neat — **the hedge was right, the number still needed correcting.** Watching the forecast
drift mid-run (534 s at n=2 → 613 s at n=11) confirmed that declining to call it at n=2 was correct: the
baseline's own per-question range was 185–1,862 s.

---

## 3. Security and operations

- **Read-only enforced at the credential layer** (`1535d47`), not just tool design. The agent had been
  authenticating with a **write-enabled superuser token**, so the read-only guarantee rested entirely on tool
  design — a bug, a new tool, or prompt injection could in principle have written. A dedicated `llm-agent`
  identity (non-superuser, non-staff, `view` on all 156 object types, `write_enabled=false`) now means NetBox
  itself refuses. Verified end to end: REST read 200, both GraphQL tools return data, MCP connects,
  `POST /api/dcim/sites/` → **HTTP 403**. The two pre-existing superuser tokens are untouched for
  admin/seeding work.
- **Repaired a corrupted job-queue Valkey AOF** (`adf9535`) that had left netbox-worker down for days with
  `/api/status/` returning 500. `valkey-check-aof --fix` truncated 235 corrupt trailing bytes; everything
  before the corruption was preserved. Side effect: Custom Scripts became viable again for seeding.
- **`scripts/serve_qwen4exp.sh`** — the week's operational deliverable. Every flag annotated with its
  measurement, including the dead-end block and the caveat that `-ub 2048` raises peak prefill VRAM and was
  verified to fit alongside `-c 131072` on 21 GiB, so it should not be raised blindly.

---

## 4. Process lessons

Three errors were recorded rather than quietly fixed, and they share a shape.

**1. Generalising from n=3 similar models.** The ceiling claim, plus a forecast ("uninformative by
construction") stated with unwarranted confidence that the next run falsified. Corrected by testing something
*unlike* the rest.

**2. Testing the expensive hypothesis first.** Convinced that oversized tool payloads were the problem, a
per-result size cap was built into the MCP wrapper. It cost two ~87-minute runs and was reverted.

- It shipped **inert**: `langchain_mcp_adapters` declares `response_format="content_and_artifact"`, so tool
  coroutines return a `(content, artifact)` **tuple**, and `_measure_result` handled only `str`/`list` —
  three oversized results, **zero** cap firings. The unit test fed it a bare string, validating an
  *assumption about* the adapter rather than its contract. **A test written from the same misunderstanding
  as the code cannot catch that misunderstanding.**
- Fixed, it shipped **mis-sized**: 60,000 chars ≈ 63% of the working budget, still permitting a truncation
  while turning a question the baseline answered in **3 calls / 141 s** into a **65-minute retry loop**.

The cheap hypothesis — *"is the window simply too small?"* — cost **20 seconds** to test and made the whole
exercise unnecessary. The expensive one was tested first because the answer had already been decided.

**3. A measurement sized by `chars/4`.** Dense JSON tokenises ~1.9× worse, so a test prompt intended at
~9,000 tokens was ~43,000, and the first benchmark ran ~2 hours instead of ~18 minutes.

---

## 5. Where the narrative actually lives

Worth knowing for anyone working in this repo: **the trace files under `docs/traces/` are pure score tables.
None contains a conclusion, a wall-clock figure, a cost figure, or the word "ceiling."** Every narrative
finding, every timing, and both the ceiling claim and its retraction live in the **git commit messages** that
added each trace; cost lives only in `2026-09-15_netbox-benchmark-v5-expansion-design.md`.

`git log` is the primary narrative source for this project, not the docs tree. This document exists partly to
make that recoverable without it.

One filing quirk that follows from the same thing: the qwen3.5:397b run that overturned the ceiling is in
`docs/traces/2026-09-18_netbox-benchmark-v5_v5-qwen.md` — a file **dated 09-18 but added by a commit dated
09-19**. There is no 09-19 trace file.

---

## 6. State at close, and open items

Both repos in sync with their remotes, clean trees. Documentation verified live on GitHub Pages. No
background jobs running. Server shut down.

**Open, deliberately not actioned:**

- The **tenant-null aggregation bug** — all three models report the *unfiltered* total on an instance-wide
  tenant-null question. Reproducible and family-independent. Held at the user's request.
- **`uv.lock` untracked** in `ollamaDeepAgents`.
- **`sysctl kernel.numa_balancing=0`** needs root; llama.cpp warns the current setting impairs performance.
- The **GraphQL routing-tightening plan** (anchor-count rule, four edit sites) remains pending from an
  earlier session and is independent of this week's work.
