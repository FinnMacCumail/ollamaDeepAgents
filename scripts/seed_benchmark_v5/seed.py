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
    "ipam",          # VRFs, VLAN groups, VLANs, prefixes
    "ipaddrs",       # IPs on interfaces, primary IPs, defects D1/D2/D3
    "ipfill",        # filler host IPs to reach the intended utilization spread
    "power",         # panels, feeds
    "circuits",      # providers' circuits + terminations
    # cabling MUST follow circuits: the WAN cables terminate on circuit
    # terminations, which do not exist until that layer has run.
    "cabling",       # interface<->interface, patch-panel trunks, console, power
    "virt",          # cluster groups, clusters, VMs, virtual disks
    "defects",       # the planted-defect answer key
    "journal",       # journal entries + the change-history activity phase
]

# Layers implemented so far. The rest are written once the earlier layers are
# verified against the live instance (deliberate: each builds on proven state).
IMPLEMENTED = {"lookups", "org", "devicetypes", "devices", "ipam", "ipaddrs",
               "ipfill", "circuits", "power", "virt", "cabling", "defects",
               "journal"}


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


# --------------------------------------------------------------------------
# layer: ipaddrs  (IPs on interfaces + primary IPs + defects D1/D2/D3)
# --------------------------------------------------------------------------
# Devices that deliberately get NO primary IP (defect D1).
NO_PRIMARY_IP = {"sea-dc1-leaf04", "hq-acc04", "por-br02-sw01"}

# Which interface carries the management/primary address, per device type.
# Verified template names -- see config.REUSE_DEVICE_TYPES.
_MGMT_IFACE = {
    "branch-router": "GigabitEthernet0/0/1",
    "access-switch": "GigabitEthernet0",
    "leaf": "fxp0",
    "core": "em0",
    "pa-3220": "management",
    "cm7116-2": "net1",
    "poweredge-r650": "idrac",
    "u6-pro": "eth0",
}
# L3 devices get a Loopback0 (virtual) carrying a /32 with role=loopback.
_LOOPBACK_ROLES = {"router", "core-switch", "distribution-switch", "firewall"}


def _mgmt_prefix_for(site_slug: str) -> str | None:
    """Management subnet per site (must match PREFIX_PLAN)."""
    return {
        "hvl-sea-dc1": "10.60.1.0/24",
        "hvl-sea-hq": "10.60.20.0/27",
        "hvl-tac-br01": "10.60.33.0/28",
        "hvl-por-br02": "10.60.37.0/28",
        "hvl-spo-br03": "10.60.41.0/28",
    }.get(site_slug)


def layer_ipaddrs(s: NetBoxSeeder, state: dict) -> None:
    import ipaddress as _ip

    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tenant = tenant[0]
    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tenant["id"])}
    corp = s.get("ipam/vrfs", name=B.VRF_CORP["name"])
    if not corp:
        raise SeedError("HVL-CORP VRF missing -- run 'ipam' first")
    corp = corp[0]

    devices: dict[str, dict] = {}
    for site in sites.values():
        for d in s.get("dcim/devices", site_id=site["id"]):
            devices[d["name"]] = d
    by_key = {spec["name"]: spec for spec in B.DEVICES}

    # running counter per management subnet
    used: dict[str, int] = {}

    def next_host(pfx: str) -> str:
        net = _ip.ip_network(pfx)
        idx = used.get(pfx, 0) + 1
        used[pfx] = idx
        return f"{net.network_address + idx}/{net.prefixlen}"

    def assign(dev: dict, iface_name: str, address: str, *,
               role: str | None = None, dns: str | None = None) -> dict | None:
        ifaces = s.get("dcim/interfaces", device_id=dev["id"], name=iface_name)
        if not ifaces:
            return None
        payload = {
            "address": address, "status": "active", "vrf": _ref(corp),
            "tenant": _ref(tenant),
            "assigned_object_type": "dcim.interface",
            "assigned_object_id": ifaces[0]["id"],
        }
        if role:
            payload["role"] = role          # FIXED choice list
        if dns:
            payload["dns_name"] = dns
        return s.get_or_create(
            "ipam/ip-addresses",
            match={"address": address.split("/")[0], "vrf_id": corp["id"]},
            payload=s.tagged(payload),
        )

    primaries: list[tuple[dict, dict]] = []
    loopback_n = 0

    for name, dev in sorted(devices.items()):
        spec = by_key.get(name)
        if not spec:
            continue
        tkey, role = spec["type"], spec["role"]
        # patch panels and PDUs are passive: no IP, BY DESIGN (not a defect)
        if tkey in {"patch-panel-copper", "patch-panel-fiber", "pdu"}:
            continue

        mgmt_pfx = _mgmt_prefix_for(spec["site"])
        primary = None

        # L3 devices: Loopback0 /32 becomes the primary IP
        if role in _LOOPBACK_ROLES:
            loopback_n += 1
            lo = s.get_or_create(
                "dcim/interfaces",
                match={"device_id": dev["id"], "name": "Loopback0"},
                payload={"device": _ref(dev), "name": "Loopback0",
                         "type": "virtual", "enabled": True},
            )
            addr = f"{B.LOOPBACK_BASE}{loopback_n}/32"
            primary = s.get_or_create(
                "ipam/ip-addresses",
                match={"address": addr.split("/")[0], "vrf_id": corp["id"]},
                payload=s.tagged({
                    "address": addr, "status": "active", "role": "loopback",
                    "vrf": _ref(corp), "tenant": _ref(tenant),
                    "dns_name": f"{name}.hvl.example",
                    "assigned_object_type": "dcim.interface",
                    "assigned_object_id": lo["id"],
                }),
            )

        # everything else: a management address on its mgmt interface
        if primary is None and mgmt_pfx:
            iface = _MGMT_IFACE.get(tkey)
            if iface:
                primary = assign(dev, iface, next_host(mgmt_pfx),
                                 dns=f"{name}.hvl.example")

        if primary and name not in NO_PRIMARY_IP:
            primaries.append((dev, primary))

    # primary_ip4 must reference an IP already on one of the device's own
    # interfaces, so this is a SECOND pass after the addresses exist.
    for dev, ip in primaries:
        if dev.get("primary_ip4") and not s.dry_run:
            continue
        s.patch("dcim/devices", dev["id"], {"primary_ip4": _ref(ip)})

    # ---- planted IPAM defects --------------------------------------------
    # D2: IPs with NO parent prefix (typo'd subnets that exist nowhere).
    # BOTH addresses must fall OUTSIDE 10.60.0.0/16 -- verified 2026-09-16 that
    # 10.60.50.1 is contained by our own /16 container, which would void the
    # defect. 10.61/10.62 are clear of both the demo space and HVL space.
    for dev_name, addr in [("sea-dc1-oob-sw01", "10.61.0.10/24"),
                           ("spo-br03-rtr01", "10.62.0.1/24")]:
        dev = devices.get(dev_name)
        if dev:
            assign(dev, _MGMT_IFACE[by_key[dev_name]["type"]], addr)

    # D3: mask does not match the enclosing prefix (/24 inside a /26)
    dev = devices.get("sea-dc1-esx01")
    if dev:
        assign(dev, "eno2", "10.60.3.20/24")

    state["ip_primaries"] = len(primaries)


