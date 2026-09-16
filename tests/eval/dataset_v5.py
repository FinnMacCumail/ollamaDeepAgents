"""netbox-benchmark-v5 — the stratified question set (scaffolding + validators).

Two hard-won lessons from v4 are baked into this module:

1. **Every `expected_entities` string MUST be a literal substring of its own
   `reference_answer`.** Four of the six v4 examples violate this, so a PERFECT
   answer cannot score 1.0 on them (site-comparison self-scores 0.500). The
   `validate_examples()` gate below makes that impossible to reintroduce.

2. **`ensure_dataset_v*` in v3/v4 is CREATE-ONLY.** If the dataset name exists
   it returns immediately and never adds, updates or removes an example — so
   editing the Python file silently has no effect. `ensure_dataset_v5()` here
   performs a real SYNC (add / update / delete) keyed on the question string.

Scoring contract (verified against the live harness):
  inputs  = {"question": str}
  outputs = {"expected_entities": list[str], "reference_answer": str,
             "category": str, "difficulty": str, ...}
  * `entity_coverage`   reads outputs["expected_entities"], substring match
                        after re.sub(r"[^a-z0-9 ]+", "", s.lower())
  * `completeness_judge` reads outputs["expected_entities"]
  * `correctness_judge`  reads outputs["reference_answer"]; scores CONTRADICTION
  * `tool_call_efficiency` reads the run, not the dataset; RAW COUNT

Measured quirk (langsmith 0.10.17): the `split` passed to `create_examples` does
NOT come back as `example.split` (that reads None). It is stored as
`metadata["dataset_split"]`, as a LIST. The sync below therefore ignores that key
when diffing metadata -- comparing it naively marks every example dirty forever.

PROVENANCE -- gold answers are only reproducible against a pinned instance:
  snapshot : 03-hvl-complete-assets-20260916.dump
  sha256   : 4c3b7e5fe5fb3439b5dd5ca4996926d59f6f1f4fd3d591cefc532822bfdc67a0
  NetBox   : 4.3.3 (Django 5.2.3, Python 3.12.3)
  token    : the READ-ONLY agent token (POST /api/dcim/sites/ -> 403), so every
             question is answerable with exactly the access the agent has.
Re-run each `source_query` and refresh the answers after any restore or reseed.

See docs/development/2026-09-16_v5-question-authoring-plan.md for the rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DATASET_NAME_V5 = "netbox-benchmark-v5"
DATASET_DESCRIPTION_V5 = (
    "Stratified NetBox question set (simple/medium/advanced) over the enriched "
    "instance: the demo tenants plus the additive Halvorsen Logistics tenant. "
    "Difficulty is defined by MECHANISM (hops, filters, aggregation), not by "
    "topic, and every tenant appears in all three tiers so tenant name cannot "
    "proxy for difficulty."
)

DIFFICULTIES = ("simple", "medium", "advanced")
ANSWER_TYPES = ("count", "list", "value", "boolean", "explanation", "absence")
DOMAINS = ("dcim", "ipam", "circuits", "virt", "tenancy", "changelog", "power")
ISLANDS = ("hvl", "demo")

# Per-tier tool-call budgets. A single global threshold would penalise the
# advanced tier by construction, since it has a higher floor by design.
TOOL_CALL_BUDGET = {"simple": 2, "medium": 4, "advanced": 12}


def _normalize(s: str) -> str:
    """EXACTLY the normalisation entity_coverage uses. Keep in sync."""
    return re.sub(r"[^a-z0-9 ]+", "", s.lower())


@dataclass(frozen=True)
class BenchmarkExampleV5:
    question: str                        # unique; scope pinned; output form stated
    expected_entities: tuple[str, ...]   # 1-5; each a substring of reference_answer
    reference_answer: str                # ANSWER / ACCEPTABLE VARIANTS / CONTRADICTIONS
    category: str
    difficulty: str                      # simple | medium | advanced
    island: str                          # hvl | demo  (for the shortcut audit)
    answer_type: str                     # count|list|value|boolean|explanation|absence
    domain: str                          # dcim|ipam|circuits|virt|tenancy|changelog|power
    source_query: str                    # the API call that produces the answer
    forbidden_entities: tuple[str, ...] = ()   # must NOT appear (absence items)
    recompute_on_reseed: bool = False     # temporal/volatile ground truth

    def to_input(self) -> dict:
        return {"question": self.question}

    def to_reference_output(self) -> dict:
        # NB: keys are hand-enumerated; a new dataclass field does NOT reach
        # LangSmith unless it is added here.
        return {
            "expected_entities": list(self.expected_entities),
            "reference_answer": self.reference_answer,
            "category": self.category,
            "difficulty": self.difficulty,
            "island": self.island,
            "answer_type": self.answer_type,
            "domain": self.domain,
            "forbidden_entities": list(self.forbidden_entities),
        }

    def to_metadata(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "island": self.island,
            "answer_type": self.answer_type,
            "domain": self.domain,
            "category": self.category,
            "source_query": self.source_query,
            "recompute_on_reseed": self.recompute_on_reseed,
            "tool_call_budget": TOOL_CALL_BUDGET.get(self.difficulty),
        }


# --------------------------------------------------------------------------
# Validation — run before any example reaches LangSmith
# --------------------------------------------------------------------------
# A "<number> <noun>" entity, e.g. "13 sites" / "6 prefixes". Fragile: a correct
# answer often inserts a qualifier ("13 Dunder-Mifflin sites", "6 IP prefixes"),
# which breaks the substring match even though the answer is right.
_COUNT_PHRASE = re.compile(r"\d+\s+[a-z][a-z-]*s?", re.I)

_BANNED_TEMPORAL = (
    "last 7 days", "last week", "this week", "recently", "today",
    "currently", "right now", "how long ago", " still ", " now ",
)


def validate_examples(examples) -> tuple[list[str], list[str]]:
    """Enforce the authoring rules. Returns (errors, warnings)."""
    errs: list[str] = []
    warns: list[str] = []
    seen_questions: dict[str, int] = {}

    for i, ex in enumerate(examples):
        tag = f"[{i}] {ex.question[:50]!r}"

        # -- vocabularies ---------------------------------------------------
        if ex.difficulty not in DIFFICULTIES:
            errs.append(f"{tag}: bad difficulty {ex.difficulty!r}")
        if ex.answer_type not in ANSWER_TYPES:
            errs.append(f"{tag}: bad answer_type {ex.answer_type!r}")
        if ex.domain not in DOMAINS:
            errs.append(f"{tag}: bad domain {ex.domain!r}")
        if ex.island not in ISLANDS:
            errs.append(f"{tag}: bad island {ex.island!r}")

        # -- uniqueness (rescore_* keys ground truth BY QUESTION STRING) ----
        if ex.question in seen_questions:
            errs.append(f"{tag}: duplicate question (also index "
                        f"{seen_questions[ex.question]}) -- ground truth would collide")
        seen_questions[ex.question] = i

        # -- RULE A1: entities must self-match their own reference ----------
        ref_norm = _normalize(ex.reference_answer)
        q_norm = _normalize(ex.question)
        for e in ex.expected_entities:
            if _normalize(e) not in ref_norm:
                errs.append(f"{tag}: entity {e!r} is NOT a substring of its own "
                            "reference_answer (a perfect answer could not score 1.0)")
            # -- no parroting: an entity also in the question is free marks --
            if _normalize(e) in q_norm:
                errs.append(f"{tag}: entity {e!r} also appears in the QUESTION "
                            "-- an agent that restates the question would score")
            if len(e.strip()) < 5:
                warns.append(f"{tag}: entity {e!r} is short (<5 chars); "
                             "substring matching will over-fire")
            if _normalize(e).strip().isdigit():
                errs.append(f"{tag}: entity {e!r} is a bare number -- it matches "
                            "inside unrelated digits (e.g. '3' in '13 devices')")
            if "%" in e:
                errs.append(f"{tag}: entity {e!r} contains '%' which normalises "
                            "away; put percentages in reference_answer instead")
            # MEASURED (v5 smoke run, 2026-09-16): a "<number> <noun>" entity is
            # fragile because a correct answer often slots a qualifier between
            # the two -- "13 sites" missed "13 Dunder-Mifflin sites", and
            # "6 prefixes" missed "6 IP prefixes". Both answers were CORRECT
            # (correctness 1.0) yet scored entity_coverage 0.0. Rule A1 proves a
            # perfect REFERENCE scores 1.0; it does not prove a correct ANSWER
            # does. Prefer a proper noun / identifier the answer must name.
            if _COUNT_PHRASE.fullmatch(e.strip()):
                warns.append(
                    f"{tag}: entity {e!r} is a '<number> <noun>' phrase -- a "
                    "correct answer may insert a qualifier between them. Prefer "
                    "an identifier (device/site/rack name, serial), or drop the "
                    "entity and let the judges score the figure.")

        if not ex.expected_entities and ex.answer_type != "absence":
            warns.append(f"{tag}: no expected_entities (entity_coverage -> None)")
        if len(ex.expected_entities) > 5:
            warns.append(f"{tag}: {len(ex.expected_entities)} entities (>5); "
                         "every optional one is a false negative for completeness")

        # -- absence items --------------------------------------------------
        if ex.answer_type == "absence" and not ex.forbidden_entities:
            warns.append(f"{tag}: absence item without forbidden_entities")

        # -- reference shape ------------------------------------------------
        if "ANSWER:" not in ex.reference_answer:
            warns.append(f"{tag}: reference_answer lacks the ANSWER: block")
        if "CONTRADICTIONS:" not in ex.reference_answer:
            warns.append(f"{tag}: reference_answer lacks the CONTRADICTIONS: block")
        if len(ex.reference_answer.split()) > 120:
            warns.append(f"{tag}: reference_answer is long "
                         f"({len(ex.reference_answer.split())} words); every extra "
                         "detail is a tripwire the agent can contradict")

        # -- temporal phrasing ----------------------------------------------
        low = f" {ex.question.lower()} "
        for phrase in _BANNED_TEMPORAL:
            if phrase in low:
                errs.append(f"{tag}: banned relative-time phrase {phrase!r} "
                            "(timestamps cannot be backdated; use an absolute "
                            "window or object-scoped history)")

        if not ex.source_query.strip():
            warns.append(f"{tag}: no source_query recorded -- ground truth is "
                         "not recomputable after a reseed")

    return errs, warns


def composition_report(examples) -> str:
    """Tier x answer-type x domain x island balance."""
    import collections

    lines = [f"examples: {len(examples)}"]
    for axis in ("difficulty", "answer_type", "domain", "island"):
        c = collections.Counter(getattr(e, axis) for e in examples)
        lines.append(f"  {axis:12}: {dict(sorted(c.items()))}")
    # The shortcut check: island must NOT predict difficulty.
    cross = collections.Counter(
        (e.island, e.difficulty) for e in examples
    )
    lines.append(f"  island x difficulty: {dict(sorted(cross.items()))}")
    lines.append("  -> every island must appear in every tier, or tenant name "
                 "proxies for difficulty")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Examples — authored in batches of ~15, each verified against live NetBox
#
# BATCH 1 (simple tier, 15 items: 10 HVL / 5 demo). Every answer below was
# computed with the READ-ONLY agent token against snapshot
# 03-hvl-complete-assets-20260916.dump, and every filter in `source_query` was
# proven to NARROW the result set first. NetBox silently ignores unknown filter
# params and returns the UNFILTERED total -- e.g. `?rack=DC1-R04` returns 141
# (every device in the instance) while `?rack_id=46` correctly returns 0.
# --------------------------------------------------------------------------
BENCHMARK_EXAMPLES_V5: tuple[BenchmarkExampleV5, ...] = (
    # ---- HVL island -----------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "How many devices are recorded at site HVL-SEA-DC1? "
            "Include every device status and report a single number."
        ),
        expected_entities=("30 devices",),
        reference_answer=(
            "ANSWER: 30 devices are recorded at site HVL-SEA-DC1, counting all statuses.\n"
            "ACCEPTABLE VARIANTS: thirty.\n"
            "CONTRADICTIONS: any other total; counting only active devices; "
            "reporting the tenant-wide total of 68."
        ),
        category="site-device-count",
        difficulty="simple", island="hvl", answer_type="count", domain="dcim",
        source_query="/api/dcim/devices/?site=hvl-sea-dc1 -> count (30 of 141)",
    ),
    BenchmarkExampleV5(
        question="How many IP prefixes are scoped to site HVL-SEA-HQ?",
        # No entity: every "<number> prefixes" phrasing is fragile (the agent
        # wrote "6 IP prefixes"). entity_coverage returns None here and the
        # figure is scored by correctness_judge instead.
        expected_entities=(),
        reference_answer=(
            "ANSWER: 6 prefixes are scoped to site HVL-SEA-HQ.\n"
            "ACCEPTABLE VARIANTS: six; 6 IP prefixes.\n"
            "CONTRADICTIONS: any other count; reporting the tenant-wide total of 42."
        ),
        category="site-prefix-count",
        difficulty="simple", island="hvl", answer_type="count", domain="ipam",
        source_query="/api/ipam/prefixes/?site=hvl-sea-hq -> count (6 of 132)",
    ),
    BenchmarkExampleV5(
        question=(
            "How many circuits does provider Evergreen Networks supply to "
            "tenant Halvorsen Logistics?"
        ),
        expected_entities=("7 circuits",),
        reference_answer=(
            "ANSWER: Evergreen Networks supplies 7 circuits to Halvorsen Logistics.\n"
            "ACCEPTABLE VARIANTS: seven.\n"
            "CONTRADICTIONS: any other count; reporting all 14 HVL circuits "
            "regardless of provider."
        ),
        category="provider-circuit-count",
        difficulty="simple", island="hvl", answer_type="count", domain="circuits",
        source_query="/api/circuits/circuits/?provider=evergreen-networks&tenant=hvl -> count (7 of 43)",
    ),
    BenchmarkExampleV5(
        question="List the names of every rack at site HVL-SEA-DC1.",
        expected_entities=("DC1-R01", "DC1-R02", "DC1-R03", "DC1-R04"),
        reference_answer=(
            "ANSWER: Four racks: DC1-R01, DC1-R02, DC1-R03 and DC1-R04.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: omitting one; naming a rack outside this set; "
            "claiming more or fewer than four."
        ),
        category="site-rack-list",
        difficulty="simple", island="hvl", answer_type="list", domain="dcim",
        source_query="/api/dcim/racks/?site=hvl-sea-dc1 -> names (4 of 52)",
    ),
    BenchmarkExampleV5(
        question="List the names of every device at site HVL-POR-BR02.",
        expected_entities=(
            "por-br02-pdu01", "por-br02-pp01", "por-br02-rtr01", "por-br02-sw01",
        ),
        reference_answer=(
            "ANSWER: Four devices: por-br02-pdu01, por-br02-pp01, "
            "por-br02-rtr01 and por-br02-sw01.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: omitting one; naming any other device."
        ),
        category="site-device-list",
        difficulty="simple", island="hvl", answer_type="list", domain="dcim",
        source_query="/api/dcim/devices/?site=hvl-por-br02 -> names (4 of 141)",
    ),
    BenchmarkExampleV5(
        question="What serial number is recorded for device sea-dc1-leaf04?",
        expected_entities=("HVL-SN-00046",),
        reference_answer=(
            "ANSWER: Device sea-dc1-leaf04 has serial HVL-SN-00046.\n"
            "ACCEPTABLE VARIANTS: none.\n"
            "CONTRADICTIONS: any other serial; stating that no serial is recorded."
        ),
        category="device-serial-lookup",
        difficulty="simple", island="hvl", answer_type="value", domain="dcim",
        source_query="/api/dcim/devices/?name=sea-dc1-leaf04 -> serial",
    ),
    BenchmarkExampleV5(
        question="Which rack holds device hq-acc04, and at which rack unit is it mounted?",
        expected_entities=("HQ-IDF2-R01", "unit 11"),
        reference_answer=(
            "ANSWER: Device hq-acc04 is mounted in rack HQ-IDF2-R01 at unit 11.\n"
            "ACCEPTABLE VARIANTS: U11; position 11.\n"
            "CONTRADICTIONS: any other rack or unit; claiming the device is unracked."
        ),
        category="device-rack-position",
        difficulty="simple", island="hvl", answer_type="value", domain="dcim",
        source_query="/api/dcim/devices/?name=hq-acc04 -> rack.name, position",
    ),
    BenchmarkExampleV5(
        question="Is rack DC1-R04 empty, or does it hold mounted devices?",
        expected_entities=("is empty", "no mounted devices"),
        reference_answer=(
            "ANSWER: Rack DC1-R04 is empty -- it holds no mounted devices (0).\n"
            "ACCEPTABLE VARIANTS: none; zero; nothing mounted.\n"
            "CONTRADICTIONS: naming any device as mounted in it; any non-zero count; "
            "reporting 141, which is what NetBox returns for the invalid filter "
            "`?rack=DC1-R04` because it ignores the unknown param."
        ),
        category="rack-occupancy",
        difficulty="simple", island="hvl", answer_type="boolean", domain="dcim",
        source_query="/api/dcim/devices/?rack_id=46 -> count (0). NOT ?rack=DC1-R04 (returns 141, unfiltered)",
    ),
    BenchmarkExampleV5(
        question=(
            "Does cluster HVL-SEA-HQ-EDGE have any virtual machines assigned, "
            "or is it unused?"
        ),
        expected_entities=("no virtual machines",),
        reference_answer=(
            "ANSWER: Cluster HVL-SEA-HQ-EDGE has no virtual machines assigned "
            "(a count of 0); it is an empty cluster.\n"
            "ACCEPTABLE VARIANTS: none; zero; unused.\n"
            "CONTRADICTIONS: naming any VM as belonging to it; any non-zero count."
        ),
        category="empty-cluster",
        difficulty="simple", island="hvl", answer_type="boolean", domain="virt",
        source_query="/api/virtualization/virtual-machines/?cluster_id=33 -> count (0 of 208)",
    ),
    BenchmarkExampleV5(
        question=(
            "Device hq-acc02 has cabling recorded against it in NetBox. What "
            "lifecycle status does NetBox record for the device, and what does "
            "that status indicate about its intended state?"
        ),
        expected_entities=("decommissioning",),
        reference_answer=(
            "ANSWER: Device hq-acc02 has status decommissioning, meaning it is being "
            "retired from service even though its cabling is still recorded.\n"
            "ACCEPTABLE VARIANTS: being retired; being removed from service.\n"
            "CONTRADICTIONS: reporting it as active, offline or planned; claiming it "
            "has already been deleted from NetBox."
        ),
        category="lifecycle-status",
        difficulty="simple", island="hvl", answer_type="explanation", domain="dcim",
        source_query="/api/dcim/devices/?name=hq-acc02 -> status (decommissioning)",
    ),
    # ---- demo island ----------------------------------------------------
    BenchmarkExampleV5(
        question="How many sites belong to tenant Dunder-Mifflin, Inc.?",
        expected_entities=("14 sites",),
        reference_answer=(
            "ANSWER: 14 sites belong to Dunder-Mifflin, Inc.\n"
            "ACCEPTABLE VARIANTS: fourteen.\n"
            "CONTRADICTIONS: any other count; counting only sites that have devices."
        ),
        category="tenant-site-count",
        difficulty="simple", island="demo", answer_type="count", domain="tenancy",
        source_query="/api/dcim/sites/?tenant=dunder-mifflin -> count (14 of 30)",
    ),
    BenchmarkExampleV5(
        question="How many devices belong to tenant Dunder-Mifflin, Inc.?",
        expected_entities=("39 devices",),
        reference_answer=(
            "ANSWER: 39 devices belong to Dunder-Mifflin, Inc.\n"
            "ACCEPTABLE VARIANTS: thirty-nine.\n"
            "CONTRADICTIONS: any other count; including the unnamed, tenantless patch "
            "panels that sit at Dunder-Mifflin sites but carry no tenant."
        ),
        category="tenant-device-count",
        difficulty="simple", island="demo", answer_type="count", domain="dcim",
        source_query="/api/dcim/devices/?tenant=dunder-mifflin -> count (39 of 141)",
    ),
    BenchmarkExampleV5(
        question=(
            "Which sites belonging to tenant Dunder-Mifflin, Inc. have no devices "
            "recorded at all?"
        ),
        expected_entities=("DM-NYC",),
        reference_answer=(
            "ANSWER: DM-NYC is the only Dunder-Mifflin site with no devices recorded.\n"
            "ACCEPTABLE VARIANTS: none.\n"
            "CONTRADICTIONS: naming any other site; claiming every site has devices."
        ),
        category="empty-site",
        difficulty="simple", island="demo", answer_type="list", domain="dcim",
        source_query="per-site /api/dcim/devices/?site=<slug> -> only dm-nyc has count 0",
    ),
    BenchmarkExampleV5(
        question=(
            "Which devices belonging to tenant Dunder-Mifflin, Inc. have a serial "
            "number recorded in NetBox?"
        ),
        expected_entities=("0 of 39",),
        reference_answer=(
            "ANSWER: 0 of 39 Dunder-Mifflin devices have a serial number "
            "recorded; the serial field is empty on every one.\n"
            "ACCEPTABLE VARIANTS: zero; no devices.\n"
            "CONTRADICTIONS: naming any specific device as having a serial; quoting "
            "a serial value for a Dunder-Mifflin device."
        ),
        category="absence-serial",
        difficulty="simple", island="demo", answer_type="absence", domain="dcim",
        source_query="/api/dcim/devices/?tenant=dunder-mifflin -> 0 of 39 have serial",
        forbidden_entities=("HVL-SN-", "dmi01-nashua-rtr01", "dmi01-scranton-sw01"),
    ),
    BenchmarkExampleV5(
        question="How many Dunder-Mifflin sites have a VLAN with VID 100 defined?",
        # DM-NYC is data-derived, not phrasing-derived: any correct answer must
        # account for the one site that lacks the VLAN. Preferred over the
        # fragile "13 sites" (the agent wrote "13 Dunder-Mifflin sites").
        expected_entities=("DM-NYC",),
        reference_answer=(
            "ANSWER: 13 of the 14 Dunder-Mifflin sites define a VLAN with VID 100; "
            "DM-NYC is the only one that does not.\n"
            "ACCEPTABLE VARIANTS: thirteen.\n"
            "CONTRADICTIONS: any other count; naming a different site as the "
            "exception; claiming Halvorsen Logistics also uses VID 100, which it "
            "does not."
        ),
        category="vlan-vid-count",
        difficulty="simple", island="demo", answer_type="count", domain="ipam",
        source_query="/api/ipam/vlans/?tenant=dunder-mifflin&vid=100 -> count (13 of 94); tenant=hvl&vid=100 -> 0",
    ),
)


# --------------------------------------------------------------------------
# Dataset sync (NOT create-only)
# --------------------------------------------------------------------------
def ensure_dataset_v5(client=None, *, prune: bool = True):
    """Create or SYNC netbox-benchmark-v5.

    Unlike ensure_dataset_v3/v4 (which return early if the dataset exists and
    therefore silently ignore edits), this reconciles the live dataset against
    BENCHMARK_EXAMPLES_V5: adds new questions, updates changed ones, and — when
    `prune` — deletes questions no longer in the set. Keyed on the question
    string, which is why questions must be unique.
    """
    if client is None:
        from pathlib import Path

        from dotenv import load_dotenv
        from langsmith import Client

        # Explicit path, not bare load_dotenv(): find_dotenv() walks the CALLER's
        # stack frames, and under `python - <<'PY'` the module is <stdin> with no
        # parent frame, so it dies on `assert frame.f_back is not None`.
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        client = Client()

    errs, warns = validate_examples(BENCHMARK_EXAMPLES_V5)
    if errs:
        raise ValueError(
            "v5 examples failed validation; refusing to upload:\n  "
            + "\n  ".join(errs)
        )
    for w in warns:
        print(f"WARN {w}")

    if client.has_dataset(dataset_name=DATASET_NAME_V5):
        dataset = client.read_dataset(dataset_name=DATASET_NAME_V5)
    else:
        dataset = client.create_dataset(
            dataset_name=DATASET_NAME_V5,
            description=DATASET_DESCRIPTION_V5,
        )

    existing = {}
    for ex in client.list_examples(dataset_id=dataset.id):
        q = (ex.inputs or {}).get("question")
        if q is not None:
            existing[q] = ex

    wanted = {ex.question: ex for ex in BENCHMARK_EXAMPLES_V5}

    def _dirty(live, ex) -> bool:
        if dict(live.outputs or {}) != ex.to_reference_output():
            return True
        # LangSmith injects metadata["dataset_split"] from `split`; it is not a
        # field we author, so exclude it or every example diffs forever.
        live_md = {k: v for k, v in (live.metadata or {}).items()
                   if k != "dataset_split"}
        return live_md != ex.to_metadata()

    to_create = [ex for q, ex in wanted.items() if q not in existing]
    to_update = [
        (existing[q], ex) for q, ex in wanted.items()
        if q in existing and _dirty(existing[q], ex)
    ]
    to_delete = [e for q, e in existing.items() if q not in wanted]

    if to_create:
        client.create_examples(
            dataset_id=dataset.id,
            examples=[
                {
                    "inputs": ex.to_input(),
                    "outputs": ex.to_reference_output(),
                    "metadata": ex.to_metadata(),
                    "split": ex.difficulty,
                }
                for ex in to_create
            ],
        )
    for live, ex in to_update:
        client.update_example(
            live.id,
            inputs=ex.to_input(),
            outputs=ex.to_reference_output(),
            metadata=ex.to_metadata(),
        )
    if prune and to_delete:
        client.delete_examples(example_ids=[e.id for e in to_delete])

    print(f"{DATASET_NAME_V5}: +{len(to_create)} created, "
          f"~{len(to_update)} updated, -{len(to_delete) if prune else 0} deleted, "
          f"{len(wanted)} total")
    return dataset


if __name__ == "__main__":
    errs, warns = validate_examples(BENCHMARK_EXAMPLES_V5)
    print(composition_report(BENCHMARK_EXAMPLES_V5))
    print(f"\nERRORS ({len(errs)}):")
    for e in errs:
        print(f"  x {e}")
    print(f"WARNINGS ({len(warns)}):")
    for w in warns:
        print(f"  ! {w}")
