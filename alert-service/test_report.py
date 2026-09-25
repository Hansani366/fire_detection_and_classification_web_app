"""The grounding check that runs before a situation report is released (RO3.1).

The rule being tested: a claim the evidence contradicts never reaches the
responder, a claim nothing can check reaches them marked, and a claim the
evidence confirms reaches them plainly.
"""

import report

ZONE = {"id": "fabric-store", "name": "Fabric Store", "floor": "Main floor"}


def _build(scene=None, ev=None):
    return report.build(scene or {}, ev or {}, ZONE)


def _by_id(out, cid):
    return next((c for c in out["claims"] if c["id"] == cid), None)


# ── The invariant ───────────────────────────────────────────────────────────

def test_a_contradicted_claim_never_reaches_the_released_text():
    out = _build(
        {"peopleVisible": False, "description": "Empty room."},
        {"occupancy": 3},
    )
    people = _by_id(out, "people")
    assert people["category"] == report.CONTRADICTED
    assert "people" not in out["released"]
    assert "none visible" not in out["text"]
    assert out["withheld"][0]["id"] == "people"


def test_the_human_detector_wins_a_disagreement_about_people():
    out = _build({"peopleVisible": True, "peopleCount": 6}, {"occupancy": 1})
    assert _by_id(out, "people")["category"] == report.CONTRADICTED


def test_an_off_by_one_head_count_is_not_called_a_contradiction():
    # Detector counts flicker by a person; a report is not a census.
    out = _build({"peopleVisible": True, "peopleCount": 3}, {"occupancy": 2})
    assert _by_id(out, "people")["category"] == report.SUPPORTED


def test_agreeing_that_the_room_is_empty_is_supported():
    out = _build({"peopleVisible": False}, {"occupancy": 0})
    assert _by_id(out, "people")["category"] == report.SUPPORTED


def test_an_unknown_head_count_leaves_the_claim_unchecked_not_wrong():
    out = _build({"peopleVisible": True, "peopleCount": 2}, {"occupancy": None})
    c = _by_id(out, "people")
    assert c["category"] == report.UNSUPPORTED
    assert "people" in out["released"]      # marked, not withheld


# ── Material, against the fuel classifier ───────────────────────────────────

def test_material_agreeing_with_the_classifier_is_supported():
    out = _build({"material": "fabric rolls", "materialFamily": "solid"},
                 {"fuelType": "solid_combustible"})
    assert _by_id(out, "material")["category"] == report.SUPPORTED


def test_material_disagreeing_with_the_classifier_is_withheld():
    out = _build({"material": "spilled solvent", "materialFamily": "liquid"},
                 {"fuelType": "solid_combustible"})
    assert _by_id(out, "material")["category"] == report.CONTRADICTED
    assert "material" not in out["released"]


def test_material_with_no_classifier_verdict_is_unsupported():
    out = _build({"material": "cardboard", "materialFamily": "solid"}, {})
    assert _by_id(out, "material")["category"] == report.UNSUPPORTED


def test_a_model_that_declines_to_name_a_fuel_makes_no_claim():
    out = _build({"material": None}, {"fuelType": "gas_fire"})
    assert _by_id(out, "material") is None


# ── Size, against the detector box ──────────────────────────────────────────

def test_a_size_band_matching_the_box_area_is_supported():
    out = _build({"sizeBand": "small"}, {"fireAreaRatio": 0.02})
    assert _by_id(out, "size")["category"] == report.SUPPORTED


def test_calling_a_frame_filling_fire_small_is_contradicted():
    out = _build({"sizeBand": "small"}, {"fireAreaRatio": 0.40})
    assert _by_id(out, "size")["category"] == report.CONTRADICTED


# ── Smoke, against the detector and the gas channel ─────────────────────────

def test_smoke_with_a_smoke_box_is_supported():
    out = _build({"smokePresent": True, "smokeColour": "black",
                  "smokeDensity": "thick"}, {"smokeBoxes": 2})
    c = _by_id(out, "smoke")
    assert c["category"] == report.SUPPORTED
    assert "thick" in c["text"] and "black" in c["text"]


def test_the_gas_channel_gets_no_vote_on_a_visual_claim():
    """Sensors catch gas leaks and feed the classifier. They do not grade what
    the camera saw, and the verdict must not move when they change."""
    seen = {
        gas: _by_id(_build({"smokePresent": True},
                           {"smokeBoxes": 0, "gasLevel": gas}), "smoke")["category"]
        for gas in ("normal", "warn", "danger", "")
    }
    assert len(set(seen.values())) == 1, seen
    assert set(seen.values()) == {report.UNSUPPORTED}


def test_a_missed_smoke_box_leaves_the_claim_unchecked_not_refuted():
    """Smoke is the weaker detector class -- Section 3.4.3 reports per-class
    results for exactly this reason. A miss is not a refutation."""
    out = _build({"smokePresent": True, "smokeColour": "black"}, {"smokeBoxes": 0})
    c = _by_id(out, "smoke")
    assert c["category"] == report.UNSUPPORTED
    assert "smoke" in out["released"]          # marked, still shown
    assert "weaker detector class" in c["why"]


def test_denying_smoke_the_detector_can_see_is_contradicted():
    out = _build({"smokePresent": False}, {"smokeBoxes": 3})
    assert _by_id(out, "smoke")["category"] == report.CONTRADICTED


# ── Location, and the shape of the whole thing ──────────────────────────────

def test_location_is_system_supplied_and_always_present():
    out = _build()
    loc = _by_id(out, "location")
    assert loc["category"] == report.SUPPORTED
    assert loc["evidence"] == "zone model"
    assert "Fabric Store" in loc["text"]


def test_grounding_figures_match_section_3_4_7():
    out = _build(
        {"material": "fabric rolls", "materialFamily": "solid",   # supported
         "smokePresent": True,                                    # unsupported
         "peopleVisible": False},                                 # contradicted
        {"fuelType": "solid_combustible", "occupancy": 2, "smokeBoxes": 0},
    )
    g = out["grounding"]
    assert g["claims"] == 4          # + location
    assert g["supported"] == 2
    assert g["unsupported"] == 1
    assert g["contradicted"] == 1
    assert g["groundingAccuracy"] == 0.5
    assert g["hallucinationRate"] == 0.5


def test_the_models_prose_is_carried_as_context_not_as_a_finding():
    out = _build({"description": "Open flames among the fabric rolls."})
    assert out["narrative"] == "Open flames among the fabric rolls."
    assert out["narrative"] not in out["text"]


def test_an_empty_scene_still_produces_a_locatable_report():
    out = _build()
    assert out["grounding"]["claims"] == 1
    assert out["text"].startswith("Location:")
    assert out["validatedBeforeRelease"] is True
