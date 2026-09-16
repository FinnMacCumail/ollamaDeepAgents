"""Layered, idempotent seeder for netbox-benchmark-v5.

Usage:
    # 1. prove the payload shapes without touching the instance
    ./venv/bin/python -m scripts.seed_benchmark_v5.seed --dry-run

    # 2. seed one layer at a time, verifying between each
    ./venv/bin/python -m scripts.seed_benchmark_v5.seed --layers org
    ./venv/bin/python -m scripts.seed_benchmark_v5.seed --layers lookups,devicetypes

    # 3. or everything (layers run in dependency order regardless of the order given)
    ./venv/bin/python -m scripts.seed_benchmark_v5.seed --layers all

Every layer is idempotent: objects are matched by natural key and only created
when absent, so a partially-failed run is fixed by re-running it. Rollback of
last resort is the baseline snapshot in /home/ola/dev/netboxdev/netbox-snapshots.

Writes use the SEEDER token. The agent's own token stays read-only.
"""

from __future__ import annotations

import argparse
import sys

from . import blueprint as B
from . import config as C
from .client import NetBoxSeeder, SeedError, preflight
from .validate import validate

# Layers in dependency order. Later layers assume earlier ones have run.
LAYER_ORDER = [
    "lookups",       # tag, roles, platforms, prefix roles, circuit types, providers
    "org",           # tenant group/tenant/region/site groups/sites/locations/racks
    "devicetypes",   # 4 new device types + component templates
    "devices",       # devices + explicit power ports where no template exists
    "ipam",          # VRFs, VLAN groups, VLANs, prefixes, IPs, primary IPs
    "cabling",       # interface<->interface, patch-panel trunks, console, power
    "power",         # panels, feeds, PDU chains
    "circuits",      # providers' circuits + terminations
    "virt",          # cluster groups, clusters, VMs, virtual disks
    "defects",       # the planted-defect answer key
    "journal",       # journal entries + the change-history activity phase
]

