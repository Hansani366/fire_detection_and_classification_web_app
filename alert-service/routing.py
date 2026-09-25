"""
Hazard-aware evacuation routing: block what the fire has taken, then Dijkstra.

The rules come from the methodology (Section 3.2.5.4) and each one is here for a
reason that showed up in testing:

  * WHOLE EDGES ARE BLOCKED, NOT NODES. "A corridor that passes close to the fire
    cannot be used safely." Testing only an edge's two endpoints leaves a long
    corridor whose *middle* runs straight past the flames -- it looks fine because
    both ends are far away. That is exactly the failure the hazard-intersection
    rate is built to catch, so the test is perpendicular distance to the segment.

  * AN EXIT BESIDE THE FIRE IS NOT AN EXIT. Blocked by node distance.

  * IF NO EXIT IS REACHABLE, SAY SO. A refuge instruction is a correct answer.
    Routing somebody through a fire because the alternative was admitting defeat
    is not.

  * THE CHOICE IS DETERMINISTIC. Ties break on exit priority, then on id. A route
    that varies run to run cannot be compared with a hand-derived ground truth,
    and the optimality gap stops meaning anything.

ROUTING MUST NEVER BE ABLE TO SUPPRESS THE ALARM. Nothing in here is on the path
that opens an incident or sends a push; `intake` calls it inside a try/except and
stores the failure. A missing route is a worse screen. A missing alarm is a fire
nobody was told about.
"""

import heapq
import math
import time
from dataclasses import dataclass, field

from sites import Site

MAX_REANCHOR_M = 25.0   # further than this, "walk out of the room first" is not advice


@dataclass(frozen=True)
class RouteResult:
    status: str                       # "exit" | "refuge"
    site_key: str
    plan_revision: str
    fire_zone_id: str
    origin_node: str
    origin_reanchored: bool
    hazard_xy_m: tuple[float, float]
    hazard_radius_m: float
    path_nodes: tuple[str, ...]
    polyline_px: tuple[tuple[float, float], ...]
    from_px: tuple[float, float]
    hazard_px: tuple[float, float]
    hazard_radius_px: float
    length_m: float
    blocked_edges: tuple[tuple[str, str], ...]
    blocked_exit_ids: tuple[str, ...]
    unreachable_exit_ids: tuple[str, ...]
    exit_id: str | None
    exit_name: str | None
    muster_px: tuple[float, float] | None
    refuge_node: str | None
    instruction: str
    generation_ms: float
    algorithm: str = "dijkstra-heapq"
    caveats: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_refuge(self) -> bool:
        return self.status == "refuge"

    def to_wire(self) -> dict:
        """The block the phone reads. Design-space pixels, camelCase keys.

        Geometry is deliberately absent: the app owns the rooms, doors and exit
        bars as const data and only needs the parts that change with the fire.
        """
        return {
            "status": self.status,
            "siteKey": self.site_key,
            "planRevision": self.plan_revision,
            "fireZoneId": self.fire_zone_id,
            "from": {"x": self.from_px[0], "y": self.from_px[1]},
            "hazard": {"x": self.hazard_px[0], "y": self.hazard_px[1],
                       "radiusPx": self.hazard_radius_px},
            "polyline": [{"x": x, "y": y} for x, y in self.polyline_px],
            "exitId": self.exit_id,
            "exitName": self.exit_name,
            "muster": (None if self.muster_px is None
                       else {"x": self.muster_px[0], "y": self.muster_px[1]}),
            "blockedExitIds": list(self.blocked_exit_ids),
            "lengthM": round(self.length_m, 1),
            "originReanchored": self.origin_reanchored,
            "instruction": self.instruction,
            "generatedInMs": round(self.generation_ms, 2),
        }

    def to_record(self) -> dict:
        """Everything, for the stored record and the analysis endpoint."""
        d = self.to_wire()
        d.update({
            "originNode": self.origin_node,
            "pathNodes": list(self.path_nodes),
            "blockedEdges": [list(e) for e in self.blocked_edges],
            "unreachableExitIds": list(self.unreachable_exit_ids),
            "refugeNode": self.refuge_node,
            "hazardXyM": list(self.hazard_xy_m),
            "hazardRadiusM": self.hazard_radius_m,
            "algorithm": self.algorithm,
            "caveats": list(self.caveats),
        })
        return d


