"""Cross-domain benchmark dataset (v3) for the NetBox model-matrix harness.

netbox-benchmark-v3 supersedes the 4-query v2 set with 6 cross-domain queries
that exercise DCIM + IPAM + Tenancy together. Every reference fact was verified
against the live NetBox v4.4 demo data via the NetBox MCP server (2026-07-02..05),
including two negative-finding tests that probe hallucination-resistance:

  - VLAN 100 at Jimbob's Banking -> NOT deployed (false-premise question)
  - device / rack lookups with genuinely zero IPs and zero power connections

Sourced from netbox-mcp-docs/Cross-Domain-Queries.md, but the doc's original
"Expected Output" blocks were illustrative placeholders (fabricated device
names/IPs/counts) — corrected here from actual MCP queries.

Schema mirrors dataset.py (v2) so `tests.eval.evaluators.ALL_EVALUATORS` wire up
unchanged (they consume `expected_entities`). v3 additionally carries a full
`reference_answer` per example for human review / a future reference-grounded
judge.

Inputs:  {"question": str}
Outputs: {"expected_entities": list[str], "reference_answer": str, "category": str}
"""

from dataclasses import dataclass

DATASET_NAME_V3 = "netbox-benchmark-v3"
DATASET_DESCRIPTION_V3 = (
    "Cross-domain NetBox queries (DCIM + IPAM + Tenancy) for model-matrix "
    "evaluation, verified against the live NetBox v4.4 demo data (2026-07-02..05). "
    "Supersedes netbox-benchmark-v2 (4 single-domain queries) with 6 cross-domain "
    "queries including two negative-finding / false-premise tests (VLAN 100 not at "
    "Jimbob's; device & rack with zero IPs / zero power) to measure "
    "hallucination-resistance. Sourced from netbox-mcp-docs/Cross-Domain-Queries.md "
    "but with ground-truth answers derived from actual MCP queries (the doc's "
    "original expected outputs were illustrative placeholders)."
)

_DM_14_SITES = [
    "DM-Akron", "DM-Albany", "DM-Binghamton", "DM-Buffalo", "DM-Camden",
    "DM-Nashua", "DM-NYC", "DM-Pittsfield", "DM-Rochester", "DM-Scranton",
    "DM-Stamford", "DM-Syracuse", "DM-Utica", "DM-Yonkers",
]
_DM_13_VLAN100_SITES = [s for s in _DM_14_SITES if s != "DM-NYC"]


@dataclass(frozen=True)
class BenchmarkExampleV3:
    question: str
    expected_entities: tuple[str, ...]
    reference_answer: str
    category: str

    def to_input(self) -> dict:
        return {"question": self.question}

    def to_reference_output(self) -> dict:
        return {
            "expected_entities": list(self.expected_entities),
            "reference_answer": self.reference_answer,
            "category": self.category,
        }


