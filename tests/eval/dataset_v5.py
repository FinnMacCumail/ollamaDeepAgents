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
# Anchor shape, the axis the ROUTING rule keys on -- independent of
# `difficulty`, which keys on retrieval MECHANISM. A question can be
# mechanically simple and still set-anchored.
ANCHORS = ("single", "set")

# Per-tier tool-call budgets. A single global threshold would penalise the
# advanced tier by construction, since it has a higher floor by design.
# MEASURED over 180 observations (90 items x 2 models, flash and pro):
#   simple   median 2.0, p75 3  -- only 32/60 within the old <=2, so raised to 3
#   medium   median 4.0, p75 7  -- 46/60 within <=7, correct, left alone
#   advanced median 6.0, p75 11 -- 50/60 within <=12, correct, left alone
# The old simple<=2 came from a 15-item single-model sample. Note the simple
# tier has a long tail regardless of the budget (single questions costing 21,
# 17, 14 calls); the median is what the budget tracks, not the outliers.
TOOL_CALL_BUDGET = {"simple": 3, "medium": 7, "advanced": 12}


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
    anchor: str                          # single | set  (routing axis)
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
            "anchor": self.anchor,
            "forbidden_entities": list(self.forbidden_entities),
        }

    def to_metadata(self) -> dict:
        return {
            "difficulty": self.difficulty,
            "island": self.island,
            "answer_type": self.answer_type,
            "domain": self.domain,
            "anchor": self.anchor,
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

# An IPv4 address or CIDR prefix, with or without a mask. These normalise to
# pure digits but are precise identifiers, so they are exempt from the
# bare-number rule.
_IP_LIKE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}(/\d{1,2})?$")

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
        if ex.anchor not in ANCHORS:
            errs.append(f"{tag}: bad anchor {ex.anchor!r}")

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
            # An IP address or CIDR prefix normalises to digits ("10.61.0.10" ->
            # "1061010") but is a STRONG identifier anchor, not a bare figure.
            # Exempt it, or the rule misfires on every IPAM item.
            if _normalize(e).strip().isdigit() and not _IP_LIKE.match(e.strip()):
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

            # MEASURED (30-item run): absence items have no stable surface form for
        # "none". The same model wrote "0 of 39 devices" on one run and "None of
        # the devices" on the next, so any entity scores 1.0 on one and 0.0 on
        # the other. Entities on an absence item measure phrasing luck.
        if ex.answer_type == "absence" and ex.expected_entities:
            errs.append(f"{tag}: absence item carries expected_entities "
                        f"{ex.expected_entities!r} -- there is no stable phrasing "
                        "for 'none'; leave them empty and let correctness_judge score it")

        if not ex.source_query.strip():
            warns.append(f"{tag}: no source_query recorded -- ground truth is "
                         "not recomputable after a reseed")

    # -- cross-item entity uniqueness ---------------------------------------
    # MEASURED (45-item set): four separate items were anchored on "DM-NYC"
    # alone, so ANY answer naming DM-NYC scores entity_coverage 1.0 on all four,
    # whichever question was actually asked. Substring matching cannot tell them
    # apart; only correctness_judge can. An item whose entities are ALL present
    # in another item's ANSWER block needs one entity unique to itself.
    #
    # Scored against the ANSWER block only: CONTRADICTIONS deliberately names
    # the wrong-answer objects, so including it flags almost everything.
    def _answer_block(ref: str) -> str:
        kept = []
        for line in ref.splitlines():
            if line.startswith(("CONTRADICTIONS:", "ACCEPTABLE VARIANTS:")):
                break
            kept.append(line)
        return _normalize("\n".join(kept))

    blocks = [(e, _answer_block(e.reference_answer)) for e in examples]
    for i, ex in enumerate(examples):
        if not ex.expected_entities:
            continue
        for other, blk in blocks:
            if other.question == ex.question:
                continue
            if all(_normalize(e) in blk for e in ex.expected_entities):
                warns.append(
                    f"[{i}] {ex.question[:50]!r}: every entity also appears in the "
                    f"ANSWER of {other.category!r} -- entity_coverage cannot "
                    "distinguish the two. If the pair is NOT a deliberate contrast "
                    "twin, add an entity unique to this question.")
                break

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
        anchor="set",
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
        anchor="set",
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
        anchor="set",
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
        anchor="set",
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
        anchor="set",
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
        anchor="single",
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
        anchor="single",
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
        anchor="single",
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
        anchor="single",
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
        anchor="single",
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
        anchor="set",
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
        anchor="set",
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
        anchor="set",
        difficulty="simple", island="demo", answer_type="list", domain="dcim",
        source_query="per-site /api/dcim/devices/?site=<slug> -> only dm-nyc has count 0",
    ),
    BenchmarkExampleV5(
        question=(
            "Which devices belonging to tenant Dunder-Mifflin, Inc. have a serial "
            "number recorded in NetBox?"
        ),
        # MEASURED: absence items cannot carry entities. Two runs of the SAME
        # model phrased this differently -- "0 of 39 devices" then "None of the
        # devices ... Every one of the 39" -- and no single substring matches
        # both. An earlier "0 of 39" repair scored 1.0 on the run it was drawn
        # from and 0.0 on the next: overfitting to one sample. Scored by
        # correctness_judge instead, like the other absence items.
        expected_entities=(),
        reference_answer=(
            "ANSWER: None of the 39 Dunder-Mifflin devices has a serial number "
            "recorded; the serial field is empty on every one.\n"
            "ACCEPTABLE VARIANTS: zero; no devices.\n"
            "CONTRADICTIONS: naming any specific device as having a serial; quoting "
            "a serial value for a Dunder-Mifflin device."
        ),
        category="absence-serial",
        anchor="set",
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
        anchor="set",
        difficulty="simple", island="demo", answer_type="count", domain="ipam",
        source_query="/api/ipam/vlans/?tenant=dunder-mifflin&vid=100 -> count (13 of 94); tenant=hvl&vid=100 -> 0",
    ),

    # ----------------------------------------------------------------------
    # BATCH 2 (medium tier, 15 items: 10 HVL / 5 demo).
    #
    # Medium = ONE join/hop or ONE aggregation, with two or more filters.
    # Difficulty is the MECHANISM, never the topic: every item here needs a
    # second step (resolve an id then filter by it, or aggregate a set), which
    # is what separates it from the simple tier's single lookup.
    #
    # Entities are IDENTIFIERS wherever the data affords one. The v5 smoke run
    # showed "<number> <noun>" entities break when a correct answer inserts a
    # qualifier ("13 sites" missed "13 Dunder-Mifflin sites"), and a join
    # naturally yields NAMES, so the medium tier can avoid that trap almost
    # everywhere. Where a count genuinely has no nameable anchor, the entity is
    # a distinctive string the answer must quote (a prefix, a device-type).
    # ----------------------------------------------------------------------

    # ---- HVL island -----------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Which access switches at site HVL-SEA-HQ are in the active state? "
            "List them by name."
        ),
        expected_entities=("hq-acc01", "hq-acc03", "hq-acc04"),
        reference_answer=(
            "ANSWER: Three active access switches: hq-acc01, hq-acc03 and hq-acc04.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: including hq-acc02, which is decommissioning, not "
            "active; naming any other device; omitting one."
        ),
        category="site-role-status-list",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="dcim",
        source_query="/api/dcim/devices/?site=hvl-sea-hq&role=access-switch&status=active -> 3 (role alone: 23 of 141)",
    ),
    BenchmarkExampleV5(
        question=(
            "Excluding patch panels and PDUs, which active Halvorsen Logistics "
            "devices have no primary IP address assigned? List them by name."
        ),
        expected_entities=("hq-acc04", "por-br02-sw01", "sea-dc1-leaf04"),
        reference_answer=(
            "ANSWER: Three: hq-acc04, por-br02-sw01 and sea-dc1-leaf04.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: including boi-br04-sw01, which is planned rather than "
            "active; reporting 25, the unfiltered has_primary_ip=false total that "
            "still counts the 9 patch panels and 12 PDUs which have no IP by design."
        ),
        category="no-primary-ip-active",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="dcim",
        source_query="/api/dcim/devices/?tenant=hvl&status=active&has_primary_ip=false minus role in (patch-panel,pdu) -> 3",
    ),
    BenchmarkExampleV5(
        # CONTRAST TWIN of the item above: identical but for the status filter.
        # The minimal pair is the sharpest test of whether the agent applied it.
        question=(
            "Excluding patch panels and PDUs, which Halvorsen Logistics devices "
            "have no primary IP address assigned? Count every status, not just "
            "active ones, and list them by name."
        ),
        expected_entities=("boi-br04-sw01", "hq-acc04", "por-br02-sw01", "sea-dc1-leaf04"),
        reference_answer=(
            "ANSWER: Four: boi-br04-sw01, hq-acc04, por-br02-sw01 and sea-dc1-leaf04.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: omitting boi-br04-sw01, which is planned and is the "
            "only difference from the active-only answer of three; reporting 25, "
            "which still includes the passive patch panels and PDUs."
        ),
        category="no-primary-ip-all-statuses",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="dcim",
        source_query="/api/dcim/devices/?tenant=hvl&has_primary_ip=false minus role in (patch-panel,pdu) -> 4",
    ),
    BenchmarkExampleV5(
        question=(
            "At site HVL-SEA-DC1, which rack holds the most mounted devices? "
            "Name the rack and give its device count."
        ),
        expected_entities=("DC1-R01",),
        reference_answer=(
            "ANSWER: DC1-R01 holds the most, with 11 mounted devices "
            "(DC1-R02 has 10, DC1-R03 has 8, DC1-R04 is empty).\n"
            "ACCEPTABLE VARIANTS: eleven.\n"
            "CONTRADICTIONS: naming any other rack; naming HQ-MDF-R01, which also "
            "holds 11 but is at HVL-SEA-HQ and outside the stated scope."
        ),
        category="rack-max-occupancy",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="value", domain="dcim",
        source_query="/api/dcim/racks/?site=hvl-sea-dc1 then /api/dcim/devices/?rack_id=<id> -> R01=11 R02=10 R03=8 R04=0",
    ),
    BenchmarkExampleV5(
        question=(
            "Which Halvorsen Logistics circuits are not in the active state? "
            "Give each circuit ID and its status."
        ),
        expected_entities=("EV-MPLS-1999", "EV-MPLS-2006"),
        reference_answer=(
            "ANSWER: Two: EV-MPLS-1999 is decommissioned and EV-MPLS-2006 is "
            "provisioning. The other 12 HVL circuits are active.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming any other circuit; swapping the two statuses; "
            "claiming all HVL circuits are active."
        ),
        category="circuit-status-filter",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="circuits",
        source_query="/api/circuits/circuits/?tenant=hvl -> 14, of which 2 are not status=active",
    ),
    BenchmarkExampleV5(
        question=(
            "Which Halvorsen Logistics hypervisor hosts have no virtual machines "
            "assigned to them? List them by name."
        ),
        expected_entities=("sea-dc1-esx05", "sea-dc1-esx09"),
        reference_answer=(
            "ANSWER: Two of the nine hypervisor hosts: sea-dc1-esx05 and "
            "sea-dc1-esx09.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a host that does carry VMs, such as "
            "sea-dc1-esx01 or sea-dc1-esx02, which have 6 each; claiming every "
            "host has VMs."
        ),
        category="hosts-without-vms",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="virt",
        source_query="/api/dcim/devices/?tenant=hvl&role=hypervisor-host then /api/virtualization/virtual-machines/?device_id=<id> -> 0 for esx05, esx09",
    ),
    BenchmarkExampleV5(
        question=(
            "Do the Halvorsen Logistics branch sites have power panels modelled "
            "in NetBox, or are panels recorded only at the larger sites? Name the "
            "panels that exist."
        ),
        expected_entities=("DC1-PP-A", "DC1-PP-B", "HQ-MDF-PP1"),
        reference_answer=(
            "ANSWER: The branch sites have no power panels. All three HVL panels "
            "sit at the two larger sites: DC1-PP-A and DC1-PP-B at HVL-SEA-DC1, "
            "and HQ-MDF-PP1 at HVL-SEA-HQ.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: claiming a branch site has a panel; naming a panel "
            "outside these three."
        ),
        category="power-panel-scope",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="boolean", domain="power",
        source_query="/api/dcim/power-panels/ -> 3 at hvl sites; ?site=hvl-<branch> -> 0 for all four branches",
    ),
    BenchmarkExampleV5(
        question=(
            "Ignoring wireless access points, which Halvorsen Logistics device is "
            "not assigned to a rack?"
        ),
        expected_entities=("sea-dc1-esx09",),
        reference_answer=(
            "ANSWER: sea-dc1-esx09 is the only one. Access points are excluded "
            "because they are 0U and ceiling-mounted, so being unracked is normal "
            "for them.\n"
            "ACCEPTABLE VARIANTS: none.\n"
            "CONTRADICTIONS: naming an access point such as hq-ap01 or "
            "spo-br03-ap02; naming a device that does have a rack."
        ),
        category="unracked-device",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="value", domain="dcim",
        source_query="/api/dcim/devices/?tenant=hvl with rack=null, minus role=wireless-ap -> sea-dc1-esx09",
    ),
    BenchmarkExampleV5(
        question=(
            "No device at site HVL-BOI-BR04 appears in a list of active Halvorsen "
            "Logistics devices. Explain why, naming the devices and the states "
            "involved."
        ),
        expected_entities=("boi-br04-rtr01", "boi-br04-sw01"),
        reference_answer=(
            "ANSWER: The site holds only boi-br04-rtr01 and boi-br04-sw01, and "
            "both are status planned rather than active. The site itself is also "
            "planned, so it is a build that has not gone live.\n"
            "ACCEPTABLE VARIANTS: not yet deployed; not yet commissioned.\n"
            "CONTRADICTIONS: describing either device as active, offline or "
            "decommissioning; claiming the site has no devices at all."
        ),
        category="planned-site-explanation",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="explanation", domain="dcim",
        source_query="/api/dcim/devices/?site=hvl-boi-br04 -> 2, both status=planned; site status=planned",
    ),
    BenchmarkExampleV5(
        question="Which IP addresses are assigned inside the VRF named HVL-GUEST?",
        # Absence item: no expected_entities, because any phrasing of "none" is
        # fragile. correctness_judge scores it against the reference instead.
        expected_entities=(),
        reference_answer=(
            "ANSWER: None. The HVL-GUEST VRF contains no IP addresses at all. It "
            "holds only four prefixes, all of them 192.168.100.0/24, duplicated "
            "once per branch site by design.\n"
            "ACCEPTABLE VARIANTS: zero; no addresses allocated.\n"
            "CONTRADICTIONS: naming any specific IP address in this VRF; quoting a "
            "non-zero address count; calling the duplicate prefixes an error."
        ),
        category="absence-vrf-ips",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="absence", domain="ipam",
        source_query="/api/ipam/ip-addresses/?vrf_id=<HVL-GUEST> -> 0; /api/ipam/prefixes/?vrf_id=<HVL-GUEST> -> 4",
        forbidden_entities=("10.60.", "10.61.", "10.62."),
    ),

    # ---- demo island ----------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Which VRFs contain exactly 30 IP addresses each? List them by name."
        ),
        # Echo IS a correct member. It was omitted from the entity list only to
        # dodge a short-string warning, and the judge then marked a complete
        # answer down for "incorrectly including Echo". Listing all five keeps
        # the entities and the reference in agreement.
        expected_entities=("Alpha", "Bravo", "Charlie", "Delta", "Echo"),
        reference_answer=(
            "ANSWER: Five VRFs hold exactly 30 addresses each: Alpha, Bravo, "
            "Charlie, Delta and Echo.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming HVL-CORP, which holds 436; naming HVL-GUEST or "
            "Shared, which hold none; omitting one of the five."
        ),
        category="vrf-ip-count-group",
        anchor="set",
        difficulty="medium", island="demo", answer_type="list", domain="ipam",
        source_query="/api/ipam/ip-addresses/?vrf_id=<id> per VRF -> Alpha..Echo = 30 each",
    ),
    BenchmarkExampleV5(
        question=(
            "Which providers supply circuits to tenant Dunder-Mifflin, Inc., and "
            "how many does each supply?"
        ),
        expected_entities=("CenturyLink", "Level 3"),
        reference_answer=(
            "ANSWER: Two providers, evenly split: CenturyLink supplies 13 and "
            "Level 3 supplies 13, for 26 circuits in total.\n"
            "ACCEPTABLE VARIANTS: any order; thirteen each.\n"
            "CONTRADICTIONS: naming a provider that supplies none, such as NTT or "
            "Comcast; claiming either provider supplies more than the other."
        ),
        category="provider-split",
        anchor="set",
        difficulty="medium", island="demo", answer_type="list", domain="circuits",
        source_query="/api/circuits/circuits/?tenant=dunder-mifflin&provider=<slug> -> centurylink 13, level-3 13 (26 total)",
    ),
    BenchmarkExampleV5(
        # BOUNDED deliberately. The unbounded form ("which object type is changed
        # most often?") cost 29 tool calls: NetBox has no group-by endpoint and
        # 16+ distinct types appear in the log, so a correct answer must probe
        # EVERY type one at a time. That measures the API's shape, not the agent.
        # Naming four candidates makes it a 4-call comparison with the same
        # answer. See the authoring plan's rule on bounding list answers.
        question=(
            "In the NetBox change log, compare these four object types -- "
            "interfaces, IP addresses, devices and cables. Which of the four has "
            "the most change records, and roughly how many?"
        ),
        # ENTITY-FREE, third attempt and the honest one. "1226" is a bare number;
        # "1226 change records" is a fragile count phrase; and "dcim.interface"
        # scored 0.0 on a FULLY CORRECT answer (judge: "All counts match the
        # reference; no contradictions") because the agent writes "Interface" and
        # "Interfaces", never the API type name. The bare word "interface" cannot
        # be used either -- the question names all four types, so it would be
        # earned by parroting. There is no stable surface string here, so
        # correctness_judge scores this item alone.
        expected_entities=(),
        reference_answer=(
            "ANSWER: Interfaces (dcim.interface) lead by a wide margin, with 1226 "
            "change records. "
            "IP addresses follow at 438, devices at 198 and cables at 95, out of "
            "3543 records in total.\n"
            "ACCEPTABLE VARIANTS: dcim.interface; about 1200.\n"
            "CONTRADICTIONS: naming IP addresses, devices or cables as the leader; "
            "giving interfaces a count below that of any other listed type."
        ),
        category="changelog-top-type",
        anchor="set",
        difficulty="medium", island="demo", answer_type="value", domain="changelog",
        source_query="/api/core/object-changes/?changed_object_type=<t> for the 4 named types -> interface 1226, ipaddress 438, device 198, cable 95",
    ),
    BenchmarkExampleV5(
        question=(
            "Which sites belonging to tenant Dunder-Mifflin, Inc. have no racks "
            "defined?"
        ),
        expected_entities=("DM-NYC",),
        reference_answer=(
            "ANSWER: DM-NYC only. It is the one Dunder-Mifflin site with no racks, "
            "and it holds no devices either. The other 13 sites have one rack each.\n"
            "ACCEPTABLE VARIANTS: none.\n"
            "CONTRADICTIONS: naming any other site; claiming every site has a rack."
        ),
        category="sites-without-racks",
        anchor="set",
        difficulty="medium", island="demo", answer_type="list", domain="dcim",
        source_query="/api/dcim/racks/?site=<slug> per DM site -> only dm-nyc has 0",
    ),
    BenchmarkExampleV5(
        question=(
            "How many devices sitting at Dunder-Mifflin sites are not assigned to "
            "any tenant, and what kind of device are they?"
        ),
        # Identifier anchor rather than a count phrase: any correct answer must
        # name the device type.
        expected_entities=("48-Port Patch Panel",),
        reference_answer=(
            "ANSWER: 13 devices, one per site that has equipment. Every one is an "
            "unnamed 48-Port Patch Panel with no tenant set. 52 devices sit at "
            "Dunder-Mifflin sites but only 39 carry the tenant.\n"
            "ACCEPTABLE VARIANTS: thirteen; patch panels.\n"
            "CONTRADICTIONS: reporting that all devices at these sites carry the "
            "tenant; naming a router, switch or PDU as the tenantless type."
        ),
        category="tenantless-devices",
        anchor="set",
        difficulty="medium", island="demo", answer_type="count", domain="tenancy",
        source_query="/api/dcim/devices/?site=<14 DM slugs> -> 52, of which 13 have tenant=null, all role=patch-panel",
    ),

    # ----------------------------------------------------------------------
    # BATCH 3 (advanced tier, 15 items: 10 HVL / 5 demo).
    #
    # Advanced = TWO OR MORE hops, or aggregation combined with filtering, or
    # absence reasoning over a traversal. Budget <=12 calls.
    #
    # Composition is deliberately corrected here: batches 1-2 over-produced
    # `list` (11 of 30) and `dcim` (17 of 30), so batch 3 is weighted to counts,
    # values and booleans, and to the thin domains (ipam, circuits, virt, power,
    # changelog).
    #
    # Ground truth is recomputed LIVE, never taken from blueprint.DEFECTS, which
    # has now disagreed with the instance six times. Two defects were DROPPED
    # after checking: D9 ("console port not connected") is 22 ports across 14
    # devices live, not the 1 the key claims; and rack `utilization` is absent
    # from this serializer, so no rack-utilization item is answerable.
    # ----------------------------------------------------------------------

    # ---- HVL island -----------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Some Halvorsen Logistics IP addresses sit outside every prefix "
            "defined in their own VRF. Which addresses are they, and which "
            "device holds each one?"
        ),
        expected_entities=("10.61.0.10", "10.62.0.1",
                           "sea-dc1-oob-sw01", "spo-br03-rtr01"),
        reference_answer=(
            "ANSWER: Two, both in VRF HVL-CORP: 10.61.0.10/24 on "
            "sea-dc1-oob-sw01, and 10.62.0.1/24 on spo-br03-rtr01. No prefix in "
            "that VRF contains either address.\n"
            "ACCEPTABLE VARIANTS: any order; addresses with or without the mask.\n"
            "CONTRADICTIONS: naming an address that does fall inside a prefix; "
            "claiming every address has a parent prefix; naming the intentional "
            "192.168.100.0/24 guest duplicates, which are not orphans."
        ),
        category="orphan-ip-no-parent-prefix",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="list", domain="ipam",
        source_query="all 132 prefixes grouped by VRF, then every IP tested for containment in its own VRF -> 2 orphans",
    ),
    BenchmarkExampleV5(
        question=(
            "The uplink on hq-acc04 does not reach its distribution switch, while "
            "the matching uplink on hq-acc03 does. Trace both and explain what "
            "differs."
        ),
        expected_entities=("hq-dist01",),
        reference_answer=(
            "ANSWER: hq-acc03's uplink GigabitEthernet1/0/48 traces through the "
            "patch panels and terminates on hq-dist01, so it is reachable. "
            "hq-acc04's GigabitEthernet1/0/48 is cabled but the path dead-ends at "
            "an unpatched panel port, so it has no far-end endpoint and is "
            "unreachable.\n"
            "ACCEPTABLE VARIANTS: broken patch path; missing panel-to-panel jumper.\n"
            "CONTRADICTIONS: claiming hq-acc04 reaches a distribution switch; "
            "claiming neither uplink is cabled; blaming a device status."
        ),
        category="broken-cable-path",
        anchor="single",
        difficulty="advanced", island="hvl", answer_type="explanation", domain="dcim",
        source_query="/api/dcim/interfaces/?device_id=<acc03|acc04> -> Gi1/0/48 reachable=True (hq-dist01:xe-0/0/1) vs reachable=False (no endpoints)",
    ),
    BenchmarkExampleV5(
        question=(
            "Each Halvorsen Logistics hypervisor host has two power supplies. "
            "Which host has exactly one of its two supplies connected to a PDU "
            "outlet, and which outlet is it?"
        ),
        expected_entities=("sea-dc1-esx05", "sea-dc1-pdu03"),
        reference_answer=(
            "ANSWER: sea-dc1-esx05. Its PSU0 is connected to sea-dc1-pdu03 "
            "Outlet 1, while PSU1 is not connected at all.\n"
            "ACCEPTABLE VARIANTS: one of two PSUs cabled.\n"
            "CONTRADICTIONS: naming sea-dc1-esx01 or sea-dc1-esx02, which have "
            "both supplies connected; naming a host with neither supply connected, "
            "such as sea-dc1-esx03 or sea-dc1-esx09; claiming both of esx05's "
            "supplies are connected."
        ),
        category="single-psu-connected",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="value", domain="power",
        source_query="/api/dcim/power-ports/?device_id=<each hypervisor> -> esx05 has 1 of 2 connected (pdu03 Outlet 1); esx01/02 have 2; others 0",
    ),
    BenchmarkExampleV5(
        question=(
            "One Halvorsen Logistics cable has lost the equipment on one of its "
            "two ends, yet the cable record remains in NetBox. Which port is "
            "attached to the end that survives?"
        ),
        expected_entities=("por-br02-sw01", "GigabitEthernet1/0/24"),
        reference_answer=(
            "ANSWER: The cable labelled por-br02-ap01 still attaches to "
            "por-br02-sw01 GigabitEthernet1/0/24. Its other end has no "
            "termination: the access point was deleted, which removed that side's "
            "termination but left the cable and the switch port reporting as "
            "cabled.\n"
            "ACCEPTABLE VARIANTS: cable 188; half-terminated cable.\n"
            "CONTRADICTIONS: naming a different port or device; claiming both ends "
            "are terminated; claiming the cable was deleted."
        ),
        category="orphaned-cable",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="value", domain="dcim",
        source_query="/api/dcim/cables/ scanned for a_terminations or b_terminations empty -> cable 188, a=0 b=1",
    ),
    BenchmarkExampleV5(
        question=(
            "How many Halvorsen Logistics virtual machines have no primary IP "
            "address, and which of them is not even assigned to a host device?"
        ),
        expected_entities=("hvl-app08", "hvl-backup01", "hvl-test01"),
        # CORRECTED after the 45-item run. The earlier reference claimed only
        # hvl-test01 lacked a host, and the judge duly penalised an agent that
        # correctly said hvl-backup01 lacks one too. Live: hvl-backup01 and
        # hvl-test01 BOTH have device=None; only hvl-app08 has a host. I had
        # over-read a probe that sampled just three VMs.
        reference_answer=(
            # VERIFIED against live data via MCP and REST. Note the two properties
            # are DIFFERENT sets: no-primary-IP = {app08, backup01, test01};
            # no-host = {backup01, fileshare01, test01}. The question scopes to
            # "of those", so the answer is the intersection, which is two.
            "ANSWER: Three of the 28 VMs have no primary IP: hvl-app08, "
            "hvl-backup01 and hvl-test01. Of those three, two are also assigned "
            "to no host device -- hvl-backup01 and hvl-test01 belong to a cluster "
            "only. hvl-app08 does have a host, sea-dc1-esx04. (Separately, "
            "hvl-fileshare01 also lacks a host but does have a primary IP, so it "
            "falls outside this question.)\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a VM that does have a primary IP, such as "
            "hvl-app01; claiming hvl-app08 has no host."
        ),
        category="vms-without-primary-ip",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="count", domain="virt",
        source_query="/api/virtualization/virtual-machines/?tenant=hvl -> 3 of 28 lack primary_ip; hvl-test01 also has device=null",
    ),
    BenchmarkExampleV5(
        question=(
            "Which Halvorsen Logistics circuit has a decommissioned status while "
            "retaining both of its terminations, and which customer site does it "
            "terminate at?"
        ),
        expected_entities=("EV-MPLS-1999", "HVL-SEA-HQ"),
        reference_answer=(
            "ANSWER: EV-MPLS-1999. Although decommissioned it retains both "
            "terminations: the A side at HVL-SEA-HQ and the Z side at the "
            "Evergreen MPLS Core.\n"
            "ACCEPTABLE VARIANTS: still terminated; terminations not removed.\n"
            "CONTRADICTIONS: naming EV-MPLS-2006, which is provisioning rather "
            "than decommissioned; naming any active circuit; claiming the "
            "terminations were removed."
        ),
        category="decommissioned-circuit-terminated",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="value", domain="circuits",
        source_query="/api/circuits/circuits/?tenant=hvl -> only EV-MPLS-1999 is decommissioned; its terminations -> HVL-SEA-HQ + Evergreen MPLS Core",
    ),
    BenchmarkExampleV5(
        question=(
            "An active Halvorsen Logistics prefix is nested inside another active "
            "prefix that is not marked as a container. Name both prefixes and the "
            "site the outer one covers."
        ),
        expected_entities=("10.60.36.128/25", "10.60.36.0/24", "HVL-POR-BR02"),
        reference_answer=(
            "ANSWER: The active prefix 10.60.36.128/25 sits inside the active "
            "prefix 10.60.36.0/24, which is scoped to HVL-POR-BR02. Neither is "
            "flagged as a container, so the nesting is an inconsistency.\n"
            "ACCEPTABLE VARIANTS: either order.\n"
            "CONTRADICTIONS: naming 10.60.3.0/26, which is a different case; "
            "naming the intentional 192.168.100.0/24 guest duplicates; claiming "
            "the outer prefix is a container."
        ),
        category="nested-active-prefix",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="list", domain="ipam",
        source_query="/api/ipam/prefixes/ -> 10.60.36.128/25 active, inside active 10.60.36.0/24 (scope HVL-POR-BR02)",
    ),
    BenchmarkExampleV5(
        question=(
            "One Halvorsen Logistics IP address carries a mask that disagrees with "
            "the prefix containing it. Which address is it, which prefix contains "
            "it, and which device interface holds it?"
        ),
        expected_entities=("10.60.3.20/24", "10.60.3.0/26", "sea-dc1-esx01"),
        reference_answer=(
            "ANSWER: 10.60.3.20/24, held on interface eno2 of sea-dc1-esx01. It "
            "falls inside the prefix 10.60.3.0/26, so its /24 mask disagrees with "
            "the /26 of the containing prefix.\n"
            "ACCEPTABLE VARIANTS: eno2; mask mismatch.\n"
            "CONTRADICTIONS: describing it as having no parent prefix, which is a "
            "different defect affecting 10.61.0.10 and 10.62.0.1; naming a "
            "different device or prefix."
        ),
        category="ip-mask-mismatch",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="value", domain="ipam",
        source_query="/api/ipam/ip-addresses/?address=10.60.3.20/24 -> on sea-dc1-esx01:eno2; containing prefix 10.60.3.0/26",
    ),
    BenchmarkExampleV5(
        question=(
            "Do any Halvorsen Logistics branch sites have a firewall, or are "
            "firewalls confined to the larger sites? Name the firewalls and where "
            "they sit."
        ),
        expected_entities=("hq-fw01", "sea-dc1-fw01", "sea-dc1-fw02"),
        reference_answer=(
            "ANSWER: No branch site has a firewall. All three sit at the two "
            "larger sites: sea-dc1-fw01 and sea-dc1-fw02 at HVL-SEA-DC1, and "
            "hq-fw01 at HVL-SEA-HQ.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: placing a firewall at HVL-TAC-BR01, HVL-POR-BR02, "
            "HVL-SPO-BR03 or HVL-BOI-BR04; naming a device that is not a firewall."
        ),
        category="firewall-site-distribution",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="boolean", domain="dcim",
        source_query="/api/dcim/devices/?tenant=hvl&role=firewall -> 3, at hvl-sea-dc1 (x2) and hvl-sea-hq only",
    ),
    BenchmarkExampleV5(
        question=(
            "Is there any Halvorsen Logistics site that has no router assigned to "
            "it?"
        ),
        # Absence item: entity-free by rule -- no stable phrasing for "none".
        expected_entities=(),
        reference_answer=(
            "ANSWER: No. Every one of the six Halvorsen Logistics sites has at "
            "least one router, including the planned site HVL-BOI-BR04, whose "
            "boi-br04-rtr01 is itself still planned.\n"
            "ACCEPTABLE VARIANTS: none; every site has a router.\n"
            "CONTRADICTIONS: naming any site as router-less; claiming HVL-BOI-BR04 "
            "has no router because it is not yet active."
        ),
        category="absence-site-without-router",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="absence", domain="dcim",
        source_query="/api/dcim/devices/?tenant=hvl&role=router -> 7 routers covering all 6 sites; set difference is empty",
        # Forbidden entries name OBJECTS, never sentences: a sentence lifted from
        # the reference leaks by construction.
        forbidden_entities=("HVL-POR-BR02", "HVL-TAC-BR01", "HVL-SPO-BR03"),
    ),

    # ---- demo island ----------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Counting every site in the instance regardless of tenant, how many "
            "hold no devices at all, and which are they?"
        ),
        expected_entities=("DM-NYC", "JBB Branch 104"),
        reference_answer=(
            "ANSWER: Seven sites hold no devices: DM-NYC and the six Jimbob's "
            "Banking & Trust branches, JBB Branch 104, 109, 115, 120, 127 and 133.\n"
            "ACCEPTABLE VARIANTS: any order; seven.\n"
            "CONTRADICTIONS: naming only DM-NYC and missing the JBB branches; "
            "naming a site that does hold devices, such as DM-AKRON or NCSU-065."
        ),
        category="empty-sites-instance-wide",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="count", domain="dcim",
        source_query="/api/dcim/devices/?site=<slug> across all 30 sites -> 7 with count 0 (dm-nyc + 6 jbb branches)",
    ),
    BenchmarkExampleV5(
        question=(
            "Across the whole instance, how many devices carry no tenant at all, "
            "and at which tenants' sites do they sit?"
        ),
        expected_entities=("48-Port Patch Panel", "tac-br01-ap01"),
        reference_answer=(
            "ANSWER: 15 devices have no tenant. Thirteen are unnamed 48-Port Patch "
            "Panels, one at each Dunder-Mifflin site that holds equipment. The "
            "other two sit elsewhere: an unnamed application server at NCSU-065, "
            "an NC State University site, and tac-br01-ap01, a wireless access "
            "point at the Halvorsen site HVL-TAC-BR01.\n"
            "ACCEPTABLE VARIANTS: fifteen; any order.\n"
            "CONTRADICTIONS: reporting 13 and counting only the Dunder-Mifflin "
            "panels; describing the NCSU-065 device as a patch panel; omitting "
            "tac-br01-ap01."
        ),
        category="tenantless-instance-wide",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="count", domain="tenancy",
        source_query="/api/dcim/devices/ -> devices with tenant=null: 13 at DM sites + 1 at ncsu-065 (+ tac-br01-ap01 at an HVL site)",
    ),
    BenchmarkExampleV5(
        question=(
            "Which VLAN group has the highest utilization figure recorded in "
            "NetBox, and is that figure closer to full or nearly empty?"
        ),
        expected_entities=("HVL-SEA-DC1 VLANs",),
        reference_answer=(
            "ANSWER: The HVL-SEA-DC1 VLANs group, at about 0.15 percent, which is "
            "nearly empty rather than close to full. The other HVL groups sit "
            "around 0.12 percent.\n"
            "ACCEPTABLE VARIANTS: 0.15; effectively empty; negligible utilization.\n"
            "CONTRADICTIONS: describing the group as full or heavily used; naming "
            "a group with a lower figure as the highest."
        ),
        category="vlan-group-utilization",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="value", domain="ipam",
        source_query="/api/ipam/vlan-groups/ -> utilization: HVL-SEA-DC1 0.15, other HVL groups 0.12",
    ),
    BenchmarkExampleV5(
        # SCOPE PINNED after the 45-item run. The earlier wording ("NC State
        # University has...") left tenant-vs-site scope open, and the agent
        # answered 20 (by site) against my 19 (by tenant). Both were defensible,
        # so the item was unanswerable as written -- exactly the ambiguity I had
        # already noted for this site and then failed to pin down.
        question=(
            "Counting only devices that carry the NC State University tenant, "
            "how do NC State's rack and device totals compare, and what does "
            "that imply about the build state?"
        ),
        expected_entities=("NCSU-065",),
        reference_answer=(
            "ANSWER: NC State has 29 racks but only 19 devices carrying its "
            "tenant, almost all of them at NCSU-065. The racks are modelled ahead "
            "of the equipment, so most stand empty.\n"
            "ACCEPTABLE VARIANTS: racks provisioned before hardware; mostly empty "
            "racks.\n"
            "CONTRADICTIONS: claiming devices outnumber racks; claiming the racks "
            "are full; reporting 20 devices, which counts an unnamed tenantless "
            "application server at NCSU-065 that carries no tenant."
        ),
        category="rack-to-device-ratio",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="explanation", domain="dcim",
        source_query="/api/dcim/racks/?tenant=nc-state -> 29; /api/dcim/devices/?tenant=nc-state -> 19",
    ),
    BenchmarkExampleV5(
        question=(
            "Comparing the two tenants that own circuits, does Dunder-Mifflin or "
            "Halvorsen Logistics have more circuits, and how many providers does "
            "each use?"
        ),
        expected_entities=("Cascadia Fiber", "Summit Wireless"),
        reference_answer=(
            "ANSWER: Dunder-Mifflin has more, with 26 circuits from 2 providers "
            "(CenturyLink and Level 3, 13 each). Halvorsen Logistics has 14 "
            "circuits but spread across 4 providers: Evergreen Networks with 7, "
            "Cascadia Fiber with 3, Rainier Broadband with 3 and Summit Wireless "
            "with 1.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: claiming Halvorsen has more circuits; giving either "
            "tenant the wrong provider count."
        ),
        category="cross-tenant-circuit-compare",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="count", domain="circuits",
        source_query="/api/circuits/circuits/?tenant=<t>&provider=<p> -> DM 26 across 2 providers; HVL 14 across 4",
    ),

    # ----------------------------------------------------------------------
    # BATCH 4 (15 items, MIXED tiers: 5 simple / 5 medium / 5 advanced).
    #
    # Batches 1-3 were one tier each, which let dcim reach 23 of 45 -- ten over
    # its 90-item share -- while changelog sat at 1 and power at 2. Batch 4 is
    # mixed so the thin domains land in ALL THREE tiers, which the plan requires,
    # and contains ZERO dcim items.
    #   changelog 3, power 3, virt 3, tenancy 2, circuits 2, ipam 2.
    #
    # Note "Nakatomi Corportation" is spelled that way in NetBox. The gold
    # answer uses the instance's spelling, not the corrected one.
    # ----------------------------------------------------------------------

    # ---- simple ---------------------------------------------------------
    BenchmarkExampleV5(
        question="Which power feeds does panel DC1-PP-A supply? List them by name.",
        expected_entities=("DC1-R01-A", "DC1-R02-A", "DC1-R03-A", "DC1-R04-A"),
        reference_answer=(
            "ANSWER: Four feeds: DC1-R01-A, DC1-R02-A, DC1-R03-A and DC1-R04-A.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a feed from the B panel, such as DC1-R01-B; "
            "omitting one; claiming the panel supplies more than four."
        ),
        category="panel-feed-list",
        anchor="single",
        difficulty="simple", island="hvl", answer_type="list", domain="power",
        source_query="/api/dcim/power-feeds/?power_panel_id=<DC1-PP-A> -> 4 of 59",
    ),
    BenchmarkExampleV5(
        question=(
            "Which virtualization platform does cluster HVL-SEA-HQ-EDGE run on, "
            "and do the other two Halvorsen Logistics clusters use the same one?"
        ),
        expected_entities=("KVM", "VMware"),
        reference_answer=(
            "ANSWER: HVL-SEA-HQ-EDGE runs KVM. The other two Halvorsen clusters, "
            "HVL-SEA-DC1-PROD and HVL-SEA-DC1-MGMT, both run VMware, so it is the "
            "odd one out.\n"
            "ACCEPTABLE VARIANTS: none.\n"
            "CONTRADICTIONS: reporting VMware for HVL-SEA-HQ-EDGE; claiming all "
            "three clusters share a platform."
        ),
        category="cluster-platform",
        anchor="single",
        difficulty="simple", island="hvl", answer_type="value", domain="virt",
        source_query="/api/virtualization/clusters/ -> HVL-SEA-HQ-EDGE type=KVM; PROD and MGMT type=VMware",
    ),
    BenchmarkExampleV5(
        question=(
            "NetBox has two tenant groups. Which one holds the most tenants, and "
            "how many does it hold?"
        ),
        expected_entities=("Customers",),
        reference_answer=(
            "ANSWER: The Customers group, with 11 tenants. The other group, "
            "Enterprise, holds just one.\n"
            "ACCEPTABLE VARIANTS: eleven.\n"
            "CONTRADICTIONS: naming Enterprise as the larger group; any other count."
        ),
        category="tenant-group-size",
        anchor="set",
        difficulty="simple", island="demo", answer_type="value", domain="tenancy",
        source_query="/api/tenancy/tenants/?group_id=<g> -> Customers 11, Enterprise 1",
    ),
    BenchmarkExampleV5(
        question="Which circuits in NetBox are of the Point-to-point circuit type?",
        expected_entities=(),
        reference_answer=(
            "ANSWER: None. The Point-to-point type is defined in NetBox but no "
            "circuit uses it. The other five types are all in use, MPLS most "
            "heavily with 20 circuits.\n"
            "ACCEPTABLE VARIANTS: zero; no circuits of that type.\n"
            "CONTRADICTIONS: naming any specific circuit as point-to-point; "
            "claiming the type does not exist in NetBox."
        ),
        category="absence-circuit-type",
        anchor="set",
        difficulty="simple", island="demo", answer_type="absence", domain="circuits",
        source_query="/api/circuits/circuits/?type=point-to-point -> 0 of 43",
        forbidden_entities=("EV-MPLS", "CF-DIA", "RB-BB", "SW-LTE"),
    ),
    BenchmarkExampleV5(
        question="How many change-log records does NetBox hold for device hq-acc02?",
        expected_entities=(),
        reference_answer=(
            "ANSWER: 4 change records.\n"
            "ACCEPTABLE VARIANTS: four.\n"
            "CONTRADICTIONS: any other count; reporting the instance-wide total "
            "of 3543 records."
        ),
        category="device-changelog-count",
        anchor="single",
        difficulty="simple", island="hvl", answer_type="count", domain="changelog",
        source_query="/api/core/object-changes/?changed_object_type=dcim.device&changed_object_id=<hq-acc02> -> 4",
        recompute_on_reseed=True,
    ),

    # ---- medium ---------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Which Halvorsen Logistics power feeds are not in the active state, "
            "and which rack does each serve?"
        ),
        expected_entities=("DC1-R04-A", "DC1-R04-B"),
        reference_answer=(
            "ANSWER: Two are planned rather than active: DC1-R04-A and DC1-R04-B. "
            "Both serve rack DC1-R04, which holds no devices.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming an active feed such as DC1-R01-A or HQ-MDF-A; "
            "claiming every Halvorsen feed is active."
        ),
        category="non-active-power-feeds",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="power",
        source_query="/api/dcim/power-feeds/?status=planned -> 2 of 59, both on rack DC1-R04",
    ),
    BenchmarkExampleV5(
        question=(
            "Are all Halvorsen Logistics virtual machines in the active state? "
            "Name any that are not, and give each one's status."
        ),
        expected_entities=("hvl-fileshare01", "hvl-ntp01"),
        reference_answer=(
            "ANSWER: No. Four of the 28 are not active: hvl-backup01 is "
            "decommissioning, hvl-fileshare01 and hvl-ntp01 are offline, and "
            "hvl-test01 is planned. The remaining 24 are active.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: claiming every VM is active; giving any named VM the "
            "wrong status."
        ),
        category="vm-status-audit",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="boolean", domain="virt",
        source_query="/api/virtualization/virtual-machines/?tenant=hvl -> 24 active, 2 offline, 1 decommissioning, 1 planned",
    ),
    BenchmarkExampleV5(
        question=(
            "How many Halvorsen Logistics prefixes have no VLAN associated with "
            "them?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: 28 of the 42 Halvorsen Logistics prefixes have no VLAN "
            "associated; the other 14 do.\n"
            "ACCEPTABLE VARIANTS: twenty-eight.\n"
            "CONTRADICTIONS: any other split; claiming every prefix carries a VLAN."
        ),
        category="prefixes-without-vlan",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="count", domain="ipam",
        source_query="/api/ipam/prefixes/?tenant=hvl -> 42, of which 14 have vlan set",
    ),
    BenchmarkExampleV5(
        question=(
            "Which change-log action is recorded least often across the instance, "
            "and how many records does it have?"
        ),
        # "delete" is NOT a substring of "deletion" -- after "delet" comes "i",
        # not "e". The validator caught this as a Rule A1 violation. "deletion"
        # is present, is absent from the question, and still fails a create/
        # update answer.
        expected_entities=("deletion",),
        reference_answer=(
            "ANSWER: Deletions are rarest, with 22 records. Creations dominate at "
            "3158 and updates account for 363, out of 3543 records in total.\n"
            "ACCEPTABLE VARIANTS: deletion; twenty-two.\n"
            "CONTRADICTIONS: naming create or update as the rarest action; giving "
            "deletions a count in the hundreds or thousands."
        ),
        category="changelog-rarest-action",
        anchor="set",
        difficulty="medium", island="demo", answer_type="value", domain="changelog",
        source_query="/api/core/object-changes/?action=<a> -> create 3158, update 363, delete 22",
        recompute_on_reseed=True,
    ),
    BenchmarkExampleV5(
        question=(
            "Which circuit type is used by the most circuits in NetBox, and how "
            "many circuits use it?"
        ),
        # "MPLS" alone matches inside circuit IDs such as EV-MPLS-1999, so an
        # answer about individual circuits could score it without naming the
        # TYPE. The fuller phrase is unambiguous and still present verbatim.
        expected_entities=("MPLS, with 20 circuits",),
        reference_answer=(
            "ANSWER: MPLS, with 20 circuits. Internet Access follows with 15, then "
            "Dark Fiber with 4, Broadband with 3 and LTE with 1.\n"
            "ACCEPTABLE VARIANTS: twenty.\n"
            "CONTRADICTIONS: naming Internet Access or any other type as the most "
            "used; claiming Point-to-point leads, since no circuit uses it."
        ),
        category="circuit-type-leader",
        anchor="set",
        difficulty="medium", island="demo", answer_type="value", domain="circuits",
        source_query="/api/circuits/circuits/?type=<slug> -> mpls 20, internet 15, dark-fiber 4, broadband 3, lte 1, point-to-point 0",
    ),

    # ---- advanced -------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "The change log holds 22 deletion records. What single event do they "
            "describe, and which device was removed?"
        ),
        expected_entities=("por-br02-ap01",),
        reference_answer=(
            "ANSWER: They record one cascading removal: the access point "
            "por-br02-ap01 was deleted, taking 13 cable terminations, 6 cables, "
            "one interface and one IP address with it. The device's name survives "
            "in the deletion record's prechange data.\n"
            "ACCEPTABLE VARIANTS: cascade delete; one device removal.\n"
            "CONTRADICTIONS: naming a different device; describing the 22 records "
            "as unrelated events; claiming the deleted object cannot be identified."
        ),
        category="deletion-cascade",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="explanation", domain="changelog",
        source_query="/api/core/object-changes/?action=delete -> 22: cabletermination 13, cable 6, device 1, interface 1, ipaddress 1; prechange_data.name = por-br02-ap01",
        recompute_on_reseed=True,
    ),
    BenchmarkExampleV5(
        question=(
            "The power feeds at HVL-SEA-DC1 and those at HVL-SEA-HQ are "
            "provisioned to different electrical specifications. Describe the "
            "difference and what it reflects about the two sites."
        ),
        expected_entities=("HQ-MDF-PP1",),
        reference_answer=(
            "ANSWER: The data-centre feeds, from panels DC1-PP-A and DC1-PP-B, run "
            "30 amps at 208 volts. The campus feeds, from HQ-MDF-PP1, run 20 amps "
            "at 120 volts. The data centre is provisioned for higher-density "
            "equipment than the office site.\n"
            "ACCEPTABLE VARIANTS: higher capacity at the data centre.\n"
            "CONTRADICTIONS: giving both sites the same rating; reversing which "
            "site carries the higher amperage or voltage."
        ),
        category="power-spec-contrast",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="explanation", domain="power",
        source_query="/api/dcim/power-feeds/ -> DC1 feeds 30A/208V (8), HQ feeds 20A/120V (3)",
    ),
    BenchmarkExampleV5(
        question=(
            "What is the total vCPU count across all Halvorsen Logistics virtual "
            "machines, and how much of that belongs to the production cluster?"
        ),
        expected_entities=("HVL-SEA-DC1-PROD",),
        reference_answer=(
            "ANSWER: 108 vCPUs in total. HVL-SEA-DC1-PROD accounts for 90 of them "
            "across its 22 VMs, HVL-SEA-DC1-MGMT for the remaining 18 across 6 "
            "VMs, and HVL-SEA-HQ-EDGE for none.\n"
            "ACCEPTABLE VARIANTS: none.\n"
            "CONTRADICTIONS: any other total; attributing vCPUs to "
            "HVL-SEA-HQ-EDGE, which has no virtual machines."
        ),
        category="vcpu-aggregation",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="count", domain="virt",
        source_query="/api/virtualization/virtual-machines/?tenant=hvl -> sum(vcpus)=108; PROD 90, MGMT 18, EDGE 0",
    ),
    BenchmarkExampleV5(
        question=(
            "Do all tenants in NetBox have at least one site? Name any that have "
            "none."
        ),
        expected_entities=("Cyberdyne Systems", "Pied Piper", "Umbrella Corporation"),
        reference_answer=(
            "ANSWER: No. Eight tenants have no sites: Cyberdyne Systems, Initech, "
            "Nakatomi Corportation, Pied Piper, Stark Industries, Strickland "
            "Propane, Umbrella Corporation and Wayne Enterprises. All eight sit in "
            "the Customers group.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: claiming every tenant has a site; naming a tenant "
            "that does have sites, such as Dunder-Mifflin or NC State University."
        ),
        category="tenants-without-sites",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="boolean", domain="tenancy",
        source_query="/api/dcim/sites/?tenant=<slug> per tenant -> 8 of 12 tenants have 0 sites",
    ),
    BenchmarkExampleV5(
        question=(
            "Outside the data-centre VLAN group, do any Halvorsen Logistics VLAN "
            "groups contain a quarantine VLAN?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: None do. QUARANTINE, VID 999, exists only in the HVL-SEA-DC1 "
            "VLANs group. The five campus and branch groups each hold the same "
            "five VLANs -- DATA, VOICE, WIFI, GUEST and MGMT -- and none of them "
            "is a quarantine VLAN.\n"
            "ACCEPTABLE VARIANTS: zero; no other group.\n"
            "CONTRADICTIONS: naming another group as holding a quarantine VLAN; "
            "claiming no quarantine VLAN exists anywhere."
        ),
        category="absence-quarantine-vlan",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="absence", domain="ipam",
        source_query="/api/ipam/vlans/?group_id=<g> -> VID 999 QUARANTINE only in HVL-SEA-DC1 VLANs; branch groups hold 110/210/310/410/900",
        forbidden_entities=("HVL-TAC-BR01 VLANs", "HVL-POR-BR02 VLANs", "HVL-SPO-BR03 VLANs"),
    ),

    # ----------------------------------------------------------------------
    # BATCH 5 (15 items, mixed tiers 5/5/5), weighted to the thin domains:
    # power 4, dcim 4, changelog 3, tenancy 2, virt 1, ipam 1.
    #
    # NOTE, honestly: this batch was PLANNED as zero-dcim, and it is not. Rack
    # reservations and platforms are dcim objects and there is no better bucket
    # for them, so dcim goes 23 -> 27 against a 12.9 even share. That was a
    # deliberate trade -- reservations and platforms were the richest unmined
    # material left -- but it means batch 6 must be strictly zero dcim and load
    # circuits, virt and tenancy, which remain at 7 apiece.
    #
    # Two candidate items were DROPPED after probing rather than authored wrong:
    #   - "which device has the most change records" has NO unique maximum:
    #     spo-br03-ap02, sea-dc1-esx04/06/07/08/09 all tie at 4. The circuit
    #     version below does have a unique max (EV-MPLS-2004 at 5, next 4).
    #   - virtual chassis and device bays are unusable: every member device and
    #     the Lenovo Flex chassis have name=None, so no question about them is
    #     answerable by name -- the same trap as the unnamed dm-scranton panel.
    # ----------------------------------------------------------------------

    # ---- simple ---------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Which user account is recorded as having made the change-log "
            "entries in this NetBox instance?"
        ),
        expected_entities=("seeder",),
        reference_answer=(
            "ANSWER: A single account, seeder, is recorded against all 3543 "
            "change-log entries. No other user appears in the log.\n"
            "ACCEPTABLE VARIANTS: only one user.\n"
            "CONTRADICTIONS: naming more than one user; naming alice or bob, who "
            "appear on rack reservations but not in the change log."
        ),
        category="changelog-user",
        anchor="set",
        difficulty="simple", island="demo", answer_type="value", domain="changelog",
        source_query="/api/core/object-changes/ -> user_name is 'seeder' on all 3543",
        recompute_on_reseed=True,
    ),
    BenchmarkExampleV5(
        question=(
            "How many power outlets does each Halvorsen Logistics PDU provide, "
            "and how many PDUs are there?"
        ),
        # ENTITY-FREE after the two-model run. "8 outlets" and "96 in total"
        # scored 0.0 on flash and 0.5 on pro despite both answering correctly --
        # the fourth time a count phrase has failed because a correct answer
        # words the figure differently. There is no identifier to anchor on here,
        # so correctness_judge scores it alone.
        expected_entities=(),
        reference_answer=(
            "ANSWER: All 12 Halvorsen PDUs provide 8 outlets each, which is 96 "
            "in total.\n"
            "ACCEPTABLE VARIANTS: eight each; twelve PDUs.\n"
            "CONTRADICTIONS: giving different outlet counts to different PDUs; any "
            "other PDU count."
        ),
        category="pdu-outlet-count",
        anchor="set",
        difficulty="simple", island="hvl", answer_type="count", domain="power",
        source_query="/api/dcim/devices/?tenant=hvl&role=pdu -> 12; /api/dcim/power-outlets/?device_id=<each> -> 8 apiece",
    ),
    BenchmarkExampleV5(
        question="Which device platforms have at least one device assigned to them?",
        expected_entities=("Cisco IOS", "Ubuntu 22.04"),
        # SCOPE PINNED. The first draft said the other five platforms "have none",
        # which is true of DEVICES but false of VMs: RHEL 9 carries 5 virtual
        # machines and Windows Server 2022 carries 2. An agent checking platform
        # usage generally would have been marked wrong for being right -- the
        # same scope trap as rack-to-device-ratio. The reference now states the
        # device scope and names the VM counts so a broader answer cannot clash.
        reference_answer=(
            "ANSWER: Counting physical devices only, two of the seven platforms "
            "are in use: Cisco IOS with 13 devices and Ubuntu 22.04 with 9. The "
            "other five -- PAN-OS 11, RHEL 9, Ubuntu Linux 18.04, Ubuntu Linux "
            "20.04 and Windows Server 2022 -- have no devices, though RHEL 9 and "
            "Windows Server 2022 are used by virtual machines.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a platform with no devices as having devices; "
            "claiming all seven platforms carry devices."
        ),
        category="platforms-in-use",
        anchor="set",
        difficulty="simple", island="demo", answer_type="list", domain="dcim",
        source_query="/api/dcim/devices/?platform=<slug> -> cisco-ios 13, ubuntu-22-04 9, other five 0",
    ),
    BenchmarkExampleV5(
        question=(
            "Which tenant is the only one in NetBox that owns virtual machines?"
        ),
        expected_entities=("only tenant",),
        reference_answer=(
            "ANSWER: Halvorsen Logistics is the only tenant that owns virtual "
            "machines, with 28. Every other tenant, including Dunder-Mifflin and "
            "NC State University, owns none.\n"
            "ACCEPTABLE VARIANTS: HVL.\n"
            "CONTRADICTIONS: naming Dunder-Mifflin or any other tenant as owning "
            "VMs; claiming several tenants own them."
        ),
        category="sole-vm-tenant",
        anchor="set",
        difficulty="simple", island="hvl", answer_type="value", domain="virt",
        source_query="/api/virtualization/virtual-machines/?tenant=<slug> per tenant -> only hvl is non-zero (28)",
    ),
    BenchmarkExampleV5(
        question=(
            "How many rack reservations exist in NetBox, and how many of them "
            "belong to Halvorsen Logistics?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: Four reservations exist, and two of them belong to Halvorsen "
            "Logistics. The other two carry no tenant.\n"
            "ACCEPTABLE VARIANTS: 4 and 2.\n"
            "CONTRADICTIONS: any other total; claiming all four belong to one "
            "tenant."
        ),
        category="rack-reservation-count",
        anchor="set",
        difficulty="simple", island="hvl", answer_type="count", domain="dcim",
        source_query="/api/dcim/rack-reservations/ -> 4 total; ?tenant=hvl -> 2 of 4",
    ),

    # ---- medium ---------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Which Halvorsen Logistics PDUs have any outlet in use, and how many "
            "outlets are in use on each?"
        ),
        expected_entities=("sea-dc1-pdu01", "sea-dc1-pdu02", "sea-dc1-pdu03"),
        reference_answer=(
            "ANSWER: Three of the 12. sea-dc1-pdu01 and sea-dc1-pdu02 are fully "
            "loaded at 8 outlets each, and sea-dc1-pdu03 has a single outlet in "
            "use, for 17 in total. The other nine PDUs have none.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a PDU outside these three, such as hq-pdu01 or "
            "tac-br01-pdu01; claiming every PDU carries load."
        ),
        category="pdu-load-distribution",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="power",
        source_query="/api/dcim/power-outlets/?device_id=<each HVL pdu> -> pdu01 8, pdu02 8, pdu03 1, rest 0",
    ),
    BenchmarkExampleV5(
        question=(
            "One tenant has VLANs defined but owns no devices, racks or prefixes "
            "at all. Which tenant is it, and how many VLANs does it have?"
        ),
        expected_entities=("Jimbob's Banking & Trust",),
        reference_answer=(
            "ANSWER: Jimbob's Banking & Trust. It has 24 VLANs and 6 sites, but no "
            "devices, no racks and no prefixes.\n"
            "ACCEPTABLE VARIANTS: twenty-four.\n"
            "CONTRADICTIONS: naming NC State University, which has racks and "
            "devices but no VLANs; naming a tenant that owns devices."
        ),
        category="vlans-without-infrastructure",
        anchor="set",
        difficulty="medium", island="demo", answer_type="value", domain="tenancy",
        source_query="tenant coverage matrix -> jimbobs-banking-trust: sites 6, vlans 24, devices 0, racks 0, prefixes 0",
    ),
    BenchmarkExampleV5(
        question=(
            "Across the whole change log, which action accounts for the updates "
            "to devices, and how many device updates are recorded?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: 127 of the 363 update records apply to devices, the largest "
            "share of any object type. Interfaces follow with 98 and circuits with "
            "28.\n"
            "ACCEPTABLE VARIANTS: 127 device updates.\n"
            "CONTRADICTIONS: reporting the 198 total device change records, which "
            "include creations; naming interfaces as the most-updated type."
        ),
        category="device-update-share",
        anchor="set",
        difficulty="medium", island="demo", answer_type="count", domain="changelog",
        source_query="/api/core/object-changes/?action=update -> 363; by type: device 127, interface 98, circuit 28",
        recompute_on_reseed=True,
    ),
    BenchmarkExampleV5(
        question=(
            "Which IP aggregates are registered under RFC 1918, and which "
            "aggregate is registered under a different RIR?"
        ),
        expected_entities=("100.64.0.0/10",),
        reference_answer=(
            "ANSWER: Three aggregates sit under RFC 1918 -- 10.0.0.0/8, "
            "172.16.0.0/12 and 192.168.0.0/16. The fourth, 100.64.0.0/10, is "
            "registered under RFC 6598 instead.\n"
            "ACCEPTABLE VARIANTS: any order; carrier-grade NAT range.\n"
            "CONTRADICTIONS: placing 100.64.0.0/10 under RFC 1918; naming an "
            "aggregate that does not exist."
        ),
        category="aggregate-rir-split",
        anchor="set",
        difficulty="medium", island="demo", answer_type="list", domain="ipam",
        source_query="/api/ipam/aggregates/ -> 4; ?rir=rfc-1918 -> 3 of 4; 100.64.0.0/10 is RFC 6598",
    ),
    BenchmarkExampleV5(
        question=(
            "Do any Halvorsen Logistics PDUs draw power from a modelled power "
            "feed, or is the upstream connection missing?"
        ),
        # "no upstream" failed Rule A1 -- the reference said "modelled upstream
        # connection". "power ports are uncabled" is the substantive claim, is
        # present verbatim, and cannot be earned by restating the question.
        expected_entities=("power ports are uncabled",),
        reference_answer=(
            "ANSWER: None of the 12 PDUs has a modelled upstream connection. Their "
            "power ports are uncabled, so no PDU traces back to a power feed even "
            "at HVL-SEA-DC1, where DC1-PP-A and DC1-PP-B do supply rack feeds.\n"
            "ACCEPTABLE VARIANTS: the upstream link is not modelled.\n"
            "CONTRADICTIONS: claiming a PDU is connected to a feed; naming a "
            "specific feed as supplying a named PDU."
        ),
        category="pdu-upstream-gap",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="boolean", domain="power",
        source_query="/api/dcim/power-ports/?device_id=<each HVL pdu> -> no connected_endpoints on any of the 12",
    ),

    # ---- advanced -------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Which single circuit has the most change-log records, how many does "
            "it have, and what kind of changes are they?"
        ),
        expected_entities=("EV-MPLS-2004",),
        reference_answer=(
            "ANSWER: EV-MPLS-2004, with 5 records: one creation and four updates. "
            "The next busiest circuits, EV-MPLS-2001, EV-MPLS-2003 and "
            "EV-MPLS-2005, have four each.\n"
            "ACCEPTABLE VARIANTS: five records.\n"
            "CONTRADICTIONS: naming a different circuit as the most changed; "
            "describing the records as deletions."
        ),
        category="most-changed-circuit",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="value", domain="changelog",
        source_query="/api/core/object-changes/?changed_object_type=circuits.circuit -> id 37 (EV-MPLS-2004) 5 records: 1 create, 4 update; next-highest 4",
        recompute_on_reseed=True,
    ),
    BenchmarkExampleV5(
        question=(
            "Two rack reservations block capacity in the Halvorsen data centre. "
            "Which racks do they cover, how many units does each hold back, and "
            "why?"
        ),
        expected_entities=("GPU expansion",),
        reference_answer=(
            "ANSWER: DC1-R02 has 20 units reserved for a GPU expansion in Q1, and "
            "DC1-R03 has 4 units held as spare capacity for storage growth. Both "
            "belong to Halvorsen Logistics.\n"
            "ACCEPTABLE VARIANTS: units 20-39 and 20-23.\n"
            "CONTRADICTIONS: naming R101 or IDF128, which are reservations on "
            "other tenants' racks; swapping the two unit counts."
        ),
        category="rack-reservation-detail",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="explanation", domain="dcim",
        source_query="/api/dcim/rack-reservations/?tenant=hvl -> DC1-R02 units 20-39 'GPU expansion (Q1)', DC1-R03 units 20-23 'Spare capacity for storage growth'",
    ),
    BenchmarkExampleV5(
        question=(
            "Comparing the power feeds at the Halvorsen data centre with those "
            "serving NC State's racks, which estate has more feeds and how do "
            "their electrical ratings differ?"
        ),
        # ENTITY-FREE: "48 feeds" was missed by BOTH models on correct answers
        # (they write "48 power feeds"). The question already names NC State and
        # Halvorsen, so neither can serve as an entity without parroting.
        expected_entities=(),
        reference_answer=(
            "ANSWER: NC State has far more, with 48 feeds across its racks against "
            "8 at HVL-SEA-DC1. The NC State feeds are rated 20 amps at 220 volts, "
            "while the Halvorsen data-centre feeds run 30 amps at 208 volts.\n"
            "ACCEPTABLE VARIANTS: forty-eight.\n"
            "CONTRADICTIONS: claiming Halvorsen has more feeds; swapping the two "
            "electrical ratings."
        ),
        category="cross-estate-power-compare",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="count", domain="power",
        source_query="/api/dcim/power-feeds/ -> 59 total: 48 on NCSU racks R101-R308 (20A/220V), 8 on DC1 racks (30A/208V), 3 at HQ (20A/120V)",
    ),
    BenchmarkExampleV5(
        question=(
            "NC State University and Jimbob's Banking & Trust are both incomplete "
            "in NetBox, but in opposite ways. Explain what each one is missing."
        ),
        # ENTITY-FREE: "29 racks" and "24 VLANs" scored 0.5 on flash and 0.0 on
        # pro. Both tenants are named in the question, so no identifier is
        # available that would not be earned by parroting.
        expected_entities=(),
        reference_answer=(
            "ANSWER: NC State has the physical estate but no addressing: 4 sites, "
            "19 devices and 29 racks, yet no prefixes and no VLANs. Jimbob's is the "
            "reverse -- 6 sites and 24 VLANs, but no devices, no racks and no "
            "prefixes.\n"
            "ACCEPTABLE VARIANTS: either order.\n"
            "CONTRADICTIONS: giving either tenant objects it does not have; "
            "claiming both are missing the same thing."
        ),
        category="opposite-incompleteness",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="explanation", domain="tenancy",
        source_query="tenant matrix -> nc-state: racks 29 devices 19 prefixes 0 vlans 0; jimbobs: vlans 24 sites 6 devices 0 racks 0 prefixes 0",
    ),
    BenchmarkExampleV5(
        question=(
            "Outside the Halvorsen data centre, is any rack anywhere in NetBox "
            "reserved with a note warning that it must not be used?"
        ),
        expected_entities=("Damaged",),
        reference_answer=(
            "ANSWER: Yes, one. Rack R101 carries a two-unit reservation made by "
            "the user bob, described as 'Damaged - DO NOT USE'. It has no tenant.\n"
            "ACCEPTABLE VARIANTS: R101; do not use.\n"
            "CONTRADICTIONS: naming a Halvorsen rack such as DC1-R02 or DC1-R03, "
            "whose reservations are for planned expansion rather than damage; "
            "claiming no such reservation exists."
        ),
        category="damaged-rack-reservation",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="boolean", domain="dcim",
        source_query="/api/dcim/rack-reservations/ -> R101 units [20,21] user=bob description='Damaged - DO NOT USE'",
    ),

    # ----------------------------------------------------------------------
    # BATCH 6 (final 15, mixed tiers 5/5/5). Completes the set at 90.
    #
    # STRICTLY zero dcim: it ends on 27 against a 12.9 even share, fourteen
    # over, because batch 5 spent four slots on rack reservations and platforms.
    # This batch loads virt, circuits and tenancy instead.
    #
    # Islands are 10 hvl / 5 demo, split 3-2 / 4-1 / 3-2 across the tiers. That
    # lands island x difficulty on exactly 19/19/19 hvl and 11/11/11 demo.
    # Hitting the raw 60/30 target instead would have forced a 13-2 final batch
    # and broken that balance, which is the property that actually stops tenant
    # name proxying for difficulty.
    #
    # Types are fully determined by what is left: boolean 4, absence 4, count 3,
    # list 3, explanation 1.
    # ----------------------------------------------------------------------

    # ---- simple ---------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Do all Halvorsen Logistics circuits have two terminations recorded? "
            "Name any that have only one."
        ),
        expected_entities=("CF-DIA-1001", "SW-LTE-4001"),
        reference_answer=(
            "ANSWER: No. Seven of the 14 have a single termination: CF-DIA-1001, "
            "CF-DIA-1003, CF-METRO-1002, RB-BB-3001, RB-BB-3002, RB-BB-3003 and "
            "SW-LTE-4001. The seven EV-MPLS circuits each have two.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: claiming every Halvorsen circuit has two "
            "terminations; naming an EV-MPLS circuit as singly terminated."
        ),
        category="single-termination-circuits",
        anchor="set",
        difficulty="simple", island="hvl", answer_type="boolean", domain="circuits",
        source_query="/api/circuits/circuit-terminations/ grouped by circuit -> 7 HVL circuits with 1, the 7 EV-MPLS with 2",
    ),
    BenchmarkExampleV5(
        question=(
            "How many Halvorsen Logistics virtual machines have no network "
            "interface at all, and which are they?"
        ),
        expected_entities=("hvl-backup01", "hvl-test01"),
        reference_answer=(
            "ANSWER: Two of the 28: hvl-backup01 and hvl-test01. The tenant's VMs "
            "carry 26 interfaces between them, so every other VM has at least one.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a VM that does have an interface, such as "
            "hvl-app01; claiming every VM has one."
        ),
        category="vms-without-interfaces",
        anchor="set",
        difficulty="simple", island="hvl", answer_type="count", domain="virt",
        source_query="/api/virtualization/interfaces/?virtual_machine_id=<each> -> 26 across 28 VMs; 2 have none",
    ),
    BenchmarkExampleV5(
        question=(
            "Across all Halvorsen Logistics PDUs, how many of the available power "
            "outlets are actually in use?"
        ),
        expected_entities=("17 of the 96",),
        reference_answer=(
            "ANSWER: 17 of the 96 outlets are in use. sea-dc1-pdu01 and "
            "sea-dc1-pdu02 account for 8 each and sea-dc1-pdu03 for one; the other "
            "nine PDUs have nothing plugged in.\n"
            "ACCEPTABLE VARIANTS: seventeen.\n"
            "CONTRADICTIONS: any other total; claiming most outlets are in use."
        ),
        category="pdu-outlet-utilisation",
        anchor="set",
        difficulty="simple", island="hvl", answer_type="count", domain="power",
        source_query="/api/dcim/power-outlets/?device_id=<12 HVL pdus> -> 96 outlets, 17 with connected_endpoints",
    ),
    BenchmarkExampleV5(
        question=(
            "Which user accounts other than seeder appear against entries in the "
            "NetBox change log?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: None. All 3543 change-log entries are attributed to the "
            "account seeder. The accounts alice and bob exist and appear on rack "
            "reservations, but never in the change log.\n"
            "ACCEPTABLE VARIANTS: zero; only seeder.\n"
            "CONTRADICTIONS: naming alice, bob or any other account as having made "
            "change-log entries."
        ),
        category="absence-other-changelog-users",
        anchor="set",
        difficulty="simple", island="demo", answer_type="absence", domain="changelog",
        source_query="/api/core/object-changes/ -> user_name 'seeder' on all 3543",
        recompute_on_reseed=True,
        # No forbidden entities. alice and bob were listed here and BOTH appear in
        # this item's own reference, which names them precisely to rule them out
        # -- a leak by construction, the same mistake as the batch-3 router item.
        # The reference is right to mention them; the forbidden list was wrong.
    ),
    BenchmarkExampleV5(
        question="Which contacts are assigned the Billing role in NetBox?",
        expected_entities=(),
        reference_answer=(
            "ANSWER: None. The Billing role is defined but no contact holds it. All "
            "three contact assignments use the other two roles: two Administrative "
            "and one Operational.\n"
            "ACCEPTABLE VARIANTS: zero; the role is unused.\n"
            "CONTRADICTIONS: naming any contact as holding the Billing role; "
            "claiming the role does not exist in NetBox."
        ),
        category="absence-billing-contacts",
        anchor="set",
        difficulty="simple", island="demo", answer_type="absence", domain="tenancy",
        source_query="/api/tenancy/contact-assignments/ -> 3 total: Administrative 2, Operational 1, Billing 0",
        forbidden_entities=("Dwight Schrute", "Michael Scott", "Pamela Halpert"),
    ),

    # ---- medium ---------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Which provider networks are defined in NetBox, and which provider "
            "owns each one?"
        ),
        expected_entities=("Evergreen MPLS Core", "Level3 MPLS"),
        reference_answer=(
            "ANSWER: Two. Evergreen MPLS Core belongs to Evergreen Networks, and "
            "Level3 MPLS belongs to Level 3.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: attributing either network to the wrong provider; "
            "naming a provider network that does not exist, such as one for "
            "Cascadia Fiber."
        ),
        category="provider-networks",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="list", domain="circuits",
        source_query="/api/circuits/provider-networks/ -> 2: Evergreen MPLS Core (Evergreen Networks), Level3 MPLS (Level 3)",
    ),
    BenchmarkExampleV5(
        question=(
            "Do any Halvorsen Logistics virtual machines have a role assigned to "
            "them?"
        ),
        expected_entities=("every one has a platform",),
        reference_answer=(
            "ANSWER: No. Not one of the 28 Halvorsen virtual machines has a role "
            "set, even though every one has a platform, a vCPU count, memory and "
            "disk recorded.\n"
            "ACCEPTABLE VARIANTS: none of them; zero.\n"
            "CONTRADICTIONS: naming a VM as having a role; claiming roles are set "
            "on some of them."
        ),
        category="vms-without-roles",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="boolean", domain="virt",
        source_query="/api/virtualization/virtual-machines/?tenant=hvl -> role is null on all 28; platform set on all 28",
    ),
    BenchmarkExampleV5(
        question=(
            "Which contacts are attached to site DM-Scranton, and what role does "
            "each hold?"
        ),
        expected_entities=("Dwight Schrute", "Michael Scott", "Pamela Halpert"),
        reference_answer=(
            "ANSWER: Three: Dwight Schrute as Operational, and Michael Scott and "
            "Pamela Halpert both as Administrative. These are the only contact "
            "assignments in the instance.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: giving any contact the wrong role; attaching a "
            "contact to a different site."
        ),
        category="site-contacts",
        anchor="single",
        difficulty="medium", island="demo", answer_type="list", domain="tenancy",
        source_query="/api/tenancy/contact-assignments/ -> all 3 on dcim.site DM-Scranton",
    ),
    BenchmarkExampleV5(
        question=(
            "Which prefixes belonging to Halvorsen Logistics have no tenant "
            "assigned to them?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: None. All 42 Halvorsen prefixes carry the tenant. NetBox does "
            "hold 22 tenantless prefixes, but they sit in the Alpha through Echo "
            "VRFs and the Shared VRF, none of which is scoped to a Halvorsen site.\n"
            "ACCEPTABLE VARIANTS: zero.\n"
            "CONTRADICTIONS: naming a Halvorsen prefix as tenantless; claiming the "
            "22 tenantless prefixes belong to Halvorsen."
        ),
        category="absence-tenantless-hvl-prefixes",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="absence", domain="ipam",
        source_query="/api/ipam/prefixes/?tenant=hvl -> 42; tenantless overall 22, none scoped to an HVL site",
        forbidden_entities=("10.60.", "192.168.100.0/24"),
    ),
    BenchmarkExampleV5(
        question=(
            "How much total disk is provisioned across all Halvorsen Logistics "
            "virtual machines?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: 5939200 MB in total, which is a little over 5.9 million MB or "
            "roughly 5.7 TB, across the 28 VMs.\n"
            "ACCEPTABLE VARIANTS: 5,939,200 MB; about 5.7 TB; about 5.8 TB.\n"
            "CONTRADICTIONS: any total that is not close to 5939200 MB; reporting "
            "the memory figure of 294912 MB instead."
        ),
        category="vm-disk-aggregate",
        anchor="set",
        difficulty="medium", island="hvl", answer_type="count", domain="virt",
        source_query="/api/virtualization/virtual-machines/?tenant=hvl -> sum(disk) = 5939200 MB over 28 VMs",
    ),

    # ---- advanced -------------------------------------------------------
    BenchmarkExampleV5(
        question=(
            "Most singly-terminated circuits in NetBox are internet-style services "
            "where no far end is modelled. One Halvorsen circuit does not fit that "
            "pattern. Which is it, and why is it the odd one out?"
        ),
        expected_entities=("CF-METRO-1002",),
        reference_answer=(
            "ANSWER: CF-METRO-1002, from Cascadia Fiber. It is a Dark Fiber "
            "circuit, yet it has only one termination. The other singly-terminated "
            "circuits are Internet Access, Broadband or LTE services, where having "
            "no Z side is expected; dark fibre normally runs between two known "
            "points.\n"
            "ACCEPTABLE VARIANTS: metro dark fibre.\n"
            "CONTRADICTIONS: naming an Internet Access, Broadband or LTE circuit as "
            "the anomaly; claiming every singly-terminated circuit is expected."
        ),
        category="dark-fiber-anomaly",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="explanation", domain="circuits",
        source_query="singly-terminated by type -> Internet Access 15, Broadband 3, LTE 1, Dark Fiber 1 (CF-METRO-1002)",
    ),
    BenchmarkExampleV5(
        question=(
            "NetBox holds a large number of Google Cloud clusters. Do any of them "
            "host virtual machines?"
        ),
        expected_entities=("DigitalOcean",),
        reference_answer=(
            "ANSWER: No. All 23 Google Cloud clusters are empty. Every one of the "
            "180 demo virtual machines sits on one of the 9 DigitalOcean clusters, "
            "20 apiece.\n"
            "ACCEPTABLE VARIANTS: none of them; zero.\n"
            "CONTRADICTIONS: naming a Google Cloud cluster as hosting VMs; "
            "claiming the VMs are spread across both cluster types."
        ),
        category="empty-cloud-clusters",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="boolean", domain="virt",
        source_query="/api/virtualization/virtual-machines/?cluster_id=<each> -> 23 gc-* clusters all 0; 9 DO-* clusters 20 each",
    ),
    BenchmarkExampleV5(
        question=(
            "Are there any tenants in NetBox that belong to neither of the two "
            "tenant groups?"
        ),
        expected_entities=(),
        reference_answer=(
            "ANSWER: None. All 12 tenants are grouped: 11 in Customers and one, "
            "Halvorsen Logistics, in Enterprise. No tenant is left ungrouped.\n"
            "ACCEPTABLE VARIANTS: zero; every tenant is grouped.\n"
            "CONTRADICTIONS: naming a tenant as ungrouped; giving a total other "
            "than 12 tenants."
        ),
        category="absence-ungrouped-tenants",
        anchor="set",
        difficulty="advanced", island="demo", answer_type="absence", domain="tenancy",
        source_query="/api/tenancy/tenants/ -> 12, group set on all: Customers 11, Enterprise 1",
        forbidden_entities=("Cyberdyne Systems", "Initech", "Umbrella Corporation"),
    ),
    BenchmarkExampleV5(
        question=(
            "According to the change log, was any Halvorsen Logistics device other "
            "than the access point por-br02-ap01 ever deleted?"
        ),
        expected_entities=("only device deletion",),
        reference_answer=(
            "ANSWER: No. The change log holds exactly one device deletion, and it "
            "is por-br02-ap01. It is the only device deletion among the 22 deletion "
            "records; the other 21 are the cables, terminations, interface and IP "
            "address that went with it.\n"
            "ACCEPTABLE VARIANTS: none; just the one.\n"
            "CONTRADICTIONS: naming another deleted device; claiming several "
            "devices were removed."
        ),
        category="sole-device-deletion",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="boolean", domain="changelog",
        source_query="/api/core/object-changes/?action=delete -> 22 records, changed_object_type dcim.device on exactly 1 (prechange name por-br02-ap01)",
        recompute_on_reseed=True,
    ),
    BenchmarkExampleV5(
        question=(
            "Which operating-system platforms are recorded on Halvorsen Logistics "
            "virtual machines, and how many VMs run each?"
        ),
        expected_entities=("Ubuntu 22.04", "RHEL 9", "Windows Server 2022"),
        reference_answer=(
            "ANSWER: Three platforms across the 28 VMs: Ubuntu 22.04 on 21, RHEL 9 "
            "on 5 and Windows Server 2022 on 2.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a platform no VM runs, such as Cisco IOS or "
            "PAN-OS 11; giving any platform the wrong VM count."
        ),
        category="vm-platform-split",
        anchor="set",
        difficulty="advanced", island="hvl", answer_type="list", domain="virt",
        source_query="/api/virtualization/virtual-machines/?tenant=hvl -> platform: Ubuntu 22.04 21, RHEL 9 5, Windows Server 2022 2",
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
