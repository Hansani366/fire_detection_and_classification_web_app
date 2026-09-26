"""
The facility catalogue: rooms, doors, exits and the walkable graph between them.

WHY JSON FILES AND NOT THE DATABASE. `init_db` seeds with INSERT OR IGNORE into a
SQLite file that lives in the `alert-data` volume and survives `compose down`. Put
geometry there and editing a corridor silently does nothing on any machine that has
run the stack before -- which is every machine that matters, and the failure is
invisible until someone notices the route going through a wall. Geometry is
configuration, not state: it is rebuilt from the image on every start.

WHY NODES ARE IN METRES. The methodology weights edges by physical length and
blocks a hazard *radius*. In abstract drawing units "radius = 60" cannot be
checked against anything, and the optimality gap against a hand-measured route has
no denominator. So the graph is authored in metres and `render.pxPerM` converts to
the phone's drawing space once, here, at import.

THE MIRROR CONTRACT. The phone owns the artwork -- rooms, doors, exit bars and
labels are const data in `lib/shared/floor_plan/floor_plan_data.dart`. This file
owns only the graph. The two must agree on exactly two things: the **exit ids**,
and the **coordinate space** (`designW` x `designH` at `pxPerM`). Change either
here and you must change it there, or the route will be drawn through the walls of
a building it does not describe. Same rule as zones_seed.py <-> mock_data.dart.
"""

import json
import logging
import math
import os
from dataclasses import dataclass, field

log = logging.getLogger("alert.sites")

SITES_DIR = os.path.join(os.path.dirname(__file__), "sites")
SITE_KEY = os.getenv("SITE_KEY", "home")

# Lets a demo retune the radius without editing a file and rebuilding. Read at
# container start, so it needs `up -d --force-recreate`, not `restart`.
_RADIUS_OVERRIDE = os.getenv("HAZARD_RADIUS_M", "").strip()


class SiteError(ValueError):
    """A site file that cannot be trusted. Raised at import, on purpose."""


@dataclass(frozen=True)
class Node:
    id: str
    xm: float
    ym: float
    kind: str
    zone_id: str | None = None
    refuge: bool = False

    def px(self, px_per_m: float) -> tuple[float, float]:
        return (round(self.xm * px_per_m, 1), round(self.ym * px_per_m, 1))


@dataclass(frozen=True)
class Exit:
    id: str
    name: str
    node: str
    priority: int


@dataclass(frozen=True)
class Site:
    key: str
    name: str
    revision: str
    px_per_m: float
    design_w: int
    design_h: int
    hazard_radius_m: float
    default_zone_id: str
    zones: list[dict]
    nodes: dict[str, Node]
    adj: dict[str, tuple[tuple[str, float], ...]]
    exits: dict[str, Exit]
    zone_anchors: dict[str, dict]
    ground_truth: dict[str, dict] = field(default_factory=dict)

    def node_px(self, node_id: str) -> tuple[float, float]:
        return self.nodes[node_id].px(self.px_per_m)

    def to_px(self, xm: float, ym: float) -> tuple[float, float]:
        return (round(xm * self.px_per_m, 1), round(ym * self.px_per_m, 1))


def _dist(a: Node, b: Node) -> float:
    return math.hypot(a.xm - b.xm, a.ym - b.ym)


