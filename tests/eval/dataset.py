"""Benchmark dataset for the NetBox model-matrix evaluation harness.

Defines the four canonical benchmark queries that have accumulated wall-time
baselines in `docs/traces/`, and provides a single function to push them
into LangSmith as a reusable dataset.

The dataset is keyed by name (`netbox-benchmark-v1`). `ensure_dataset()` is
idempotent — call it from any harness entrypoint; it creates on first run,
reuses thereafter. Bump the version suffix when changing the question set so
historical experiments stay comparable against their original dataset.

Inputs schema per example:
    {"question": str}

Reference output schema per example:
    {
        "expected_entities": list[str],   # facts the answer must mention
        "category": str,                  # query class for filtering / grouping
        "baseline_wall_seconds": float,   # observed floor on deepseek-v4-pro:cloud
    }

Evaluators consume `expected_entities` to score correctness without needing
exhaustive reference answers (NetBox state changes; pinning full answers
would create constant churn). The "did the answer cover these entities" check
is the structural signal; an LLM-as-judge supplies the semantic one.
"""

from dataclasses import dataclass

DATASET_NAME = "netbox-benchmark-v2"
DATASET_DESCRIPTION = (
    "NetBox infrastructure queries used as wall-time and quality baselines for "
    "the model-matrix evaluation harness. Four query classes covering "
    "multi-aspect tenant decomposition, device-detail lookup, cross-relationship "
    "VLAN deployment, and single-object rack elevation. "
    "v2 (2026-06-07): tightened expected_entities for all examples — pulled from "
    "actual deepseek-v4-pro:cloud trace ground-truth (the 14 DM sites for the "
    "tenant query, the 4 named devices for the rack-elevation query, etc.). v1's "
    "list was too permissive — a model could score 1.0 by naming 3 of 14 sites. "
    "v2 forces structural completeness."
)


@dataclass(frozen=True)
class BenchmarkExample:
    question: str
    expected_entities: tuple[str, ...]
    category: str
    baseline_wall_seconds: float

    def to_input(self) -> dict:
        return {"question": self.question}

    def to_reference_output(self) -> dict:
        return {
            "expected_entities": list(self.expected_entities),
            "category": self.category,
            "baseline_wall_seconds": self.baseline_wall_seconds,
        }