def _seg_point_dist_m(ax, ay, bx, by, px, py) -> float:
    """Shortest distance from a point to a closed line segment, in metres."""
    vx, vy = bx - ax, by - ay
    l2 = vx * vx + vy * vy
    if l2 == 0.0:
        return math.hypot(ax - px, ay - py)
    t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / l2))
    return math.hypot(ax + t * vx - px, ay + t * vy - py)


def _prune(site: Site, hx: float, hy: float, radius: float):
    """Drop every edge that comes within `radius` of the fire. Returns (adj, blocked)."""
    adj: dict[str, list[tuple[str, float]]] = {nid: [] for nid in site.nodes}
    blocked: set[tuple[str, str]] = set()
    for a, neighbours in site.adj.items():
        na = site.nodes[a]
        for b, w in neighbours:
            nb = site.nodes[b]
            if _seg_point_dist_m(na.xm, na.ym, nb.xm, nb.ym, hx, hy) <= radius:
                blocked.add(tuple(sorted((a, b))))
                continue
            adj[a].append((b, w))
    return adj, tuple(sorted(blocked))


def _dijkstra(adj, start: str):
    dist = {start: 0.0}
    prev: dict[str, str] = {}
    pq = [(0.0, start)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, math.inf):
            continue          # stale entry; lazy deletion
        for v, w in adj.get(u, ()):
            nd = d + w
            if nd < dist.get(v, math.inf):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def _path(prev: dict, start: str, goal: str) -> tuple[str, ...]:
    out = [goal]
    while out[-1] != start:
        out.append(prev[out[-1]])
    return tuple(reversed(out))


def _node_dist(site: Site, node_id: str, hx: float, hy: float) -> float:
    n = site.nodes[node_id]
    return math.hypot(n.xm - hx, n.ym - hy)


