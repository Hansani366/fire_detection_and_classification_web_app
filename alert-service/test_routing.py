"""
Route-validity tests: the Section 3.3.7 scenarios, with their answers written down.

These are the ground truth the analysis compares against, and recording them HERE
rather than reading them off the running system is the whole point. When the same
team builds and evaluates an artefact, the easy failure is to accept whatever it
produces as correct. A route nobody wrote down in advance cannot be wrong.

Run offline, no HTTP, no database:   python3 -m pytest test_routing.py -v
"""

import pytest

import routing
import sites

HOME = sites.load("home")
INDUSTRIAL = sites.load("industrial")


def _route(site, fire, occupant=None, blocked=()):
    return routing.route_for_zone(site, fire_zone_id=fire, occupant_zone_id=occupant,
                                  blocked_exit_ids=blocked)


# ── The invariant that matters more than any single scenario ────────────────

@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_no_route_ever_passes_through_the_hazard(site):
    """Hazard-intersection rate must be zero. Not low -- zero.

    Checked over every fire/occupant pair on both sites, because a single unsafe
    route is a serious failure regardless of the average.
    """
    for fire in site.zones:
        for occupant in site.zones:
            r = _route(site, fire["id"], occupant["id"])
            assert not routing.hazard_intersects(site, r.to_record()), (
                f"{site.key}: fire in {fire['id']}, occupant in {occupant['id']}")


@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_every_route_is_a_real_walk_through_the_graph(site):
    for fire in site.zones:
        r = _route(site, fire["id"])
        ok, why = routing.validate(site, r.to_record())
        assert ok, f"{site.key}/{fire['id']}: {why}"


@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_generation_is_far_inside_the_five_second_budget(site):
    """RO2.2 claims a route within 5 s of a confirmed detection."""
    worst = max(_route(site, f["id"], o["id"]).generation_ms
                for f in site.zones for o in site.zones)
    assert worst < 50.0, f"{site.key}: slowest route took {worst:.1f} ms"


def test_the_choice_is_deterministic():
    """Ties break on priority then id, so a rerun cannot pick a different exit."""
    first = [_route(HOME, z["id"]).exit_id for z in HOME.zones]
    for _ in range(5):
        assert [_route(HOME, z["id"]).exit_id for z in HOME.zones] == first


# ── Section 3.3.7, scenario by scenario ─────────────────────────────────────

def test_s1_fire_far_from_all_exits_takes_the_obvious_route():
    """Bedroom (NE) burns. It is far from both doors; the front door is nearer."""
    r = _route(HOME, "bedroom-northeast")
    assert r.status == "exit"
    assert r.exit_id == "exit-north"


def test_s2_fire_beside_the_nearest_exit_makes_the_obvious_route_wrong():
    """A dining fire sits beside the front door, the exit it is nearest to.

    The naive answer -- nearest exit by straight line -- is the front door, which
    is exactly the one nobody may use.
    """
    r = _route(HOME, "dining")
    assert "exit-north" in r.blocked_exit_ids, "the front door is 1.1 m from the fire"
    assert r.exit_id == "exit-south", "should not route towards the fire"


def test_s3_fire_on_the_shortest_path_forces_the_longer_route():
    """A verander fire puts itself across the living area's way to the back door.

    The back door is not blocked -- it is 4.4 m from the flames. The *path* to it
    is. So the route abandons a 6.7 m walk south and takes a 7.8 m walk north,
    which is the case Section 3.3.7 asks for.

    Note the occupant has to be somebody with two ways out. Every bedroom and the
    kitchen in this house has a single door onto a shared space, so for them the
    answer is always either that one door or a refuge -- never a longer detour.
    See THESIS_CHANGES.md.
    """
    short = _route(HOME, "bedroom-northeast", "living")   # nothing in the way
    detour = _route(HOME, "verander", "living")           # fire across the path
    assert short.exit_id == "exit-south"
    assert detour.exit_id == "exit-north", "should not walk through the verander"
    assert detour.length_m > short.length_m
    assert "exit-south" not in detour.blocked_exit_ids, (
        "the back door itself is clear; it is the way there that is cut")


def test_s4_blocking_one_of_two_exits_leaves_the_distant_one():
    r = _route(HOME, "bedroom-southeast", blocked=("exit-south",))
    assert r.status == "exit"
    assert r.exit_id == "exit-north"
    assert "exit-south" in r.blocked_exit_ids


def test_s5_all_exits_cut_off_returns_a_refuge_not_a_route():
    """The correct refusal. A refuge instruction beats a route through a fire."""
    r = _route(HOME, "living", blocked=("exit-north", "exit-south"))
    assert r.status == "refuge"
    assert r.exit_id is None
    assert r.refuge_node is not None
    assert "stay" in r.instruction.lower()