# --------------------------------------------------------------------------
# layer: ipfill  (reach the intended utilization spread)
# --------------------------------------------------------------------------
# Device management addresses alone leave every prefix near-empty (measured:
# 6 of 27 active prefixes held any IP, max ~6%). Utilization and
# next-available questions are degenerate until the prefixes actually FILL --
# so this layer adds non-device host addresses (printers, handsets, APs, DHCP
# reservations) up to each prefix's `fill_target` in PREFIX_PLAN.
_FILL_LABELS = {
    "access-data": "host", "access-voice": "voip", "access-wireless": "wlan",
    "management": "mgmt", "server": "srv", "guest": "guest",
}


def layer_ipfill(s: NetBoxSeeder, state: dict) -> None:
    import ipaddress as _ip

    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tenant = tenant[0]
    corp = s.get("ipam/vrfs", name=B.VRF_CORP["name"])
    if not corp:
        raise SeedError("HVL-CORP VRF missing -- run 'ipam' first")
    corp = corp[0]

    for pfx, status, role, site_slug, _vid, target, _note in B.PREFIX_PLAN:
        if status != "active" or not target:
            continue
        net = _ip.ip_network(pfx)
        have = s.count("ipam/ip-addresses", parent=pfx, vrf_id=corp["id"])
        if have >= target:
            # already filled -- tally it, or a re-run reports silence and a
            # genuine no-op becomes indistinguishable from a broken layer
            s._tally(s.reused, "ipam/prefixes (already filled)")
            continue

        # skip .0 (network) and the gateway .1, and never exceed the subnet
        capacity = net.num_addresses - 2 if net.prefixlen < 31 else net.num_addresses
        want = min(target, capacity)
        label = _FILL_LABELS.get(role or "", "host")
        made = 0
        for offset in range(2, capacity + 2):
            if have + made >= want:
                break
            addr = f"{net.network_address + offset}/{net.prefixlen}"
            if s.get("ipam/ip-addresses", address=addr.split("/")[0],
                     vrf_id=corp["id"]):
                continue
            s.create("ipam/ip-addresses", s.tagged({
                "address": addr, "status": "active",
                "vrf": _ref(corp), "tenant": _ref(tenant),
                "dns_name": f"{label}-{offset:03d}.{(site_slug or 'hvl')}.example",
                "description": f"{label} host",
            }))
            made += 1

    # /31 point-to-point links: BOTH addresses are usable (RFC 3021), so a
    # fully-provisioned link is GENUINELY 100% utilized -- a different 100%
    # from the mark_utilized case below, and a distinct utilization band.
    for p2p in B.P2P_LINKS:
        net = _ip.ip_network(p2p)
        addresses = list(net) if net.prefixlen >= 31 else list(net.hosts())
        for host in addresses:
            if s.get("ipam/ip-addresses", address=str(host), vrf_id=corp["id"]):
                s._tally(s.reused, "ipam/ip-addresses")
                continue
            s.create("ipam/ip-addresses", s.tagged({
                "address": f"{host}/{net.prefixlen}", "status": "active",
                "vrf": _ref(corp), "tenant": _ref(tenant),
                "description": f"P2P link {p2p}",
            }))

    # A DHCP pool marked as fully used -- gives one prefix a hard 100% that is
    # NOT produced by counting child IPs (tests a different utilization rule).
    pool = s.get("ipam/prefixes", prefix="10.60.19.0/24", vrf_id=corp["id"])
    if pool:
        if pool[0].get("mark_utilized"):
            s._tally(s.reused, "ipam/prefixes (already marked)")
        else:
            s.patch("ipam/prefixes", pool[0]["id"], {"mark_utilized": True})


