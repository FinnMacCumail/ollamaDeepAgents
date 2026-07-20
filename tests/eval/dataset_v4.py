"""netbox-benchmark-v4 — same questions + verified reference answers as v3, in a
clean namespace intended to be scored with the reference-grounded
`correctness_judge`.

Why a new version rather than editing v3: the 2026-07-05 v3 experiments used the
old evaluator set, which never read `reference_answer`. That let a confidently
hallucinated "~7.7% IP utilization" answer score 0.9 on completeness, because
the judge was only ever shown `expected_entities` (positive keywords), never the
ground truth. See `docs/development/2026-07-20_netbox-benchmark-v4-rescore.md`.

v4 keeps the DATA identical (the v3 reference answers were already correct —
re-verified against live NetBox on 2026-07-20: DM Data prefix 10.112.149.0/24
holds 0 IPs; all 180 NetBox IPs live in 172.16.0.0/24, unrelated to the DM
sites → 0% allocation confirmed). The change is entirely in SCORING:
`tests.eval.evaluators.ALL_EVALUATORS` now includes `correctness_judge`, which
is fed `reference_answer` and flags factual contradictions.

`expected_entities` are intentionally unchanged from v3 so `entity_coverage`
stays comparable; substring matching cannot robustly verify numeric negatives
like "0%" (the normalizer strips the "%"), which is precisely why the
reference-grounded judge is the real fix.
"""

from tests.eval.dataset_v3 import (  # noqa: F401  (BenchmarkExampleV3 re-exported for callers)
    BENCHMARK_EXAMPLES_V3,
    BenchmarkExampleV3,
)

DATASET_NAME_V4 = "netbox-benchmark-v4"
DATASET_DESCRIPTION_V4 = (
    "Cross-domain NetBox queries (DCIM + IPAM + Tenancy), identical questions and "
    "verified reference answers to netbox-benchmark-v3, re-verified against live "
    "NetBox 2026-07-20. Distinct namespace so it can be scored with the "
    "reference-grounded correctness_judge (which reads reference_answer and flags "
    "factual contradictions) without disturbing the v3 experiments. v3's evaluators "
    "never read reference_answer, so a hallucinated '~7.7% IP utilization' answer "
    "scored 0.9 completeness; v4 fixes the scoring, not the data."
)

# Data is identical to v3 (reference answers already correct). The v4 improvement
# is the scoring (correctness_judge), not the examples.
BENCHMARK_EXAMPLES_V4 = BENCHMARK_EXAMPLES_V3


def ensure_dataset_v4(client=None):
    """Create netbox-benchmark-v4 in LangSmith if absent. Idempotent."""
    if client is None:
        from dotenv import load_dotenv
        from langsmith import Client

        load_dotenv()
        client = Client()

    if client.has_dataset(dataset_name=DATASET_NAME_V4):
        return client.read_dataset(dataset_name=DATASET_NAME_V4)

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME_V4,
        description=DATASET_DESCRIPTION_V4,
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[ex.to_input() for ex in BENCHMARK_EXAMPLES_V4],
        outputs=[ex.to_reference_output() for ex in BENCHMARK_EXAMPLES_V4],
    )
    return dataset


if __name__ == "__main__":
    ds = ensure_dataset_v4()
    print(f"Dataset ready: {ds.name} (id={ds.id})")
    print(f"Examples: {len(BENCHMARK_EXAMPLES_V4)}")