def test_s5b_a_room_whose_only_door_is_blocked_shelters_in_place():
    """The kitchen opens only into the dining area. A dining fire traps it.

    This one is not staged -- it falls out of the real layout, and it is the
    reason the refuge branch has to exist for a house rather than only for a
    factory with several ways out.
    """
    r = _route(HOME, "dining", "kitchen")
    assert r.status == "refuge", "the kitchen has no second door"


def test_s6_occupants_in_different_areas_get_different_routes():
    """One fire, two people, two answers."""
    fire = "living"
    sw = _route(HOME, fire, "bedroom-southwest")
    ne = _route(HOME, fire, "bedroom-northeast")
    assert sw.exit_id != ne.exit_id, "both were sent the same way"
    assert sw.exit_id == "exit-south"
    assert ne.exit_id == "exit-north"


# ── Industrial unit: the demo path ───────────────────────────────────────────────────

def test_industrial_fabric_store_fire_cuts_the_north_door():
    """The drawn plan labels the north door "by fire". This makes that true."""
    r = _route(INDUSTRIAL, "fabric-store")
    assert "exit-north" in r.blocked_exit_ids
    assert r.exit_id == "exit-east"


def test_industrial_route_changes_with_the_fire():
    """Move the fire, get a different door. The point of the whole exercise."""
    chosen = {z["id"]: _route(INDUSTRIAL, z["id"]).exit_id for z in INDUSTRIAL.zones}
    assert len(set(chosen.values())) > 1, chosen


# ── Guards on the map itself ────────────────────────────────────────────────

@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_declared_ground_truth_matches_what_the_router_does(site):
    for zone_id, gt in site.ground_truth.items():
        r = _route(site, zone_id)
        assert r.is_refuge == gt["refugeExpected"], zone_id
        if not gt["refugeExpected"]:
            assert r.exit_id == gt["exitId"], zone_id
            # The length is checked too, not just the exit. The optimality gap
            # divides by this number, so a declared length that no longer matches
            # would report a gap against a route nobody walked.
            assert abs(r.length_m - gt["lengthM"]) < 0.01, (zone_id, r.length_m)


@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_every_zone_has_a_written_down_answer(site):
    """Ground truth must cover the whole building, not the convenient part of it.

    The industrial profile once had answers for three of its seven zones, so a
    wrong route in any of the other four would have gone unnoticed while the
    route-validity rate still read 100 per cent.
    """
    missing = {z["id"] for z in site.zones} - set(site.ground_truth)
    assert not missing, missing
    for zone_id, gt in site.ground_truth.items():
        if not gt["refugeExpected"]:
            assert gt.get("lengthM") is not None, zone_id


@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_blocked_exit_scenarios_match_what_the_router_does(site):
    """Fire location combined with a blocked exit — Section 3.3.7's real test.

    The zone-keyed ground truth above can only express "fire here, nothing
    blocked". These are the combinations, and they are where a reroute is forced
    rather than merely available.
    """
    assert site.route_scenarios, f"{site.key} declares no blocked-exit scenarios"
    for sc in site.route_scenarios:
        r = _route(site, sc["fireZone"], blocked=tuple(sc["blockedExits"]))
        exp = sc["expect"]
        assert r.is_refuge == exp["refugeExpected"], sc["id"]
        if not exp["refugeExpected"]:
            assert r.exit_id == exp["exitId"], sc["id"]
            assert abs(r.length_m - exp["lengthM"]) < 0.01, (sc["id"], r.length_m)
            # A blocked exit must never be the answer.
            assert r.exit_id not in sc["blockedExits"], sc["id"]


@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_the_refusal_case_is_actually_exercised(site):
    """RO2.2 requires a refuge instruction when no exit is reachable.

    The code has always implemented it, but no scenario reached it, so the
    correct-refusal measure could only ever report zero — which reads as "never
    tested" and "never passed" in exactly the same way.
    """
    refuges = [s for s in site.route_scenarios if s["expect"]["refugeExpected"]]
    assert refuges, f"{site.key} has no scenario where every exit is cut"
    for sc in refuges:
        r = _route(site, sc["fireZone"], blocked=tuple(sc["blockedExits"]))
        assert r.is_refuge, sc["id"]
        assert r.exit_id is None, sc["id"]
        assert r.refuge_node is not None, sc["id"]


@pytest.mark.parametrize("site", [HOME, INDUSTRIAL], ids=["home", "industrial"])
def test_both_sites_carry_comparable_route_evidence(site):
    """Section 3.3.7 asks for at least eight fire-location / blocked-exit
    combinations. Both profiles must meet it, not just the one the results
    chapter happens to report."""
    total = len(site.ground_truth) + len(site.route_scenarios)
    assert total >= 8, (site.key, total)


def test_a_broken_site_file_refuses_to_load():
    with pytest.raises(sites.SiteError):
        sites.load("no-such-site")