# --------------------------------------------------------------------------
# layer: circuits
# --------------------------------------------------------------------------
def layer_circuits(s: NetBoxSeeder, state: dict) -> None:
    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tenant = tenant[0]
    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tenant["id"])}
    providers = {p["slug"]: p for p in s.get("circuits/providers")}
    ctypes = {t["slug"]: t for t in s.get("circuits/circuit-types")}

    # MPLS circuits terminate Z-side on the provider's network (as the demo
    # data does); internet circuits have an A side only -- a legitimate gap.
    # NB: provider-networks have NO `slug` field in 4.3 (verified via OPTIONS:
    # provider/name/service_id/description only). Matching on a non-existent
    # filter would silently return every object, so match on name + provider.
    pnet = s.get_or_create(
        "circuits/provider-networks",
        match={"name": "Evergreen MPLS Core",
               "provider_id": providers["evergreen-networks"]["id"]},
        payload=s.tagged({
            "provider": _ref(providers["evergreen-networks"]),
            "name": "Evergreen MPLS Core",
        }),
    )

    for cid, prov, ctype, site_slug, status, rate, _cable_to in B.CIRCUITS:
        payload = {
            "cid": cid,
            "provider": _ref(providers[prov]),
            "type": _ref(ctypes[ctype]),
            "status": status,
            "tenant": _ref(tenant),
        }
        if rate:
            payload["commit_rate"] = rate
        circuit = s.get_or_create(
            "circuits/circuits",
            match={"cid": cid},
            payload=s.tagged(payload),
        )
        # A side: always the site
        s.get_or_create(
            "circuits/circuit-terminations",
            match={"circuit_id": circuit["id"], "term_side": "A"},
            payload={
                "circuit": _ref(circuit), "term_side": "A",
                "termination_type": "dcim.site",
                "termination_id": sites[site_slug]["id"],
            },
        )
        # Z side: only MPLS, onto the provider network
        if ctype == "mpls":
            s.get_or_create(
                "circuits/circuit-terminations",
                match={"circuit_id": circuit["id"], "term_side": "Z"},
                payload={
                    "circuit": _ref(circuit), "term_side": "Z",
                    "termination_type": "circuits.providernetwork",
                    "termination_id": pnet["id"],
                },
            )


# --------------------------------------------------------------------------
# layer: power
# --------------------------------------------------------------------------
def layer_power(s: NetBoxSeeder, state: dict) -> None:
    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tenant = tenant[0]
    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tenant["id"])}
    racks = {x["name"]: x for x in s.get("dcim/racks", tenant_id=tenant["id"])}

    panels = {}
    for spec in B.POWER_PANELS:
        site = sites[spec["site"]]
        locs = s.get("dcim/locations", site_id=site["id"], name=spec["location"])
        payload = {"site": _ref(site), "name": spec["name"]}
        if locs:
            payload["location"] = _ref(locs[0])
        panels[spec["name"]] = s.get_or_create(
            "dcim/power-panels",
            match={"name": spec["name"], "site_id": site["id"]},
            payload=s.tagged(payload),
        )

    for name, panel, rack, ftype, status, voltage, amperage in B.POWER_FEEDS:
        s.get_or_create(
            "dcim/power-feeds",
            match={"name": name, "power_panel_id": panels[panel]["id"]},
            payload=s.tagged({
                "power_panel": _ref(panels[panel]),
                "rack": _ref(racks[rack]),
                "name": name, "status": status, "type": ftype,
                "supply": "ac", "phase": "single-phase",
                "voltage": voltage, "amperage": amperage,
                "max_utilization": 80,
            }),
        )
    state["power_panels"] = panels


# --------------------------------------------------------------------------
# layer: virt
# --------------------------------------------------------------------------
# VMs deliberately left without a primary IP.
VM_NO_PRIMARY = {"hvl-app08"}          # D16: has an IP, but not set as primary
VM_NO_IP = {"hvl-test01", "hvl-backup01"}