def compute_route(site: Site, *, fire_zone_id: str, from_node: str,
                  hazard_xy_m: tuple[float, float],
                  hazard_radius_m: float | None = None,
                  blocked_exit_ids: tuple[str, ...] = ()) -> RouteResult:
    """`blocked_exit_ids` marks exits unusable for reasons the graph cannot see --
    a locked shutter, a scenario input. Section 3.3.7 blocks exits this way rather
    than physically, so the route tests can reach the cases that matter."""
    t0 = time.perf_counter()
    radius = site.hazard_radius_m if hazard_radius_m is None else hazard_radius_m
    hx, hy = hazard_xy_m
    caveats: list[str] = []

    adj, blocked_edges = _prune(site, hx, hy, radius)

    # AN OCCUPANT IN THE BURNING ROOM IS INSIDE THE HAZARD, and in a domestic-sized
    # room that is the normal case, not an edge case: if your 3 m kitchen is
    # alight you are standing within two metres of it. Every edge touching them is
    # blocked, so a plain search answers "shelter where you are" -- next to the
    # fire. Re-anchor to the doorway instead.
    #
    # The search is over the UNPRUNED graph and ordered by WALKING distance, not
    # by straight-line distance, so the answer is the first place they can
    # actually get to rather than the nearest point as the crow flies. Exits are
    # excluded: re-anchoring onto the exit itself produced a zero-length route
    # that told someone standing in a burning room they had already arrived.
    origin, reanchored = from_node, False
    leave_first = ""
    if _node_dist(site, from_node, hx, hy) <= radius:
        walk, _ = _dijkstra(site.adj, from_node)
        reach = min(
            (n for n, d in walk.items()
             if d <= MAX_REANCHOR_M
             and site.nodes[n].kind != "exit"
             and _node_dist(site, n, hx, hy) > radius),
            key=lambda n: (walk[n], n), default=None)
        if reach is not None:
            origin, reanchored = reach, True
            zone_name = next((z["name"] for z in site.zones if z["id"] == fire_zone_id),
                             fire_zone_id)
            leave_first = f"Leave the {zone_name} immediately, then "
            caveats.append(
                "The occupant's own position was inside the hazard radius, so the "
                "route starts from the first reachable point outside it.")

    dist, prev = _dijkstra(adj, origin)

    blocked_exits, unreachable, reachable = [], [], []
    for x in sorted(site.exits.values(), key=lambda e: (e.priority, e.id)):
        if x.id in blocked_exit_ids or _node_dist(site, x.node, hx, hy) <= radius:
            blocked_exits.append(x.id)
        elif x.node not in dist:
            unreachable.append(x.id)
        else:
            reachable.append(x)

    px_radius = round(radius * site.px_per_m, 1)
    hazard_px = site.to_px(hx, hy)

    def _poly(nodes):
        return tuple(site.node_px(n) for n in nodes)

    if reachable:
        best = min(reachable, key=lambda x: (dist[x.node], x.priority, x.id))
        nodes = _path(prev, origin, best.node)
        instruction = (f"{leave_first}leave through the {best.name.lower()}."
                       if leave_first else
                       f"Leave through the {best.name.lower()}.")
        if blocked_exits:
            names = ", ".join(site.exits[e].name.lower() for e in blocked_exits)
            instruction += f" Do not use the {names}."
        result = RouteResult(
            status="exit", site_key=site.key, plan_revision=site.revision,
            fire_zone_id=fire_zone_id, origin_node=origin,
            origin_reanchored=reanchored, hazard_xy_m=(hx, hy),
            hazard_radius_m=radius, path_nodes=nodes, polyline_px=_poly(nodes),
            from_px=site.node_px(origin), hazard_px=hazard_px,
            hazard_radius_px=px_radius, length_m=dist[best.node],
            blocked_edges=blocked_edges, blocked_exit_ids=tuple(blocked_exits),
            unreachable_exit_ids=tuple(unreachable), exit_id=best.id,
            exit_name=best.name, muster_px=site.node_px(best.node),
            refuge_node=None, instruction=instruction,
            generation_ms=(time.perf_counter() - t0) * 1000.0,
            caveats=tuple(caveats),
        )
    else:
        # Refuge: the reachable node furthest from the fire, preferring somewhere
        # authored as a refuge (a room with a door that closes and a window).
        options = [n for n in dist if n in site.nodes]
        best_node = max(
            options,
            key=lambda n: (site.nodes[n].refuge, _node_dist(site, n, hx, hy), n),
        ) if options else origin
        nodes = _path(prev, origin, best_node) if best_node != origin else (origin,)
        where = site.nodes[best_node].zone_id
        where_name = next((z["name"] for z in site.zones if z["id"] == where), None)
        instruction = (
            f"No safe exit from here. Stay in the {where_name}. Close the door, "
            "seal the gaps and signal from a window. Do not move towards the fire."
            if where_name else
            "No safe exit from here. Stay where you are, close the door, seal the "
            "gaps and signal from a window. Do not move towards the fire.")
        result = RouteResult(
            status="refuge", site_key=site.key, plan_revision=site.revision,
            fire_zone_id=fire_zone_id, origin_node=origin,
            origin_reanchored=reanchored, hazard_xy_m=(hx, hy),
            hazard_radius_m=radius, path_nodes=nodes, polyline_px=_poly(nodes),
            from_px=site.node_px(origin), hazard_px=hazard_px,
            hazard_radius_px=px_radius, length_m=dist.get(best_node, 0.0),
            blocked_edges=blocked_edges, blocked_exit_ids=tuple(blocked_exits),
            unreachable_exit_ids=tuple(unreachable), exit_id=None, exit_name=None,
            muster_px=None, refuge_node=best_node, instruction=instruction,
            generation_ms=(time.perf_counter() - t0) * 1000.0,
            caveats=tuple(caveats),
        )

    # The invariant the whole design rests on. Cheap to check, and a violation
    # means somebody is being walked past a fire.
    _assert_clear(site, result)
    return result


