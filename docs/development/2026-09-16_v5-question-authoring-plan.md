# netbox-benchmark-v5 — Question Authoring Plan

**Date:** 2026-09-16
**Status:** 🟡 Plan — authoring not started; two harness fixes are prerequisites
**Purpose:** Specify exactly how to author the ~90 v5 questions so they score *validly* under the
existing four evaluators, and so difficulty measures reasoning rather than topic.
**Inputs:** a live audit of how the harness consumes each dataset field, and an online survey of
benchmark-authoring practice (ABC checklist, text-to-SQL annotation-error studies, AmbigQA, (QA)²,
SQuAD 2.0, contrast sets, Hamel Husain, Anthropic eval guidance, HealthBench, Miller's error bars).
**Related:** `2026-09-15_netbox-benchmark-v5-expansion-design.md` (sizing + taxonomy),
`2026-09-15_netbox-v5-data-enrichment-research.md` (the data these questions run against).

---

## 0. The finding that changes the most

**Four of the six existing v4 examples contain `expected_entities` that their own ground-truth
`reference_answer` cannot match.** Scoring each v4 reference *as if it were the agent's answer*:

| # | category | self-score | unmatchable entity |
|---|---|---|---|
| 1 | tenant-site-summary | 0.950 | `68 prefixes` (reference says "68 **IP** prefixes") |
| 2 | device-detail | 0.889 | `no IP addresses` (reference says "IP addresses: NONE") |
| 4 | multi-site-vlan | 0.895 | `no devices`, `no IP addresses` |
| 6 | site-comparison | **0.500** | `DM-Nashua`, `DM-Akron`, `DM-Scranton` — the v4 override never names them |

A *perfect* answer cannot score 1.0 on those four. Some of the v4 entity-coverage numbers quoted in
earlier write-ups are therefore depressed by an authoring bug, not by model behaviour.

**Rule A1 (non-negotiable): every `expected_entities` string must be a literal, normalised substring
of its own `reference_answer`.** A three-line check over all 90 enforces it.

## 1. How the harness actually consumes fields (verified)

| Field | Consumed by | Exact behaviour |
|---|---|---|
| `question` | target fn, both judges | `inputs["question"]`; a missing key raises `KeyError`. **Must be unique** — `rescore_v4.py` keys ground truth by question string, so duplicates silently collide |
| `expected_entities` | `entity_coverage`, `completeness_judge` | substring match after `re.sub(r"[^a-z0-9 ]+", "", s.lower())` |
| `reference_answer` | `correctness_judge` only | judge scores **contradiction, not completeness**; returns `None` (not 0.0) if absent |
| `category` | leaderboard grouping | also the key `_REFERENCE_OVERRIDES` uses — do not reuse that pattern at n=90 |
| `answer`, `tool_call_count` | produced by the target | `tool_calls` score is a **raw count**, not 0–1 |

**Normalisation traps, measured against the real function:**

```
'10.112.129.0/24'    -> '10112129024'     dots and slash vanish; digits fuse
'10.112.129.0 /24'   -> '101121290 24'    one stray space => different string => NO match
'0%'                 -> '0'               matches any zero anywhere — USELESS as an entity
'IP addresses: NONE' -> 'ip addresses none'   does NOT contain 'no ip addresses'
"Jimbob's Banking"   -> 'jimbobs banking'
```

## 2. Per-item schema

A fresh `BenchmarkExampleV5` in `tests/eval/dataset_v5.py` — **do not mutate `BenchmarkExampleV3`**,
which `dataset_v4.py` still imports and `replace()`s.

```python
@dataclass(frozen=True)
class BenchmarkExampleV5:
    question: str                       # unique; scope pinned; output form stated
    expected_entities: tuple[str, ...]  # 1-5; each a substring of reference_answer
    reference_answer: str               # ANSWER / ACCEPTABLE VARIANTS / CONTRADICTIONS
    category: str
    difficulty: str                     # "simple" | "medium" | "advanced"
    island: str                         # "hvl" | "demo"  (for the shortcut audit)
    answer_type: str                    # count|list|value|boolean|explanation|absence
    domain: str                         # dcim|ipam|circuits|virt|tenancy|changelog|power
    source_query: str                   # the REST/GraphQL call that produces the answer
    forbidden_entities: tuple[str, ...] = ()   # must NOT appear (absence items)
```

`to_reference_output()` **hand-enumerates keys** — every new field must be added there or it never
reaches LangSmith.

## 3. Authoring rules

### The question must pin its own answer

1. **Scope, explicitly**: object type, status filter, org scope, null-handling, dedupe. "How many
   **active** devices **at HVL-SEA-DC1** have **no primary IPv4**? Count physical devices only."
2. **Use NetBox-native filter vocabulary** (`status=active`, `tenant=`, `has_primary_ip=false`). If a
   scope phrase has no filter equivalent, the ground truth isn't reproducible.
3. **State the output form** — names or IDs, never leave it to the agent.
4. **No bare superlatives** without a stated tie-break or a verified unique maximum.
5. **Bound list answers** ("name all four") — this is also what blocks the dump-everything shortcut.
6. **One claim per question**, or one homogeneous list. Multi-part capped at 3 enumerated sub-parts,
   and only in the advanced tier (~10–15% of items).

### Scope ambiguity becomes a contrast pair, not a footnote

Where scope changes the answer, author **both** as separate items. Our two live cases:
- "devices with no primary IP" = **3** scoped to active, **4** across all statuses (`boi-br04-sw01` is
  `planned`).
- "HVL devices" = **68** by tenant, **69** by site (`tac-br01-ap01` is deliberately tenantless, D14).

A minimal pair differing only in the filter is the sharpest available test of whether the agent
actually applied it.

### Reference-answer template (≤80 words)

```
ANSWER: <canonical answer, one sentence, scope restated>
ACCEPTABLE VARIANTS: <numeric/format equivalences that must not be penalised>
CONTRADICTIONS: <the specific wrong claims that must fail>
```

The CONTRADICTIONS block is the highest-leverage addition for a contradiction-scoring judge — it
converts an implicit judgement into an enumerated one. Keep the reference **minimal**: every
incidental detail becomes a new tripwire the agent can contradict without being wrong.

**Do not write global claims.** The v4 sentence *"Every one of the 180 IP addresses in NetBox…"*
became false the moment HVL IPs were seeded. Scope every claim to a tenant or site.

### `expected_entities` selection

- **Never include a string that also appears in the question** — otherwise an agent that merely
  restates the question scores.
- **1–5 entities**, each ≥5 characters, globally unique in the seed, not a substring of another
  entity name.
- **No bare integers.** `3` matches "13 devices", "10.3.0.0", "sw03", "2026-03-01". Use a distinctive
  phrase (`3 active devices`) or leave cardinality to the judges.
- **No percentages** — `0%` normalises to `0`. Utilization figures belong in `reference_answer`.
- Write in the exact casing/punctuation a real trace emits, not as guessed.

### Absence and false-premise items

- Every absence item gets a **twin** with identical phrasing over a target where the answer is
  non-empty — otherwise the phrasing leaks the answer.
- Use "Which…/List…", never yes/no (acquiescence bias).
- Set `forbidden_entities` — naming any specific object is the failure mode.
- `entity_coverage` is degenerate on absence items; report coverage over the positive subset only.
- ~5% false-premise items (a device that doesn't exist), always twinned with true-premise versions.

### Temporal phrasing

Timestamps cannot be backdated — everything was created at seed time. **Banned:** "last 7 days",
"recently", "currently", "now", "still". **Use instead**, in order of preference: object-scoped
history ("what action does the changelog record for device X?"), ordering ("which was created
first?"), or absolute windows with `recompute_on_reseed` marked. Anchor with *"as recorded in
NetBox"*.

## 4. Composition — 90 items

Stratified on **four axes simultaneously**: tier × answer type × domain × island.

| Answer type | per tier | ×3 tiers |
|---|---|---|
| Count | 7 | 21 |
| List (bounded) | 7 | 21 |
| Single value / lookup | 6 | 18 |
| Boolean / existence | 4 | 12 |
| Explanation / relationship | 3 | 9 |
| Absence ("none") | 3 | 9 |
| **Total** | **30** | **90** |

False-premise items (~4–5) are drawn *from* these counts, not added.

**Difficulty is defined by mechanism, never by topic:**

| Tier | Mechanism | Tool-call budget |
|---|---|---|
| simple | single object, one filter, no aggregation | 1–2 |
| medium | one join/hop or one aggregation, two filters | 2–4 |
| advanced | ≥2 hops, aggregation + filtering, or absence reasoning | 4+ |

**The binding constraint — every tenant, site and domain must appear in all three tiers.** Target
~20 HVL + ~10 demo per tier. If tenant name predicts tier, the routing evaluation measures topic
rather than difficulty, and the whole benchmark is compromised. Domains (DCIM, IPAM, circuits,
virtualization, tenancy, changelog, power) each appear in every tier.

## 5. Harness fixes required BEFORE authoring

| # | Issue | Why it blocks |
|---|---|---|
| 1 | `_fetch_feedback` returns at `len(fb) >= 3` but there are **four** evaluators | can return before `correctness` lands, silently dropping the primary metric |
| 2 | `ensure_dataset_*` is **create-only, not sync** | editing the Python file has *no effect* if the dataset name exists; iterating on 90 items needs a versioned name or an explicit delete |
| 3 | `tool_calls` is a single global number | advanced items have a higher floor; per-tier budgets are needed or the metric penalises the hard tier by construction |
| 4 | `_find_completed_experiment` requires **all** runs complete | one failure in 90 re-runs the entire experiment |
| 5 | `_experiment_was_quota_throttled` aborts at 46 of 90 | burns 45 quota failures before giving up |

Fixes 1 and 2 are mandatory. 3 is needed for the tier breakdown. 4 and 5 are cost/robustness.

## 6. Workflow

1. **Author the question + scope** from the 22-archetype checklist, tagging tier/type/domain/island.
2. **Record `source_query`** — the actual API call.
3. **Compute the answer** by running it with the **read-only agent token** (parity: if the agent
   can't see it, the question is unanswerable for the wrong reason).
4. **Write the reference** in the three-block template.
5. **Pick entities**, then run the self-match check (Rule A1).
6. Load as `netbox-benchmark-v5`.

Author in **batches of ~15**, verifying each batch, rather than 90 then discovering a systemic flaw.

## 7. Validation gates before any scoring run

- **Self-match check** — every entity is a substring of its own reference (catches the v4 bug class).
- **Uniqueness check** — no duplicate question strings.
- **Surface audit** — fit a trivial classifier on question features (tenant, site, length, wh-word,
  digits, negation) to predict tier and answer type. Target near-chance.
- **Three baselines**, each a non-discriminating-item detector: closed-book (no tools), schema-only,
  and dump-everything (one broad list call, verbose answer).
- **Judge alignment** — hand-label ~30 outputs and measure the judges' true-positive and
  true-negative rates. Expect to rewrite references afterwards; criteria drift is normal.

## 8. Statistical caveats to state in any write-up

At 30 items per tier, the standard error on a tier's pass rate is **≈9pp** — only effects of roughly
15–20pp are detectable. Questions sharing a tenant/site are a **cluster**, and clustering can inflate
standard errors ~3×, so report question count *and* cluster count. For routing comparisons use
**paired** analysis on identical questions (roughly a third less variance) and report the pairwise
difference with its CI, not two independent means.

## 9. Open items

- **Serials/asset tags approved for seeding** (0 of 141 devices currently have either), which
  restores the asset-management archetype and makes defect D15 real. Must run before authoring any
  serial-dependent question.
- Decide whether `forbidden_entities` gets a matching evaluator or stays advisory.
- `defects.json` supplies ready-made ground truth for ~10–15 advanced audit items.
