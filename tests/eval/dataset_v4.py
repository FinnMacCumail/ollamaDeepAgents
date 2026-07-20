"""netbox-benchmark-v4 — same questions + verified reference answers as v3, in a
clean namespace intended to be scored with the reference-grounded
`correctness_judge`.

Why a new version rather than editing v3: the 2026-07-05 v3 experiments used the
old evaluator set, which never read `reference_answer`. That let a confidently
hallucinated "~7.7% IP utilization" answer score 0.9 on completeness, because
the judge was only ever shown `expected_entities` (positive keywords), never the
ground truth. See `docs/development/2026-07-20_netbox-benchmark-v4-rescore.md`.

The primary change is SCORING: `tests.eval.evaluators.ALL_EVALUATORS` now
includes `correctness_judge`, fed `reference_answer` to flag contradictions.

v4 also CLARIFIES two reference answers that were under-specified in v3 and
caused the correctness judge to penalise defensible answers (verified vs live
NetBox 2026-07-20):
  - device count: each active DM site has 3 tenant-owned devices (router/switch/
    PDU) PLUS 1 unnamed tenant-less patch panel → both "3" (tenant) and "4"
    (physical) are acceptable.
  - prefix count: each site's /22 block holds 5 prefixes (a /22 container + a
    /28 + the three VLAN /24s), so both "3 /24 prefixes" and "5 prefixes" are
    acceptable (confirmed: 10.112.148.0/22 → 5 prefixes).
  - IP allocation is HARDENED to 0%: all 180 NetBox IPs live in the unrelated
    172.16.0.0/24 range; any non-zero utilization figure is a fabrication.
Only the `tenant-site-summary` and `site-comparison` reference answers differ
from v3; all other examples are identical.

`expected_entities` are unchanged from v3 so `entity_coverage` stays comparable;
substring matching cannot robustly verify numeric negatives like "0%" (the
normalizer strips the "%"), which is why the reference-grounded judge is the fix.
"""

from dataclasses import replace

from tests.eval.dataset_v3 import (  # noqa: F401  (BenchmarkExampleV3 re-exported for callers)
    _DM_14_SITES,
    BENCHMARK_EXAMPLES_V3,
    BenchmarkExampleV3,
)

# Clarified reference answers (v4 only) — remove the device/prefix-count ambiguity
# the judge tripped on, and harden the IP-allocation ground truth.
_REFERENCE_OVERRIDES = {
    "tenant-site-summary": (
        "Dunder-Mifflin, Inc. (tenant id 5) has 14 sites: "
        + ", ".join(_DM_14_SITES) + ".\n\n"
        "Tenant totals: 39 devices, 13 racks, 68 IP prefixes, 39 VLANs.\n\n"
        "Per-site pattern: 13 of the 14 sites are 'active' branch sites. Each "
        "active site has 3 tenant-owned devices (a router, an access switch, a "
        "PDU) PLUS 1 unnamed tenant-less patch panel — so a tenant-scoped count "
        "is 3 and a physical count is 4; BOTH '3 devices' and '4 devices' are "
        "acceptable. Each also has 1 rack ('Comms closet'), 3 VLANs (VID 100 "
        "Data / 200 Voice / 300 Wireless), and 5 IP prefixes (a /22 container, a "
        "/28, and the three VLAN /24s) — so both '3 /24 prefixes' and '5 "
        "prefixes' are acceptable. DM-NYC (site id 1) is the exception with 0 "
        "tenant devices, 0 racks and 0 VLANs."
    ),
    "site-comparison": (
        "All three sites belong to the Dunder-Mifflin, Inc. tenant, are Active, "
        "and are structurally identical in the demo data. Each has: 3 "
        "tenant-owned devices (router/switch/PDU) plus 1 unnamed tenant-less "
        "patch panel — both '3 devices' (tenant) and '4 devices' (physical) are "
        "acceptable; 1 rack ('Comms closet'); 3 VLANs (Data/Voice/Wireless); and "
        "5 IP prefixes per site (a /22 container + a /28 + three VLAN /24s). IP "
        "allocation percentage: 0% at all three — the /24 prefixes exist but no "
        "host IPs are allocated. Every one of the 180 IP addresses in NetBox "
        "lives in the unrelated 172.16.0.0/24 range; none are in the sites' "
        "10.112.x prefixes. A true utilization comparison shows no "
        "differentiation, and ANY non-zero IP-utilization figure (e.g. 7.7%, "
        "17.6%, 100%) is a fabrication and is wrong."
    ),
}


def _clarify(ex: BenchmarkExampleV3) -> BenchmarkExampleV3:
    new_ref = _REFERENCE_OVERRIDES.get(ex.category)
    return replace(ex, reference_answer=new_ref) if new_ref else ex

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

# v4 examples = v3, with the two under-specified reference answers clarified.
BENCHMARK_EXAMPLES_V4 = tuple(_clarify(ex) for ex in BENCHMARK_EXAMPLES_V3)


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