BENCHMARK_EXAMPLES: tuple[BenchmarkExample, ...] = (
    BenchmarkExample(
        question=(
            "Show all Dunder Mifflin sites with device counts, rack allocations, "
            "and IP prefix assignments"
        ),
        # Ground truth from trace 019e1c4e (2026-05-12): 14 DM-prefixed sites
        # under tenant "Dunder Mifflin". The full enumeration is the
        # correctness bar — a model that names "some sites" or only 3 of 14
        # should fail entity_coverage, not pass with the loose v1 list.
        # Aggregates "14" + "device"/"rack"/"prefix" verify all three aspects
        # of the multi-aspect question were addressed.
        expected_entities=(
            "Dunder Mifflin",
            # All 14 DM sites (per trace 019e1c4e lines 70-78)
            "DM-NYC",
            "DM-Akron",
            "DM-Albany",
            "DM-Binghamton",
            "DM-Buffalo",
            "DM-Camden",
            "DM-Nashua",
            "DM-Pittsfield",
            "DM-Rochester",
            "DM-Scranton",
            "DM-Stamford",
            "DM-Syracuse",
            "DM-Utica",
            "DM-Yonkers",
            # The three aspects asked for — each must be mentioned somewhere
            "device",
            "rack",
            "prefix",
            # Aggregate marker — answer should acknowledge "14 sites" not "some"
            "14",
        ),
        category="multi-aspect-tenant",
        baseline_wall_seconds=58.6,
    ),
    BenchmarkExample(
        question=(
            "For device dmi01-nashua-rtr01, show location details, "
            "assigned IP addresses, and tenant ownership"
        ),
        # Ground truth (trace 019e63e3): device exists, site DM-Nashua,
        # tenant Dunder Mifflin, role Edge Router, NO IPs assigned (model
        # explored 14 interfaces, all with count_ipaddresses=0). The
        # negative-IP finding is the semantic crux — we add "interface" so
        # answers that say "no IPs assigned" without grounding (i.e. without
        # mentioning the interface check) score lower than ones that do.
        expected_entities=(
            "dmi01-nashua-rtr01",
            "DM-Nashua",
            "Dunder Mifflin",
            "router",          # role/type — answer should classify the device
            "interface",       # answer should reference the interface check
        ),
        category="device-detail",
        baseline_wall_seconds=29.5,
    ),
    BenchmarkExample(
        question=(
            "Show where VLAN 100 is deployed across Jimbob's Banking sites, "
            "including devices using this VLAN and IP allocations"
        ),
        # Ground truth (conversation_history 25d3e6fe): the search for
        # Jimbob's Banking returns the tenant, but VLAN 100 is NOT deployed
        # at any of its sites — VLAN 100 is only at Dunder Mifflin sites.
        # The correct answer is a *negative finding*. Tightening here is
        # tricky because entity_coverage can't easily verify a negative; we
        # add "not" (catches "not deployed"/"is not present") and "0" (catches
        # "0 sites"/"zero deployments") as language markers, plus "tenant" to
        # verify the tenant lookup was actually performed.
        expected_entities=(
            "Jimbob's Banking",
            "VLAN 100",
            "tenant",
            "not",   # "not deployed" / "is not" — language of negative finding
            "0",     # "0 sites" / "zero deployments" / "0 devices"
        ),
        category="cross-relationship-vlan",
        baseline_wall_seconds=70.6,
    ),
    BenchmarkExample(
        question="Get rack elevation for rack Comms closet in site DM-Akron",
        # Ground truth (trace 019e1c19 lines 60-87): the rack is 12U Active,
        # contains 4 devices at specific positions — Patch Panel at U12,
        # dmi01-akron-sw01 at U10, dmi01-akron-rtr01 at U4, dmi01-akron-pdu01
        # at U1. "Rack elevation" in NetBox terminology specifically refers
        # to the layout view, so a correct answer enumerates the devices.
        # v1 only required {Comms closet, DM-Akron, 12U} — a 3-entity bar
        # that doesn't differentiate a one-liner from a real elevation listing.
        expected_entities=(
            "Comms closet",
            "DM-Akron",
            "12U",
            "Active",
            # All four devices in the rack (per the deepseek baseline trace)
            "dmi01-akron-sw01",
            "dmi01-akron-rtr01",
            "dmi01-akron-pdu01",
            "patch panel",
        ),
        category="single-object-rack",
        baseline_wall_seconds=10.0,
    ),
)


def ensure_dataset(client=None):
    """Create the benchmark dataset in LangSmith if it does not already exist.

    Returns the LangSmith Dataset object. Idempotent — safe to call from every
    matrix run; first call creates and populates, subsequent calls return the
    existing dataset unchanged.

    The runner imports this and calls it once before `client.evaluate()` so
    the harness has no setup ceremony beyond `python -m tests.eval.run_matrix`.
    """
    if client is None:
        # Load .env so LANGSMITH_API_KEY / LANGSMITH_ENDPOINT are picked up
        # when this runs outside of `python -m src.main` (which loads dotenv
        # via load_config()).
        from dotenv import load_dotenv
        from langsmith import Client
        load_dotenv()
        client = Client()

    if client.has_dataset(dataset_name=DATASET_NAME):
        return client.read_dataset(dataset_name=DATASET_NAME)

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=DATASET_DESCRIPTION,
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[ex.to_input() for ex in BENCHMARK_EXAMPLES],
        outputs=[ex.to_reference_output() for ex in BENCHMARK_EXAMPLES],
    )
    return dataset


if __name__ == "__main__":
    ds = ensure_dataset()
    print(f"Dataset ready: {ds.name} (id={ds.id})")
    print(f"Examples: {len(BENCHMARK_EXAMPLES)}")
    for ex in BENCHMARK_EXAMPLES:
        print(f"  [{ex.category}] {ex.question[:70]}{'…' if len(ex.question) > 70 else ''}")