def _reachable(adj: dict[str, tuple], start: str) -> set[str]:
    seen, stack = {start}, [start]
    while stack:
        for nxt, _ in adj.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def load(key: str = SITE_KEY) -> Site:
    """Read, validate and index one site file.

    Validation raises rather than warns. A site whose graph is disconnected, or
    whose exit points at a node that does not exist, produces confident nonsense
    routes -- and it would do so for the first time during a fire. Far better for
    the container to refuse to start with the reason in its logs.
    """
    path = os.path.join(SITES_DIR, f"{key}.json")
    if not os.path.exists(path):
        raise SiteError(f"No site file for SITE_KEY={key!r} (looked in {SITES_DIR})")
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)

    nodes: dict[str, Node] = {}
    for n in raw["nodes"]:
        if n["id"] in nodes:
            raise SiteError(f"{key}: duplicate node id {n['id']!r}")
        nodes[n["id"]] = Node(
            id=n["id"], xm=float(n["x"]), ym=float(n["y"]),
            kind=n.get("kind", "junction"), zone_id=n.get("zoneId"),
            refuge=bool(n.get("refuge", False)),
        )

    adj: dict[str, list[tuple[str, float]]] = {nid: [] for nid in nodes}
    for e in raw["edges"]:
        a, b = e["a"], e["b"]
        for end in (a, b):
            if end not in nodes:
                raise SiteError(f"{key}: edge {a}->{b} names unknown node {end!r}")
        straight = _dist(nodes[a], nodes[b])
        w = float(e.get("wM", straight))
        if w < straight - 1e-6:
            # A stated weight shorter than the straight line is a typo, and a typo
            # here quietly shortens a route the system then calls optimal.
            raise SiteError(
                f"{key}: edge {a}->{b} declares wM={w} but its endpoints are "
                f"{straight:.2f} m apart")
        adj[a].append((b, w))
        adj[b].append((a, w))

    exits = {}
    for x in raw["exits"]:
        if x["node"] not in nodes:
            raise SiteError(f"{key}: exit {x['id']!r} points at unknown node {x['node']!r}")
        exits[x["id"]] = Exit(id=x["id"], name=x["name"], node=x["node"],
                              priority=int(x.get("priority", 99)))
    if not exits:
        raise SiteError(f"{key}: a facility with no exits cannot be evacuated")

    zone_ids = {z["id"] for z in raw["zones"]}
    anchors = raw.get("zoneAnchors", {})
    for zid in zone_ids:
        if zid not in anchors:
            raise SiteError(f"{key}: zone {zid!r} has no zoneAnchors entry")
        if anchors[zid]["node"] not in nodes:
            raise SiteError(f"{key}: anchor for {zid!r} names unknown node")
    for zid in anchors:
        if zid not in zone_ids:
            raise SiteError(f"{key}: zoneAnchors has {zid!r}, which is not a zone")
    for zid in raw.get("groundTruth", {}):
        if zid not in zone_ids:
            raise SiteError(f"{key}: groundTruth has {zid!r}, which is not a zone")

    frozen_adj = {k: tuple(v) for k, v in adj.items()}

    # Connectivity, before any hazard. If an exit is unreachable from a zone with
    # nothing burning, the map is wrong -- not the fire.
    for zid, anchor in anchors.items():
        seen = _reachable(frozen_adj, anchor["node"])
        for x in exits.values():
            if x.node not in seen:
                raise SiteError(
                    f"{key}: exit {x.id!r} is unreachable from zone {zid!r} even "
                    f"with no hazard. The graph is disconnected.")

    render = raw["render"]
    radius = float(_RADIUS_OVERRIDE) if _RADIUS_OVERRIDE else float(raw["hazardRadiusM"])

    site = Site(
        key=raw["key"], name=raw["name"], revision=raw["revision"],
        px_per_m=float(render["pxPerM"]),
        design_w=int(render["designW"]), design_h=int(render["designH"]),
        hazard_radius_m=radius,
        default_zone_id=raw["defaultZoneId"],
        zones=raw["zones"], nodes=nodes, adj=frozen_adj, exits=exits,
        zone_anchors=anchors, ground_truth=raw.get("groundTruth", {}),
    )
    log.info("Site %r (%s, rev %s): %d zones, %d nodes, %d edges, %d exits, hazard %.1f m",
             site.key, site.name, site.revision, len(site.zones), len(nodes),
             len(raw["edges"]), len(exits), radius)
    return site


ACTIVE: Site = load()