# Layers implemented so far. The rest are written once the earlier layers are
# verified against the live instance (deliberate: each builds on proven state).
IMPLEMENTED = {"lookups", "org", "devicetypes", "devices", "ipam"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _ref(obj: dict | None) -> dict | None:
    """NetBox accepts {"id": N} for nested-object FKs."""
    return {"id": obj["id"]} if obj else None


# --------------------------------------------------------------------------
# layer: lookups
# --------------------------------------------------------------------------
def layer_lookups(s: NetBoxSeeder, state: dict) -> None:
    state["tag"] = s.get_or_create(
        "extras/tags",
        match={"slug": C.SEED_TAG["slug"]},
        payload=dict(C.SEED_TAG),
    )

    roles = {}
    for r in C.NEW_DEVICE_ROLES:
        roles[r["slug"]] = s.get_or_create(
            "dcim/device-roles", match={"slug": r["slug"]}, payload=s.tagged(dict(r))
        )
    state["new_device_roles"] = roles

    plats = {}
    for p in C.NEW_PLATFORMS:
        plats[p["slug"]] = s.get_or_create(
            "dcim/platforms", match={"slug": p["slug"]}, payload=s.tagged(dict(p))
        )
    state["platforms"] = plats

    pref_roles = {}
    for r in C.NEW_PREFIX_ROLES:
        pref_roles[r["slug"]] = s.get_or_create(
            "ipam/roles", match={"slug": r["slug"]}, payload=dict(r)
        )
    state["prefix_roles"] = pref_roles

    ctypes = {}
    for t in B.NEW_CIRCUIT_TYPES:
        ctypes[t["slug"]] = s.get_or_create(
            "circuits/circuit-types", match={"slug": t["slug"]}, payload=s.tagged(dict(t))
        )
    state["new_circuit_types"] = ctypes

    provs = {}
    for p in B.PROVIDERS:
        provs[p["slug"]] = s.get_or_create(
            "circuits/providers", match={"slug": p["slug"]}, payload=s.tagged(dict(p))
        )
    state["providers"] = provs


# --------------------------------------------------------------------------
# layer: org
# --------------------------------------------------------------------------
def layer_org(s: NetBoxSeeder, state: dict) -> None:
    group = s.get_or_create(
        "tenancy/tenant-groups",
        match={"slug": C.TENANT_GROUP["slug"]},
        payload=dict(C.TENANT_GROUP),
    )
    tenant = s.get_or_create(
        "tenancy/tenants",
        match={"slug": C.TENANT["slug"]},
        payload=s.tagged({**C.TENANT, "group": _ref(group)}),
    )
    state["tenant"] = tenant

    region = s.get_or_create(
        "dcim/regions",
        match={"slug": C.REGION["slug"]},
        payload={
            "name": C.REGION["name"],
            "slug": C.REGION["slug"],
            "parent": {"id": C.REGION["parent_id"]},
        },
    )
    state["region"] = region

    groups = {}
    for g in B.SITE_GROUPS:
        groups[g["slug"]] = s.get_or_create(
            "dcim/site-groups", match={"slug": g["slug"]}, payload=dict(g)
        )

    sites, locations = {}, {}
    for spec in B.SITES:
        site = s.get_or_create(
            "dcim/sites",
            match={"slug": spec["slug"]},
            payload=s.tagged({
                "name": spec["name"],
                "slug": spec["slug"],
                "status": spec["status"],
                "region": _ref(region),
                "group": _ref(groups[spec["group"]]),
                "tenant": _ref(tenant),
            }),
        )
        sites[spec["slug"]] = site
        for loc_name in spec["locations"]:
            slug = f"{spec['slug']}-{loc_name.lower().replace(' ', '-')}"
            locations[(spec["slug"], loc_name)] = s.get_or_create(
                "dcim/locations",
                match={"slug": slug},
                payload={
                    "name": loc_name,
                    "slug": slug,
                    "site": _ref(site),
                    "status": "active",
                    "tenant": _ref(tenant),
                },
            )
    state["sites"] = sites
    state["locations"] = locations

    racks = {}
    for spec in B.RACKS:
        racks[spec["name"]] = s.get_or_create(
            "dcim/racks",
            match={"name": spec["name"], "site_id": sites[spec["site"]]["id"]},
            payload=s.tagged({
                "name": spec["name"],
                "site": _ref(sites[spec["site"]]),
                "location": _ref(locations[(spec["site"], spec["location"])]),
                "status": spec["status"],
                "u_height": spec["u_height"],
                "width": C.RACK_WIDTH,
                "tenant": _ref(tenant),
            }),
        )
    state["racks"] = racks

    # Reservations need a user; attribute them to the seeder account so the
    # provenance of seeded data is obvious in the UI.
    seeder_user = s.get("users/users", username="seeder")
    if seeder_user:
        for res in B.RACK_RESERVATIONS:
            s.get_or_create(
                "dcim/rack-reservations",
                match={"rack_id": racks[res["rack"]]["id"],
                       "description": res["description"]},
                payload={
                    "rack": _ref(racks[res["rack"]]),
                    "units": res["units"],
                    "user": {"id": seeder_user[0]["id"]},
                    "tenant": _ref(tenant),
                    "description": res["description"],
                },
            )


# --------------------------------------------------------------------------
# layer: devicetypes
# --------------------------------------------------------------------------
def layer_devicetypes(s: NetBoxSeeder, state: dict) -> None:
    types = {}
    for spec in C.NEW_DEVICE_TYPES:
        dt = s.get_or_create(
            "dcim/device-types",
            match={"slug": spec["slug"]},
            payload=s.tagged({
                "manufacturer": {"id": C.MANUFACTURERS[spec["manufacturer"]]},
                "model": spec["model"],
                "slug": spec["slug"],
                "u_height": spec["u_height"],
            }),
        )
        types[spec["slug"]] = dt
        dt_ref = _ref(dt)

        # interface templates: (name, type) or (name, type, mgmt_only)
        for tpl in spec["interfaces"]:
            name, iftype = tpl[0], tpl[1]
            mgmt = bool(tpl[2]) if len(tpl) > 2 else False
            # NB: the filter is `device_type_id`; `devicetype_id` is silently
            # IGNORED by NetBox and would match every template on the instance.
            s.get_or_create(
                "dcim/interface-templates",
                match={"device_type_id": dt["id"], "name": name},
                payload={"device_type": dt_ref, "name": name,
                         "type": iftype, "mgmt_only": mgmt},
            )
        for name, ctype in spec.get("console", []):
            s.get_or_create(
                "dcim/console-port-templates",
                match={"device_type_id": dt["id"], "name": name},
                payload={"device_type": dt_ref, "name": name, "type": ctype},
            )
        for name, ptype, maximum, allocated in spec.get("power", []):
            s.get_or_create(
                "dcim/power-port-templates",
                match={"device_type_id": dt["id"], "name": name},
                payload={"device_type": dt_ref, "name": name, "type": ptype,
                         "maximum_draw": maximum, "allocated_draw": allocated},
            )
        for name in spec.get("console_server_ports", []):
            s.get_or_create(
                "dcim/console-server-port-templates",
                match={"device_type_id": dt["id"], "name": name},
                payload={"device_type": dt_ref, "name": name,
                         "type": C.CONSOLE_PORT_TYPE},
            )
    state["new_device_types"] = types


# --------------------------------------------------------------------------
# layer: devices
# --------------------------------------------------------------------------
def _resolve_device_types(s: NetBoxSeeder) -> dict[str, dict]:
    """Map blueprint type keys -> live device-type objects.

    Reused demo types are looked up by their pinned id; new types by slug.
    """
    out: dict[str, dict] = {}
    for key, spec in C.REUSE_DEVICE_TYPES.items():
        found = s.get("dcim/device-types", id=spec["id"])
        if not found:
            raise SeedError(f"reusable device type id={spec['id']} ({key}) not found")
        out[key] = found[0]
    for spec in C.NEW_DEVICE_TYPES:
        found = s.get("dcim/device-types", slug=spec["slug"])
        if not found:
            raise SeedError(f"device type {spec['slug']} missing -- run the "
                            "'devicetypes' layer first")
        out[spec["slug"]] = found[0]
    return out


def _resolve_roles(s: NetBoxSeeder) -> dict[str, dict]:
    out = {}
    for slug in set(C.DEVICE_ROLES) | {r["slug"] for r in C.NEW_DEVICE_ROLES}:
        found = s.get("dcim/device-roles", slug=slug)
        if found:
            out[slug] = found[0]
    return out


def layer_devices(s: NetBoxSeeder, state: dict) -> None:
    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run the 'org' layer first")
    tenant = tenant[0]

    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tenant["id"])}
    racks = {x["name"]: x for x in s.get("dcim/racks", tenant_id=tenant["id"])}
    types = _resolve_device_types(s)
    roles = _resolve_roles(s)
    platforms = {x["slug"]: x for x in s.get("dcim/platforms")}

    devices: dict[str, dict] = {}
    for spec in B.DEVICES:
        name = spec["name"]
        site = sites[spec["site"]]
        payload = {
            "name": name,
            "device_type": _ref(types[spec["type"]]),
            "role": _ref(roles[spec["role"]]),
            "site": _ref(site),
            "status": spec.get("status", "active"),
        }
        # `tenant: False` marks a DELIBERATE defect (D14: device with no tenant)
        if spec.get("tenant", True) is not False:
            payload["tenant"] = _ref(tenant)
        if spec.get("platform"):
            payload["platform"] = _ref(platforms[spec["platform"]])
        if spec.get("rack"):
            payload["rack"] = _ref(racks[spec["rack"]])
            if spec.get("position") is not None:
                payload["position"] = spec["position"]
                payload["face"] = "front"
        devices[name] = s.get_or_create(
            "dcim/devices",
            match={"name": name, "site_id": site["id"]},
            payload=s.tagged(payload),
        )
    state["devices"] = devices

    # Power ports do NOT exist for every type (e.g. C9200-48P has no
    # power-port template -- verified 2026-09-16; the demo data creates them
    # per-device too). Create them explicitly so the power chain and the
    # dual-PSU defect have something to attach to.
    for spec in B.DEVICES:
        tkey = spec["type"]
        reuse = C.REUSE_DEVICE_TYPES.get(tkey)
        if not reuse or reuse.get("power_ports") is not None:
            continue          # template exists, or it is a new type
        dev = devices[spec["name"]]
        if s.dry_run or not s.get("dcim/power-ports", device_id=dev["id"]):
            s.get_or_create(
                "dcim/power-ports",
                match={"device_id": dev["id"], "name": "Power Port"},
                payload={"device": _ref(dev), "name": "Power Port",
                         "type": C.POWER_PORT_TYPE,
                         "maximum_draw": 370, "allocated_draw": 125},
            )


