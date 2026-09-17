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
        # Identifier anchor, not the bare figure: "1226" is a bare number (it
        # matches inside unrelated digits) and "1226 change records" is a
        # fragile count phrase. Any correct comparison of the four named types
        # must say which one leads, so the type name is the stable string.
        expected_entities=("dcim.interface",),
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
        difficulty="advanced", island="hvl", answer_type="value", domain="dcim",
        source_query="/api/dcim/cables/ scanned for a_terminations or b_terminations empty -> cable 188, a=0 b=1",
    ),
    BenchmarkExampleV5(
        question=(
            "How many Halvorsen Logistics virtual machines have no primary IP "
            "address, and which of them is not even assigned to a host device?"
        ),
        expected_entities=("hvl-app08", "hvl-backup01", "hvl-test01"),
        reference_answer=(
            "ANSWER: Three of the 28 VMs have no primary IP: hvl-app08, "
            "hvl-backup01 and hvl-test01. Of those, hvl-test01 is also assigned to "
            "no host device -- it belongs to a cluster only.\n"
            "ACCEPTABLE VARIANTS: any order.\n"
            "CONTRADICTIONS: naming a VM that does have a primary IP, such as "
            "hvl-app01; claiming hvl-app08 has no host, since it runs on "
            "sea-dc1-esx04."
        ),
        category="vms-without-primary-ip",
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
        difficulty="advanced", island="demo", answer_type="value", domain="ipam",
        source_query="/api/ipam/vlan-groups/ -> utilization: HVL-SEA-DC1 0.15, other HVL groups 0.12",
    ),
    BenchmarkExampleV5(
        question=(
            "NC State University has far more racks than devices. How many of "
            "each does it have, and what does that imply about the site's build "
            "state?"
        ),
        expected_entities=("NCSU-065",),
        reference_answer=(
            "ANSWER: NC State has 29 racks but only 19 devices carrying its "
            "tenant, almost all of them at NCSU-065. The racks are modelled ahead "
            "of the equipment, so most stand empty.\n"
            "ACCEPTABLE VARIANTS: racks provisioned before hardware; mostly empty "
            "racks.\n"
            "CONTRADICTIONS: claiming devices outnumber racks; claiming the racks "
            "are full."
        ),
        category="rack-to-device-ratio",
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
        difficulty="advanced", island="demo", answer_type="count", domain="circuits",
        source_query="/api/circuits/circuits/?tenant=<t>&provider=<p> -> DM 26 across 2 providers; HVL 14 across 4",
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