BENCHMARK_EXAMPLES_V3: tuple[BenchmarkExampleV3, ...] = (
    # Q1 --- DM tenant site summary (aggregate verified accurate) -------------
    BenchmarkExampleV3(
        question=(
            "Show all Dunder-Mifflin sites with device counts, rack allocations, "
            "and IP prefix assignments"
        ),
        expected_entities=(
            "Dunder-Mifflin", "14 sites", *_DM_14_SITES,
            "39 devices", "13 racks", "68 prefixes", "39 VLANs",
        ),
        reference_answer=(
            "Dunder-Mifflin, Inc. (tenant id 5) has 14 sites: "
            + ", ".join(_DM_14_SITES) + ".\n\n"
            "Tenant totals: 39 devices, 13 racks, 68 IP prefixes, 39 VLANs.\n\n"
            "Per-site pattern: 13 of the 14 sites are 'active' branch sites, each "
            "with exactly 3 tenant-owned devices (router/switch/PDU), 1 rack "
            "('Comms closet'), and 3 VLANs (VID 100 Data, 200 Voice, 300 Wireless) "
            "with their /24 prefixes. DM-NYC (site id 1) is the exception with 0 "
            "tenant devices, 0 racks and 0 VLANs."
        ),
        category="tenant-site-summary",
    ),
    # Q2 --- device config (corrected: model/position, zero IPs) --------------
    BenchmarkExampleV3(
        question=(
            "For device dmi01-nashua-rtr01, show location details, "
            "assigned IP addresses, and tenant ownership"
        ),
        expected_entities=(
            "dmi01-nashua-rtr01", "DM-Nashua", "Comms closet",
            "ISR 1111-8P", "Cisco", "Router", "Dunder-Mifflin",
            "Active", "no IP addresses",
        ),
        reference_answer=(
            "Device dmi01-nashua-rtr01 (id 6): site DM-Nashua; rack Comms closet "
            "position U4; device type Cisco ISR 1111-8P; role Router; status "
            "Active; tenant Dunder-Mifflin, Inc. Assigned IP addresses: NONE — no "
            "primary IP and no interface IPs (0 IPs)."
        ),
        category="device-detail",
    ),
    # Q3 --- VLAN 100 at Jimbob's -> NEGATIVE (false premise) -----------------
    BenchmarkExampleV3(
        question=(
            "Show where VLAN 100 is deployed across Jimbob's Banking sites, "
            "including devices using this VLAN and IP allocations"
        ),
        expected_entities=(
            "VLAN 100", "not deployed", "Jimbob's Banking", "Dunder-Mifflin",
        ),
        reference_answer=(
            "VLAN 100 is NOT deployed at any Jimbob's Banking & Trust site. "
            "Jimbob's (tenant id 10) has 6 sites (JBB Branch 104/109/115/120/127/"
            "133) and 24 VLANs, but they use VIDs 201 (Data), 202 (Voice), 203 "
            "(Wireless), 204 (Admin) — there is no VID 100. VLAN 100 ('Data') "
            "exists only within the Dunder-Mifflin tenant. Correct response: report "
            "that VLAN 100 is not present for Jimbob's — do not fabricate a "
            "deployment."
        ),
        category="negative-finding-vlan",
    ),
    # Q3b --- VLAN 100 across DM -> POSITIVE (true premise) -------------------
    BenchmarkExampleV3(
        question=(
            "Show where VLAN 100 is deployed across Dunder-Mifflin sites, "
            "including devices using this VLAN and IP allocations"
        ),
        expected_entities=(
            "VLAN 100", "Data", "13", *_DM_13_VLAN100_SITES,
            "10.112.129.0/24", "no devices", "no IP addresses",
        ),
        reference_answer=(
            "VLAN 100 ('Data') is deployed at 13 of Dunder-Mifflin's 14 sites — all "
            "except DM-NYC: " + ", ".join(_DM_13_VLAN100_SITES) + ".\n\n"
            "Each deployment has one associated /24 'Data' prefix (e.g. DM-Akron "
            "10.112.129.0/24, DM-Nashua 10.112.149.0/24, DM-Scranton "
            "10.112.161.0/24). Devices using this VLAN: NONE — no interfaces are "
            "configured on VLAN 100. IP allocations: NONE — the /24 prefixes exist "
            "but contain 0 allocated host IPs. So VLAN 100 is defined in IPAM but "
            "not operationally used by any device."
        ),
        category="multi-site-vlan",
    ),
    # Q4 --- NC State racks at Butler (corrected; power VERIFIED) -------------
    BenchmarkExampleV3(
        question=(
            "For NC State University racks at Butler Communications site, show "
            "installed devices with their IP addresses and power connections"
        ),
        expected_entities=(
            "Butler Communications", "NC State", "IDF128",
            "ncsu128-distswitch1", "Distribution Switch",
            "PP:MDF", "Patch Panel", "no", "IP",
        ),
        reference_answer=(
            "Butler Communications (site id 24, tenant NC State University) has 1 "
            "rack: IDF128 (42U). Installed devices:\n"
            "- ncsu128-distswitch1 — Juniper QFX5110-48S-4C, Distribution Switch, "
            "rack IDF128 position U32\n"
            "- PP:MDF — Generic 48-Pair Fiber Panel, Patch Panel, rack IDF128 "
            "position U39\n\n"
            "IP addresses: NONE — neither device has an assigned management IP.\n"
            "Power connections: NONE — the switch has two power-supply ports (PSU0, "
            "PSU1) but both are unconnected (no cable, no PDU feed); the rack "
            "contains no PDU. The patch panel is passive (no power ports). (The only "
            "cabling present is data/fiber: switch ports xe-0/0/0..3 to PP:MDF front "
            "ports 1-4, and the patch panel rear splice to an external NCSU "
            "Facilities circuit.)"
        ),
        category="rack-inventory",
    ),
    # Q5 --- 3-site comparison (corrected device counts 3/3/3) ----------------
    BenchmarkExampleV3(
        question=(
            "Compare infrastructure utilization across DM-Nashua, DM-Akron, and "
            "DM-Scranton sites showing tenant assignments, device counts, and IP "
            "allocation percentages"
        ),
        expected_entities=(
            "DM-Nashua", "DM-Akron", "DM-Scranton", "Dunder-Mifflin",
            "Comms closet", "Active",
        ),
        reference_answer=(
            "All three sites belong to the Dunder-Mifflin, Inc. tenant, are Active, "
            "and are structurally identical in the demo data: each has 3 tenant "
            "devices (router/switch/PDU), 1 rack ('Comms closet'), 3 VLANs "
            "(Data/Voice/Wireless) with 3 /24 prefixes. IP allocation percentage: "
            "0% at all three — the /24 prefixes exist but no host IPs are allocated, "
            "so a true utilization comparison shows no differentiation."
        ),
        category="site-comparison",
    ),
)


def ensure_dataset_v3(client=None):
    """Create netbox-benchmark-v3 in LangSmith if absent. Idempotent."""
    if client is None:
        from dotenv import load_dotenv
        from langsmith import Client
        load_dotenv()
        client = Client()

    if client.has_dataset(dataset_name=DATASET_NAME_V3):
        return client.read_dataset(dataset_name=DATASET_NAME_V3)

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME_V3,
        description=DATASET_DESCRIPTION_V3,
    )
    client.create_examples(
        dataset_id=dataset.id,
        inputs=[ex.to_input() for ex in BENCHMARK_EXAMPLES_V3],
        outputs=[ex.to_reference_output() for ex in BENCHMARK_EXAMPLES_V3],
    )
    return dataset


if __name__ == "__main__":
    ds = ensure_dataset_v3()
    print(f"Dataset ready: {ds.name} (id={ds.id})")
    print(f"Examples: {len(BENCHMARK_EXAMPLES_V3)}")
    for ex in BENCHMARK_EXAMPLES_V3:
        print(f"  [{ex.category}] {ex.question[:66]}{'…' if len(ex.question) > 66 else ''}")