# --------------------------------------------------------------------------
# layer: ipam
# --------------------------------------------------------------------------
def layer_ipam(s: NetBoxSeeder, state: dict) -> None:
    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run the 'org' layer first")
    tenant = tenant[0]
    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tenant["id"])}
    devices = {x["name"]: x for x in s.get("dcim/devices", tenant_id=tenant["id"])}
    # D14's device has no tenant, so fetch HVL devices by site as well
    for site in sites.values():
        for d in s.get("dcim/devices", site_id=site["id"]):
            devices.setdefault(d["name"], d)
    roles = {x["slug"]: x for x in s.get("ipam/roles")}

    # -- VRFs ---------------------------------------------------------------
    vrfs = {}
    for spec in (B.VRF_CORP, B.VRF_GUEST):
        vrfs[spec["name"]] = s.get_or_create(
            "ipam/vrfs",
            match={"name": spec["name"]},
            payload=s.tagged({**spec, "tenant": _ref(tenant)}),
        )
    corp, guest = vrfs[B.VRF_CORP["name"]], vrfs[B.VRF_GUEST["name"]]

    # -- VLAN groups + VLANs (VID 100 is FORBIDDEN -- v4 collision) ---------
    vlans: dict[tuple[str, int], dict] = {}
    for slug, site in sites.items():
        grp = s.get_or_create(
            "ipam/vlan-groups",
            match={"slug": f"{slug}-vlans"},
            payload={"name": f"{site['name']} VLANs", "slug": f"{slug}-vlans",
                     "scope_type": "dcim.site", "scope_id": site["id"]},
        )
        plan = B.VLANS_DC if slug == "hvl-sea-dc1" else B.VLANS_BRANCH
        for vid, name in plan:
            if vid in C.FORBIDDEN_VIDS:
                raise SeedError(f"refusing to create FORBIDDEN VID {vid}")
            vlans[(slug, vid)] = s.get_or_create(
                "ipam/vlans",
                match={"vid": vid, "group_id": grp["id"]},
                payload=s.tagged({
                    "vid": vid, "name": name, "group": _ref(grp),
                    "site": _ref(site), "tenant": _ref(tenant),
                    "status": "active",
                }),
            )

    # -- prefixes -----------------------------------------------------------
    prefixes = {}
    for pfx, status, role, site_slug, vid, _fill, note in B.PREFIX_PLAN:
        payload = {
            "prefix": pfx, "status": status, "vrf": _ref(corp),
            "tenant": _ref(tenant), "description": note,
        }
        if role:
            payload["role"] = _ref(roles[role])
        if site_slug:
            payload["scope_type"] = "dcim.site"
            payload["scope_id"] = sites[site_slug]["id"]
        if vid and (site_slug, vid) in vlans:
            payload["vlan"] = _ref(vlans[(site_slug, vid)])
        prefixes[pfx] = s.get_or_create(
            "ipam/prefixes",
            match={"prefix": pfx, "vrf_id": corp["id"]},
            payload=s.tagged(payload),
        )

    # /31 point-to-point links: 100% utilized by definition
    for p2p in B.P2P_LINKS:
        prefixes[p2p] = s.get_or_create(
            "ipam/prefixes",
            match={"prefix": p2p, "vrf_id": corp["id"]},
            payload=s.tagged({
                "prefix": p2p, "status": "active", "vrf": _ref(corp),
                "tenant": _ref(tenant), "role": _ref(roles["point-to-point"]),
                "description": "P2P link",
            }),
        )

    # D5: four IDENTICAL guest prefixes, only possible because the GUEST VRF
    # has enforce_unique=False. Intentional duplicate -- not a mistake.
    for slug in ["hvl-sea-hq", "hvl-tac-br01", "hvl-por-br02", "hvl-spo-br03"]:
        # Cannot use get_or_create here: all four are the SAME prefix string,
        # so the natural key is (prefix, vrf, scope). Match on the scope too,
        # or a re-run would create duplicates of the duplicates.
        already = s.get(
            "ipam/prefixes",
            prefix=C.GUEST_DUP_PREFIX,
            vrf_id=guest["id"],
            scope_id=sites[slug]["id"],
        )
        if already:
            # keep the tally honest -- this path bypasses get_or_create
            s._tally(s.reused, "ipam/prefixes")
        else:
            s.create("ipam/prefixes", s.tagged({
                "prefix": C.GUEST_DUP_PREFIX, "status": "active",
                "vrf": _ref(guest), "tenant": _ref(tenant),
                "role": _ref(roles["guest"]),
                "scope_type": "dcim.site", "scope_id": sites[slug]["id"],
                "description": f"Guest wifi ({slug}) - duplicate by design",
            }))

    # D4: an active prefix nested inside another ACTIVE (non-container) prefix
    s.get_or_create(
        "ipam/prefixes",
        match={"prefix": "10.60.36.128/25", "vrf_id": corp["id"]},
        payload=s.tagged({
            "prefix": "10.60.36.128/25", "status": "active", "vrf": _ref(corp),
            "tenant": _ref(tenant),
            "description": "nested inside active 10.60.36.0/24 (defect D4)",
        }),
    )

    state["vrfs"], state["vlans"], state["prefixes"] = vrfs, vlans, prefixes
    state["ipam_devices"] = devices