def layer_virt(s: NetBoxSeeder, state: dict) -> None:
    import ipaddress as _ip

    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tenant = tenant[0]
    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tenant["id"])}
    platforms = {x["slug"]: x for x in s.get("dcim/platforms")}
    corp = s.get("ipam/vrfs", name=B.VRF_CORP["name"])
    if not corp:
        raise SeedError("HVL-CORP VRF missing -- run 'ipam' first")
    corp = corp[0]
    devices = {}
    for site in sites.values():
        for d in s.get("dcim/devices", site_id=site["id"]):
            devices[d["name"]] = d

    groups = {}
    for spec in B.CLUSTER_GROUPS:
        groups[spec["slug"]] = s.get_or_create(
            "virtualization/cluster-groups",
            match={"slug": spec["slug"]}, payload=dict(spec),
        )

    clusters = {}
    for spec in B.CLUSTERS:
        site = sites[spec["site"]]
        clusters[spec["name"]] = s.get_or_create(
            "virtualization/clusters",
            match={"name": spec["name"]},
            payload=s.tagged({
                "name": spec["name"],
                "type": {"id": C.CLUSTER_TYPES[spec["type"]]},
                "group": _ref(groups[spec["group"]]),
                "status": spec["status"],
                "tenant": _ref(tenant),
                "scope_type": "dcim.site", "scope_id": site["id"],
            }),
        )

    # NetBox REJECTS `VirtualMachine.device` unless that device is itself a
    # member of the same cluster:
    #   "The selected device (sea-dc1-esx01) is not assigned to this cluster"
    # So the hypervisor hosts must join their cluster BEFORE any VM pins to
    # them. (A dry run cannot catch this -- it creates nothing, so the
    # cross-object constraint is never evaluated.)
    host_cluster: dict[str, str] = {}
    for _n, cl, host, *_rest in B.VMS:
        if host:
            host_cluster[host] = cl
    for host_name, cl_name in sorted(host_cluster.items()):
        dev = devices.get(host_name)
        if not dev:
            continue
        current = (dev.get("cluster") or {}).get("id")
        if current == clusters[cl_name]["id"]:
            s._tally(s.reused, "dcim/devices (already in cluster)")
            continue
        s.patch("dcim/devices", dev["id"], {"cluster": _ref(clusters[cl_name])})

    # VM addresses come from the DC server subnet, high offsets so they cannot
    # collide with the filler hosts created by the ipfill layer.
    vm_net = _ip.ip_network("10.60.2.0/24")
    offset = 100

    for name, cl, host, vcpus, memory, disk, status, platform in B.VMS:
        payload = {
            "name": name, "status": status,
            "cluster": _ref(clusters[cl]),
            "tenant": _ref(tenant),
            "platform": _ref(platforms[platform]),
            "vcpus": vcpus, "memory": memory,
        }
        if host and host in devices:
            payload["device"] = _ref(devices[host])
        # `disk` is DERIVED from the aggregate of any VirtualDisks, and NetBox
        # rejects a mismatch outright (verified 2026-09-16):
        #   "The specified disk size (999999) must match the aggregate size of
        #    assigned virtual disks (204800)."
        # So db VMs must NOT send `disk` -- their VirtualDisks define it.
        is_db = name.startswith("hvl-db")
        if not is_db:
            payload["disk"] = disk
        vm = s.get_or_create(
            "virtualization/virtual-machines",
            match={"name": name}, payload=s.tagged(payload),
        )

        if is_db:
            for n_disk in (1, 2):
                s.get_or_create(
                    "virtualization/virtual-disks",
                    match={"virtual_machine_id": vm["id"], "name": f"disk{n_disk}"},
                    payload={"virtual_machine": _ref(vm), "name": f"disk{n_disk}",
                             "size": disk // 2},
                )

        if name in VM_NO_IP:
            continue

        iface = s.get_or_create(
            "virtualization/interfaces",
            match={"virtual_machine_id": vm["id"], "name": "eth0"},
            payload={"virtual_machine": _ref(vm), "name": "eth0", "enabled": True},
        )
        addr = f"{vm_net.network_address + offset}/{vm_net.prefixlen}"
        offset += 1
        ip = s.get_or_create(
            "ipam/ip-addresses",
            match={"address": addr.split("/")[0], "vrf_id": corp["id"]},
            payload=s.tagged({
                "address": addr, "status": "active", "vrf": _ref(corp),
                "tenant": _ref(tenant), "dns_name": f"{name}.hvl.example",
                "assigned_object_type": "virtualization.vminterface",
                "assigned_object_id": iface["id"],
            }),
        )
        if name not in VM_NO_PRIMARY and not vm.get("primary_ip4"):
            s.patch("virtualization/virtual-machines", vm["id"],
                    {"primary_ip4": _ref(ip)})


# --------------------------------------------------------------------------
# layer: cabling
# --------------------------------------------------------------------------
def _term(object_type: str, obj_id: int) -> list[dict]:
    return [{"object_type": object_type, "object_id": obj_id}]


def layer_cabling(s: NetBoxSeeder, state: dict) -> None:
    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tenant = tenant[0]
    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tenant["id"])}

    devices: dict[str, dict] = {}
    for site in sites.values():
        for d in s.get("dcim/devices", site_id=site["id"]):
            devices[d["name"]] = d

    def iface(dev_name: str, name: str) -> dict | None:
        dev = devices.get(dev_name)
        if not dev:
            return None
        found = s.get("dcim/interfaces", device_id=dev["id"], name=name)
        return found[0] if found else None

    def port(ep: str, dev_name: str, name: str) -> dict | None:
        dev = devices.get(dev_name)
        if not dev:
            return None
        found = s.get(ep, device_id=dev["id"], name=name)
        return found[0] if found else None

    made = 0

    skipped: list[str] = []

    def cable(a_type: str, a_obj, b_type: str, b_obj, *,
              ctype: str, status: str = "connected", label: str = "") -> None:
        nonlocal made
        if not a_obj or not b_obj:
            # A silent skip here is how D10 was created as "0 PSUs connected"
            # instead of 1, and why a missing path went unnoticed. Record it.
            skipped.append(f"{label or '(unlabelled)'}: "
                           f"a={'ok' if a_obj else 'MISSING'} "
                           f"b={'ok' if b_obj else 'MISSING'}")
            return
        # a cabled termination already has `cable` set -- cheapest idempotency
        if a_obj.get("cable") or b_obj.get("cable"):
            s._tally(s.reused, "dcim/cables")
            return
        s.create("dcim/cables", s.tagged({
            "a_terminations": _term(a_type, a_obj["id"]),
            "b_terminations": _term(b_type, b_obj["id"]),
            "type": ctype, "status": status, "tenant": _ref(tenant),
            "label": label,
        }))
        made += 1

    IF = "dcim.interface"
    FP, RP = "dcim.frontport", "dcim.rearport"
    CP, CSP = "dcim.consoleport", "dcim.consoleserverport"
    PP, PO = "dcim.powerport", "dcim.poweroutlet"

    # -- DC: hosts -> leaf pair (25G), iDRAC -> management switch ------------
    for i in range(1, 6):
        host = f"sea-dc1-esx{i:02d}"
        cable(IF, iface(host, "eno1"), IF, iface("sea-dc1-leaf01", f"xe-0/0/{i}"),
              ctype=C.CABLE_TYPE_FIBER, label=f"{host}:eno1")
        cable(IF, iface(host, "eno2"), IF, iface("sea-dc1-leaf02", f"xe-0/0/{i}"),
              ctype=C.CABLE_TYPE_FIBER, label=f"{host}:eno2")
        cable(IF, iface(host, "idrac"), IF,
              iface("sea-dc1-oob-sw01", f"GigabitEthernet1/0/{i}"),
              ctype=C.CABLE_TYPE_COPPER, label=f"{host}:idrac")
    for i in range(6, 9):
        host = f"sea-dc1-esx{i:02d}"
        cable(IF, iface(host, "eno1"), IF, iface("sea-dc1-leaf03", f"xe-0/0/{i}"),
              ctype=C.CABLE_TYPE_FIBER, label=f"{host}:eno1")

    # -- DC: leaf uplinks THROUGH a panel pair (multi-hop trace) ------------
    # A rear-to-rear trunk carries POSITIONS. The HQ pair works because both
    # ends are 48-Pair Fiber Panels with a single 48-position "Rear Splice":
    # front Port N maps to position N at both ends, so every port crosses.
    #
    # sea-dc1-pp02/pp03 are 48-PORT COPPER panels: 48 discrete rear ports of
    # ONE position each. A copper rear -> fibre splice trunk therefore carries
    # a single position, so leaf01 stalled at the far splice and leaf02 had no
    # rear cable at all. Copper panels are used for per-port patching, not as
    # a trunked pair -- so the DC uplinks are cabled DIRECTLY leaf -> core and
    # the multi-hop panel path is modelled at HQ, where the panel types allow
    # it. (Verified against the demo data's own NCSU path, which is
    # splice -> circuit -> splice between two fibre panels.)
    for leaf, core in [("sea-dc1-leaf01", "sea-dc1-core01"),
                       ("sea-dc1-leaf02", "sea-dc1-core02")]:
        cable(IF, iface(leaf, "et-0/0/48"), IF, iface(core, "et-0/0/0"),
              ctype=C.CABLE_TYPE_FIBER, label=f"{leaf} uplink to {core}")
    # Copper panel used the way copper panels ARE used: per-port patching.
    # NB: do NOT patch to the hosts' eno2 -- that NIC is already cabled to
    # leaf02 above, so the cable would be silently skipped and pp02 would end
    # up with no cabling at all. Patch to spare leaf access ports instead.
    # The REAR ports stay uncabled on purpose: that is the documented
    # legitimate gap "user patch paths end at a rear port" (wall outlets are
    # not modelled), and it should NOT be reported as a fault.
    for n_ in (1, 2):
        cable(FP, port("dcim/front-ports", "sea-dc1-pp02", f"Port {n_}"),
              IF, iface("sea-dc1-leaf01", f"xe-0/0/{9 + n_}"),
              ctype=C.CABLE_TYPE_COPPER, label=f"pp02 Port {n_} patch")

    # -- DC: core <-> core, core -> firewall -> router ----------------------
    cable(IF, iface("sea-dc1-core01", "et-0/0/35"), IF,
          iface("sea-dc1-core02", "et-0/0/35"), ctype=C.CABLE_TYPE_FIBER,
          label="core peer-link")
    for core, fw in [("sea-dc1-core01", "sea-dc1-fw01"),
                     ("sea-dc1-core02", "sea-dc1-fw02")]:
        cable(IF, iface(core, "et-0/0/1"), IF, iface(fw, "ethernet1/1"),
              ctype=C.CABLE_TYPE_FIBER, label=f"{core}-{fw}")
    for fw, rtr in [("sea-dc1-fw01", "sea-dc1-rtr01"),
                    ("sea-dc1-fw02", "sea-dc1-rtr02")]:
        cable(IF, iface(fw, "ethernet1/2"), IF, iface(rtr, "GigabitEthernet0/1/0"),
              ctype=C.CABLE_TYPE_COPPER, label=f"{fw}-{rtr}")

    # -- console: DC devices -> console server ------------------------------
    # sea-dc1-leaf03's console is deliberately left UNCABLED (defect D9).
    for n_, dev in enumerate(["sea-dc1-core01", "sea-dc1-core02", "sea-dc1-leaf01",
                              "sea-dc1-leaf02", "sea-dc1-fw01"], start=1):
        cable(CP, port("dcim/console-ports", dev, "Console") or
              port("dcim/console-ports", dev, "con 0"),
              CSP, port("dcim/console-server-ports", "sea-dc1-con01", f"port{n_:02d}"),
              ctype=C.CABLE_TYPE_COPPER, label=f"console {dev}")

    # -- power: PDU outlet -> device PSU (dual-fed A/B) ---------------------
    # sea-dc1-esx05 gets ONE supply only (defect D10).
    # Each PDU has only 8 outlets, so the A/B pairs must be spread across the
    # PDUs IN THE DEVICE'S OWN RACK. Sending everything to pdu01/pdu02 (rack
    # R01) exhausted them at 8/8 and silently dropped esx05 entirely -- which
    # turned defect D10 ("one supply connected") into "no supplies connected".
    dc_power = [
        # (device, PSUs, A-side PDU, B-side PDU)
        ("sea-dc1-core01", ["PSU0", "PSU1"], "sea-dc1-pdu01", "sea-dc1-pdu02"),
        ("sea-dc1-core02", ["PSU0", "PSU1"], "sea-dc1-pdu01", "sea-dc1-pdu02"),
        ("sea-dc1-fw01", ["PSU0", "PSU1"], "sea-dc1-pdu01", "sea-dc1-pdu02"),
        ("sea-dc1-fw02", ["PSU0", "PSU1"], "sea-dc1-pdu01", "sea-dc1-pdu02"),
        ("sea-dc1-leaf01", ["PSU0", "PSU1"], "sea-dc1-pdu03", "sea-dc1-pdu04"),
        ("sea-dc1-leaf02", ["PSU0", "PSU1"], "sea-dc1-pdu03", "sea-dc1-pdu04"),
        ("sea-dc1-esx01", ["PSU0", "PSU1"], "sea-dc1-pdu03", "sea-dc1-pdu04"),
        ("sea-dc1-esx02", ["PSU0", "PSU1"], "sea-dc1-pdu03", "sea-dc1-pdu04"),
        # D10: exactly ONE connected supply, on the PDU in its own rack
        ("sea-dc1-esx05", ["PSU0"], "sea-dc1-pdu03", "sea-dc1-pdu04"),
    ]
    outlet_n: dict[str, int] = {}
    for dev, psus, pdu_a, pdu_b in dc_power:
        for idx, psu in enumerate(psus):
            pdu = pdu_a if idx == 0 else pdu_b
            slot = outlet_n.get(pdu, 0) + 1
            if slot > 8:
                skipped.append(f"{dev} {psu}: {pdu} has no free outlet")
                continue
            outlet_n[pdu] = slot
            cable(PP, port("dcim/power-ports", dev, psu),
                  PO, port("dcim/power-outlets", pdu, f"Outlet {slot}"),
                  ctype=C.CABLE_TYPE_POWER, label=f"{dev} {psu}")

    # -- HQ: access -> distribution, one PLANNED cable (defect D7) ----------
    cable(IF, iface("hq-acc01", "GigabitEthernet1/0/48"), IF,
          iface("hq-dist01", "xe-0/0/0"), ctype=C.CABLE_TYPE_COPPER,
          label="hq-acc01 uplink")
    cable(IF, iface("hq-acc01", "GigabitEthernet1/0/47"), IF,
          iface("hq-dist02", "xe-0/0/0"), ctype=C.CABLE_TYPE_COPPER,
          status="planned", label="hq-acc01 second uplink (planned)")
    cable(IF, iface("hq-dist01", "et-0/0/48"), IF, iface("hq-rtr01", "GigabitEthernet0/1/0"),
          ctype=C.CABLE_TYPE_COPPER, label="hq-dist01 to router")

    # -- HQ: IDF uplink through panels, deliberately BROKEN for hq-acc04 ----
    # hq-acc03 completes: acc03 -> pp03 front1 -> rear -> pp01 front3 -> dist01
    cable(IF, iface("hq-acc03", "GigabitEthernet1/0/48"), FP,
          port("dcim/front-ports", "hq-pp03", "Port 1"),
          ctype=C.CABLE_TYPE_FIBER, label="hq-acc03 uplink")
    cable(RP, port("dcim/rear-ports", "hq-pp03", "Rear Splice"), RP,
          port("dcim/rear-ports", "hq-pp01", "Rear Splice"),
          ctype=C.CABLE_TYPE_FIBER, label="HQ IDF trunk")
    # The onward cable MUST sit on the front port the traffic actually arrives
    # on. hq-acc03 enters hq-pp03 "Port 1" (position 1), and the splice-to-
    # splice trunk preserves position, so it emerges on hq-pp01 "Port 1" --
    # NOT "Port 3". Cabling the wrong port leaves the path dead-ending and
    # makes the good path indistinguishable from the D6 broken one.
    cable(FP, port("dcim/front-ports", "hq-pp01", "Port 1"), IF,
          iface("hq-dist01", "xe-0/0/1"), ctype=C.CABLE_TYPE_FIBER,
          label="hq-pp01 Port 1 to dist01")
    # hq-acc04 uplink enters pp03 but pp01 Port 4 is NEVER cabled onward:
    # the trace dead-ends at a front port (defect D6).
    cable(IF, iface("hq-acc04", "GigabitEthernet1/0/48"), FP,
          port("dcim/front-ports", "hq-pp03", "Port 4"),
          ctype=C.CABLE_TYPE_FIBER, label="hq-acc04 uplink (path breaks at pp01)")

    # -- branch / HQ patch panels: user patching -----------------------------
    # Six of nine panels were left entirely uncabled, which reads as unfinished
    # seeding rather than deliberate modelling, and left every branch with a
    # panel that connects nothing. Patch a handful of access ports per site.
    # REAR ports stay uncabled ON PURPOSE: that is the documented legitimate
    # gap ("user patch paths end at a rear port" -- wall outlets are not
    # modelled) and must NOT be reported as a fault.
    for sw, panel in [("tac-br01-sw01", "tac-br01-pp01"),
                      ("por-br02-sw01", "por-br02-pp01"),
                      ("spo-br03-sw01", "spo-br03-pp01"),
                      ("hq-acc01", "hq-pp02")]:
        for n_ in range(1, 5):
            cable(IF, iface(sw, f"GigabitEthernet1/0/{n_}"),
                  FP, port("dcim/front-ports", panel, f"Port {n_}"),
                  ctype=C.CABLE_TYPE_COPPER, label=f"{sw} port {n_} patch")

    # sea-dc1-pp03 and sea-dc1-pp01 are deliberately left as installed SPARES
    # (DC1-R03 / DC1-R01) -- one unused panel per site is realistic; six was not.

    # -- branches: router <-> switch, AP -> switch, WAN -> circuit ----------
    for pfx in ["tac-br01", "por-br02", "spo-br03"]:
        cable(IF, iface(f"{pfx}-rtr01", "GigabitEthernet0/1/0"), IF,
              iface(f"{pfx}-sw01", "GigabitEthernet1/0/48"),
              ctype=C.CABLE_TYPE_COPPER, label=f"{pfx} rtr-sw")
    cable(IF, iface("tac-br01-ap01", "eth0"), IF,
          iface("tac-br01-sw01", "GigabitEthernet1/0/24"),
          ctype=C.CABLE_TYPE_COPPER, label="tac-br01-ap01")
    cable(IF, iface("por-br02-ap01", "eth0"), IF,
          iface("por-br02-sw01", "GigabitEthernet1/0/24"),
          ctype=C.CABLE_TYPE_COPPER, label="por-br02-ap01")

    # -- WAN: router interface -> circuit termination (A side) --------------
    for cid, _prov, _ct, _site, _status, _rate, cable_to in B.CIRCUITS:
        if not cable_to:
            continue
        circuit = s.get("circuits/circuits", cid=cid)
        if not circuit:
            continue
        terms = s.get("circuits/circuit-terminations",
                      circuit_id=circuit[0]["id"], term_side="A")
        if not terms:
            continue
        cable(IF, iface(cable_to, "GigabitEthernet0/0/0"),
              "circuits.circuittermination", terms[0],
              ctype=C.CABLE_TYPE_FIBER, label=f"WAN {cid}")

    state["cables_created"] = made
    # Surface the misses. Instrumentation that stays silent is how the esx05
    # power gap and the pp02 patch conflict both went unnoticed.
    if skipped:
        print(f"    WARNING: {len(skipped)} cable(s) skipped:")
        for line in skipped:
            print(f"      - {line}")
    state["cables_skipped"] = skipped