def _assert_clear(site: Site, r: RouteResult) -> None:
    hx, hy = r.hazard_xy_m
    for a, b in zip(r.path_nodes, r.path_nodes[1:]):
        na, nb = site.nodes[a], site.nodes[b]
        d = _seg_point_dist_m(na.xm, na.ym, nb.xm, nb.ym, hx, hy)
        if d <= r.hazard_radius_m + 1e-9:
            raise AssertionError(
                f"route {a}->{b} passes {d:.2f} m from the fire "
                f"(radius {r.hazard_radius_m} m)")


def route_for_zone(site: Site, *, fire_zone_id: str,
                   occupant_zone_id: str | None = None,
                   hazard_radius_m: float | None = None,
                   blocked_exit_ids: tuple[str, ...] = ()) -> RouteResult:
    """Route an occupant away from a fire in `fire_zone_id`.

    With no `occupant_zone_id` the occupant is assumed to be in the zone that is
    burning -- the worst case, and the one the alert is for.
    """
    if fire_zone_id not in site.zone_anchors:
        raise KeyError(f"{site.key}: no anchor for zone {fire_zone_id!r}")
    fire = site.zone_anchors[fire_zone_id]["firePoint"]
    occupant = site.zone_anchors.get(occupant_zone_id or fire_zone_id)
    if occupant is None:
        raise KeyError(f"{site.key}: no anchor for occupant zone {occupant_zone_id!r}")
    return compute_route(
        site, fire_zone_id=fire_zone_id, from_node=occupant["node"],
        hazard_xy_m=(float(fire["x"]), float(fire["y"])),
        hazard_radius_m=hazard_radius_m, blocked_exit_ids=blocked_exit_ids,
    )


def validate(site: Site, record: dict) -> tuple[bool, list[str]]:
    """Check a STORED route against the graph, for the route-validity analysis.

    Deliberately re-derives nothing: it reads the stored path, the stored hazard
    and the stored radius. Recomputing against today's graph would quietly
    re-answer the question about a building that has since been edited.
    """
    reasons: list[str] = []
    if record.get("planRevision") != site.revision:
        reasons.append(
            f"recorded against plan {record.get('planRevision')}, current is {site.revision}")
        return False, reasons

    path = record.get("pathNodes") or []
    if not path:
        reasons.append("no path recorded")
        return False, reasons
    for n in path:
        if n not in site.nodes:
            reasons.append(f"unknown node {n!r}")
            return False, reasons
    for a, b in zip(path, path[1:]):
        if not any(v == b for v, _ in site.adj[a]):
            reasons.append(f"{a}->{b} is not an edge")

    if record.get("status") == "exit":
        exit_id = record.get("exitId")
        if exit_id not in site.exits:
            reasons.append(f"unknown exit {exit_id!r}")
        elif path[-1] != site.exits[exit_id].node:
            reasons.append(f"path ends at {path[-1]!r}, not at exit {exit_id!r}")
    return (not reasons), reasons


def hazard_intersects(site: Site, record: dict) -> bool:
    """Does a stored route pass within the hazard radius it was generated under?"""
    hx, hy = record.get("hazardXyM", (None, None))
    if hx is None:
        return False
    radius = float(record.get("hazardRadiusM", 0.0))
    path = record.get("pathNodes") or []
    for a, b in zip(path, path[1:]):
        if a not in site.nodes or b not in site.nodes:
            continue
        na, nb = site.nodes[a], site.nodes[b]
        if _seg_point_dist_m(na.xm, na.ym, nb.xm, nb.ym, hx, hy) <= radius:
            return True
    return False