LAYERS = {
    "lookups": layer_lookups,
    "org": layer_org,
    "devicetypes": layer_devicetypes,
    "devices": layer_devices,
    "ipam": layer_ipam,
}


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Seed the HVL benchmark tenant.")
    ap.add_argument("--dry-run", action="store_true",
                    help="perform no writes; prove payload shapes only")
    ap.add_argument("--layers", default="all",
                    help=f"comma-separated, or 'all'. Known: {','.join(LAYER_ORDER)}")
    ap.add_argument("--skip-preflight", action="store_true")
    args = ap.parse_args(argv)

    errs, warn = validate()
    if errs:
        print("blueprint validation FAILED -- refusing to seed:", file=sys.stderr)
        for e in errs:
            print(f"  x {e}", file=sys.stderr)
        return 1
    print(f"blueprint validation OK ({len(warn)} warning(s))")

    if args.layers == "all":
        wanted = [l for l in LAYER_ORDER if l in IMPLEMENTED]
        skipped = [l for l in LAYER_ORDER if l not in IMPLEMENTED]
        if skipped:
            print(f"NOTE: not yet implemented, skipping: {', '.join(skipped)}")
    else:
        asked = [x.strip() for x in args.layers.split(",") if x.strip()]
        unknown = [x for x in asked if x not in LAYER_ORDER]
        if unknown:
            print(f"unknown layer(s): {unknown}", file=sys.stderr)
            return 2
        missing = [x for x in asked if x not in IMPLEMENTED]
        if missing:
            print(f"layer(s) not yet implemented: {missing}", file=sys.stderr)
            return 2
        wanted = [l for l in LAYER_ORDER if l in asked]   # dependency order

    s = NetBoxSeeder(dry_run=args.dry_run)
    try:
        if not args.skip_preflight:
            preflight(s)
        state: dict = {}
        for name in wanted:
            print(f"\n--- layer: {name} ---")
            LAYERS[name](s, state)
            print(f"    ok ({name})")
        print(s.summary())
    except SeedError as e:
        print(f"\nSEED FAILED:\n{e}", file=sys.stderr)
        print(s.summary(), file=sys.stderr)
        return 1
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