# --------------------------------------------------------------------------
# layer: defects  (emit the audit answer key, COMPUTED from live data)
# --------------------------------------------------------------------------
# The blueprint's `expect` numbers are TARGETS, not answers. D1 already proved
# they diverge: 3 active devices without a primary IP, but 4 across all
# statuses. So every figure here is read back from the API, and the SCOPE is
# recorded alongside it -- reference-answer ambiguity is what bit v4.
def layer_defects(s: NetBoxSeeder, state: dict) -> None:
    import json
    from pathlib import Path

    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tid = tenant[0]["id"]
    sites = s.get("dcim/sites", tenant_id=tid)
    site_ids = [x["id"] for x in sites]

    devices: dict[str, dict] = {}
    for sid in site_ids:
        for d in s.get("dcim/devices", site_id=sid):
            devices[d["name"]] = d

    passive = {"48-Port Patch Panel", "48-Pair Fiber Panel", "AP7901"}
    active = [d for d in devices.values() if d["status"]["value"] == "active"]

    def no_primary(pool):
        return sorted(d["name"] for d in pool
                      if not d.get("primary_ip4")
                      and (d.get("device_type") or {}).get("model") not in passive)

    findings: dict[str, dict] = {}

    # D1 -- scope-dependent, so BOTH scopes are recorded
    findings["D1"] = {
        "description": "Device with no primary IP (excluding passive panels/PDUs)",
        "scoped_to_active": no_primary(active),
        "all_statuses": no_primary(devices.values()),
        "note": "scope MUST be stated in the question; the two answers differ",
    }

    # D2 -- IPs whose address has no containing prefix anywhere
    orphans = []
    for addr in ["10.61.0.10", "10.62.0.1"]:
        ip = s.get("ipam/ip-addresses", address=addr)
        if ip and s.count("ipam/prefixes", contains=addr) == 0:
            ao = ip[0].get("assigned_object") or {}
            orphans.append({"address": ip[0]["address"],
                            "device": (ao.get("device") or {}).get("name"),
                            "interface": ao.get("name")})
    findings["D2"] = {"description": "IP address with no parent prefix",
                      "found": orphans, "count": len(orphans)}

    # D6/D7/D9/D10 -- created by the cabling layer, verified here
    planned = s.get("dcim/cables", status="planned")
    findings["D7"] = {"description": "Planned cable between active devices",
                      "count": len(planned),
                      "labels": [x.get("label") for x in planned]}

    consoles = []
    for name in ["sea-dc1-core01", "sea-dc1-core02", "sea-dc1-leaf01",
                 "sea-dc1-leaf02", "sea-dc1-leaf03", "sea-dc1-fw01"]:
        d = devices.get(name)
        if not d:
            continue
        cps = s.get("dcim/console-ports", device_id=d["id"])
        if cps and not any(p.get("cable") for p in cps):
            consoles.append(name)
    findings["D9"] = {"description": "Console port not connected",
                      "found": sorted(consoles), "count": len(consoles)}

    single_psu = []
    for d in devices.values():
        pps = s.get("dcim/power-ports", device_id=d["id"])
        if len(pps) >= 2:
            connected = sum(1 for p in pps if p.get("cable"))
            if connected == 1:
                single_psu.append({"device": d["name"], "psus": len(pps),
                                   "connected": connected})
    findings["D10"] = {"description": "Only one power supply connected",
                       "found": single_psu, "count": len(single_psu)}

    # D5 -- intentional duplicates, only possible in the non-unique VRF
    guest = s.get("ipam/vrfs", name=B.VRF_GUEST["name"])
    dup = s.get("ipam/prefixes", prefix=C.GUEST_DUP_PREFIX,
                vrf_id=guest[0]["id"]) if guest else []
    findings["D5"] = {"description": "Duplicate prefixes (intentional, GUEST VRF)",
                      "prefix": C.GUEST_DUP_PREFIX, "count": len(dup),
                      "scopes": [(p.get("scope") or {}).get("name") for p in dup]}

    # D12 -- non-active lifecycle still in service
    findings["D12"] = {
        "description": "Non-active lifecycle states",
        "devices": sorted((d["name"], d["status"]["value"]) for d in devices.values()
                          if d["status"]["value"] != "active"),
    }

    # D14 -- HVL-region device with no tenant
    findings["D14"] = {"description": "Device at an HVL site with no tenant",
                       "found": sorted(d["name"] for d in devices.values()
                                       if not d.get("tenant"))}

    # D16 -- empty cluster / host with no VMs / VM with an IP but no primary
    clusters = s.get("virtualization/clusters", tenant_id=tid)
    empty = [c["name"] for c in clusters
             if s.count("virtualization/virtual-machines", cluster_id=c["id"]) == 0]
    hosts_no_vms = [d["name"] for d in devices.values()
                    if (d.get("role") or {}).get("slug") == "hypervisor-host"
                    and s.count("virtualization/virtual-machines",
                                device_id=d["id"]) == 0]
    vms_no_primary = [v["name"] for v in
                      s.get("virtualization/virtual-machines", tenant_id=tid)
                      if not v.get("primary_ip4")]
    findings["D16"] = {"description": "Empty cluster / host with no VMs / VM without primary IP",
                       "empty_clusters": sorted(empty),
                       "hosts_without_vms": sorted(hosts_no_vms),
                       "vms_without_primary_ip": sorted(vms_no_primary)}

    # D17 -- decommissioned circuit still terminated
    stale = []
    for ci in s.get("circuits/circuits", tenant_id=tid):
        if ci["status"]["value"] == "decommissioned":
            t = s.count("circuits/circuit-terminations", circuit_id=ci["id"])
            if t:
                stale.append({"cid": ci["cid"], "terminations": t})
    findings["D17"] = {"description": "Decommissioned circuit still terminated",
                       "found": stale, "count": len(stale)}

    payload = {
        "generated": "netbox-benchmark-v5 seed",
        "tenant": C.TENANT["slug"],
        "note": ("Values are COMPUTED from the live instance, not the blueprint's "
                 "targets. Recompute after any restore."),
        "legitimate_gaps_do_not_flag": B.LEGITIMATE_GAPS,
        "defects": findings,
    }
    out = Path("/home/ola/dev/netboxdev/netbox-snapshots/defects.json")
    if not s.dry_run:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, sort_keys=True))
    print(f"    answer key -> {out}")
    for k in sorted(findings):
        v = findings[k]
        summary = v.get("count")
        if summary is None:
            summary = sum(len(x) for x in v.values() if isinstance(x, list))
        print(f"      {k}: {v['description'][:58]:58} n={summary}")
    state["defects"] = findings


# --------------------------------------------------------------------------
# layer: journal  (change-history activity phase)
# --------------------------------------------------------------------------
# MEASURED CONSTRAINT: after seeding, the change log was ~87% component noise
# (2,014 of 2,319 rows were template-generated interfaces/ports), and EVERY row
# was a `create`. So "how many changes happened?" is answered by template noise.
#
# This layer therefore emits UPDATE and DELETE actions -- the only actions that
# are distinguishable from the bulk-create floor -- and touches a small, named
# set of objects so questions can be scoped by object type and by object.
#
# Timestamps CANNOT be backdated through the API (ObjectChange.time is
# auto_now_add), so every entry lands at seed time. Change questions must use
# absolute windows or ordering, never "in the last N days".
def layer_journal(s: NetBoxSeeder, state: dict) -> None:
    tenant = s.get("tenancy/tenants", slug=C.TENANT["slug"])
    if not tenant:
        raise SeedError("tenant missing -- run 'org' first")
    tid = tenant[0]["id"]
    sites = {x["slug"]: x for x in s.get("dcim/sites", tenant_id=tid)}
    devices: dict[str, dict] = {}
    for site in sites.values():
        for d in s.get("dcim/devices", site_id=site["id"]):
            devices[d["name"]] = d

    # ---- 1. UPDATES: status/description changes with a clear "before" -----
    updates = [
        ("hq-acc02", {"description": "Scheduled for removal in Q1; do not patch"}),
        ("spo-br03-ap02", {"description": "RMA raised with vendor"}),
        ("sea-dc1-leaf04", {"description": "Awaiting management address"}),
        ("boi-br04-rtr01", {"description": "Staged for BR04 go-live"}),
        ("sea-dc1-esx09", {"description": "Received, not yet racked"}),
    ]
    for name, payload in updates:
        d = devices.get(name)
        if d and d.get("description") != payload["description"]:
            s.patch("dcim/devices", d["id"], payload)
        elif d:
            s._tally(s.reused, "dcim/devices (description set)")

    # A commit-rate change gives a "what was the previous value?" question a
    # real pre-change snapshot in the change log.
    circuit = s.get("circuits/circuits", cid="EV-MPLS-2004")
    if circuit and circuit[0].get("commit_rate") != 100000:
        s.patch("circuits/circuits", circuit[0]["id"], {"commit_rate": 100000})
    elif circuit:
        s._tally(s.reused, "circuits/circuits (rate already raised)")

    # A VM resize -- vcpus 4 -> 8, again with a recorded previous value.
    vm = s.get("virtualization/virtual-machines", name="hvl-app01")
    if vm and (vm[0].get("vcpus") or 0) != 8:
        s.patch("virtualization/virtual-machines", vm[0]["id"], {"vcpus": 8})
    elif vm:
        s._tally(s.reused, "virtualization/virtual-machines (already resized)")

    # BR04 prefixes move reserved -> active as the site is commissioned.
    corp = s.get("ipam/vrfs", name=B.VRF_CORP["name"])
    if corp:
        p = s.get("ipam/prefixes", prefix="10.60.44.0/24", vrf_id=corp[0]["id"])
        if p and p[0]["status"]["value"] != "active":
            s.patch("ipam/prefixes", p[0]["id"], {"status": "active"})
        elif p:
            s._tally(s.reused, "ipam/prefixes (already activated)")

    # ---- 2. JOURNAL ENTRIES: human-readable operational notes -------------
    notes = [
        ("hq-acc02", "warning", "Switch scheduled for decommissioning; uplink "
                                "remains patched until the replacement lands."),
        ("sea-dc1-esx05", "info", "Second PSU feed pending electrician visit."),
        ("sea-dc1-leaf03", "warning", "Console cable missing after rack tidy."),
        ("boi-br04-rtr01", "info", "BR04 build in progress; MPLS circuit is "
                                   "still provisioning."),
    ]
    for name, kind, comment in notes:
        d = devices.get(name)
        if not d:
            continue
        existing = s.get("extras/journal-entries",
                         assigned_object_type="dcim.device",
                         assigned_object_id=d["id"])
        if existing:
            s._tally(s.reused, "extras/journal-entries")
            continue
        s.create("extras/journal-entries", {
            "assigned_object_type": "dcim.device",
            "assigned_object_id": d["id"],
            "kind": kind, "comments": comment,
        })

    # ---- 3. DELETE: an AP is replaced, leaving a delete in the log --------
    # This is the ONLY destructive step in the whole seeder. It is deliberate:
    # `delete` is one of the two actions distinguishable from the bulk-create
    # floor. Deleting the device CASCADES to its interface, its IP assignment
    # and its cable -- which is realistic for a replaced access point, but it
    # is irreversible short of restoring the snapshot.
    doomed = s.get("dcim/devices", name="por-br02-ap01")
    if doomed:
        s.delete("dcim/devices", doomed[0]["id"])
        s._tally(s.deleted, "dcim/devices (por-br02-ap01, replaced AP)")
    else:
        s._tally(s.reused, "dcim/devices (AP already removed)")


LAYERS = {
    "lookups": layer_lookups,
    "org": layer_org,
    "devicetypes": layer_devicetypes,
    "devices": layer_devices,
    "ipam": layer_ipam,
    "ipaddrs": layer_ipaddrs,
    "ipfill": layer_ipfill,
    "circuits": layer_circuits,
    "power": layer_power,
    "virt": layer_virt,
    "cabling": layer_cabling,
    "defects": layer_defects,
    "journal": layer_journal,
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
