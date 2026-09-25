"""
The situation report, and the grounding check that runs before it is released.

RO3.1 asks for a structured description of the event -- what is burning, where,
roughly how big, what the smoke is doing, and whether anyone is present -- and it
asks that **every generated claim is validated against the logged detection and
sensor evidence before release**. This module is that validation.

WHY IT RUNS HERE AND NOT IN THE VLM SERVICE. A model cannot mark its own
homework. The evidence a claim has to be checked against -- detector boxes, the
human count, graded sensor levels, the fuel classifier's verdict, the stored zone
model -- all lives on this side. Asking the vision service to self-validate would
just be asking it a second question.

WHY IT RUNS AT ALL, GIVEN SECTION 3.4.7. The methodology describes claim-level
grounding as an analysis performed afterwards, on logs. That measures how often
the model hallucinates; it does nothing for the responder holding the phone while
it happens. The same three categories (Table 3.20) applied at release time turn a
measurement into a control.

THE THREE CATEGORIES, AND WHAT EACH ONE COSTS:

    supported    Confirmed by detector output, sensor evidence or the zone model.
                 Released plainly.

    contradicted Directly contradicted by the logged evidence. WITHHELD from the
                 released text. This is the serious one: a claim that the camera
                 sees nobody when the human detector counts three is not a
                 nuance, and a responder acting on it makes a worse decision than
                 one who was told nothing.

    unsupported  Cannot be checked against any logged evidence. Released but
                 MARKED. Dropping these would quietly strip the report of most of
                 its content -- the smoke colour is genuinely useful and nothing
                 else in the system observes it -- but presenting them as findings
                 would be exactly the hallucination risk Table 3.20 names.

A claim nobody can check is not the same as a claim that is wrong, and neither is
the same as a claim that is right. Collapsing those three into "the model said
so" is the failure this module exists to prevent.

WHAT MAY OVERRULE WHAT. A fire is confirmed by the fire detector and the VLM
agreeing on the same frame; the sensors are there to catch gas leaks, which can
kill with nothing visible, and to feed the fuel classifier. So a claim about what
the camera saw is graded against same-frame detector output and against the
classifier's verdict -- never against a raw sensor reading. The gas channel is
still stored with the incident as logged evidence for the analysis in Section
3.4.7; it simply gets no vote on what reaches a responder.
"""

SUPPORTED = "supported"
CONTRADICTED = "contradicted"
UNSUPPORTED = "unsupported"

# Families the fuel classifier can speak about, mapped to its class names.
_FAMILY_BY_FUEL = {
    "solid_combustible": "solid",
    "liquid_fuel": "liquid",
    "gas_fire": "gas",
}

# Fraction of the frame a fire box must cover for each size band. Deliberately
# coarse: this checks whether a claim is contradicted, not how big the fire is.
_SIZE_BANDS = (
    ("small", 0.0, 0.05),
    ("moderate", 0.02, 0.25),
    ("large", 0.15, 1.01),
)


def _claim(cid, label, text, category, evidence, why):
    return {"id": cid, "label": label, "text": text, "category": category,
            "evidence": evidence, "why": why}


def _check_material(scene, ev):
    """What is burning, against the fuel classifier."""
    material = (scene.get("material") or "").strip()
    if not material:
        return None
    family = (scene.get("materialFamily") or "unknown").lower()
    fuel = ev.get("fuelType")
    text = f"Burning material: {material}"

    if not fuel:
        return _claim("material", "Material", text, UNSUPPORTED, "none",
                      "The fuel classifier has not returned a verdict for this "
                      "incident, so nothing here can confirm or deny it.")
    expected = _FAMILY_BY_FUEL.get(fuel)
    if family == "unknown" or expected is None:
        return _claim("material", "Material", text, UNSUPPORTED, "classifier",
                      "The description does not commit to a fuel family, so it "
                      "cannot be compared with the classifier.")
    if family == expected:
        return _claim("material", "Material", text, SUPPORTED, "classifier",
                      f"The fuel classifier independently reports {expected}.")
    return _claim("material", "Material", text, CONTRADICTED, "classifier",
                  f"The description says {family}; the fuel classifier reports "
                  f"{expected} from the sensor and vision channels.")


def _check_location(zone):
    """Location is system-supplied, so it is the one claim that cannot drift.

    The model is never asked where it is. The zone comes from the stored zone
    model and the detector that raised the event, which is why this is always
    supported -- and why it is still listed: a report that omits the location is
    not a report, and its provenance deserves to be visible next to the claims
    that were generated.
    """
    name = zone.get("name") or zone.get("id") or "Unknown zone"
    floor = zone.get("floor") or ""
    where = f"{name}{', ' + floor if floor else ''}"
    return _claim("location", "Location", f"Location: {where}", SUPPORTED,
                  "zone model",
                  "Taken from the stored zone model and the detector that "
                  "raised the event. Not generated.")


def _check_size(scene, ev):
    """Approximate size, against the largest fire box as a share of the frame."""
    band = (scene.get("sizeBand") or "").strip().lower()
    if not band:
        return None
    note = (scene.get("sizeNote") or "").strip()
    text = f"Approximate size: {band}{' — ' + note if note else ''}"
    area = ev.get("fireAreaRatio")

    if area is None:
        return _claim("size", "Size", text, UNSUPPORTED, "none",
                      "No detector box area was logged for this frame, so the "
                      "extent cannot be checked.")
    allowed = next((b for b in _SIZE_BANDS if b[0] == band), None)
    if allowed is None:
        return _claim("size", "Size", text, UNSUPPORTED, "detector",
                      "The size band is not one the check understands.")
    _, lo, hi = allowed
    pct = area * 100
    if lo <= area <= hi:
        return _claim("size", "Size", text, SUPPORTED, "detector",
                      f"The largest fire box covers {pct:.1f}% of the frame, "
                      f"consistent with '{band}'.")
    return _claim("size", "Size", text, CONTRADICTED, "detector",
                  f"The largest fire box covers {pct:.1f}% of the frame, which "
                  f"is outside the range for '{band}'.")


def _check_smoke(scene, ev):
    """Smoke, against the smoke detector class on the same frame.

    THE GAS CHANNEL DELIBERATELY TAKES NO PART IN THIS. The sensors are not part
    of visual fire detection: a fire is confirmed by YOLO and the VLM agreeing,
    and the sensors exist to catch gas leaks -- which can kill with nothing
    visible -- and to feed the fuel classifier. Letting a gas reading grade a
    visual observation borrows an instrument for a job it was never pointed at.

    It would also be wrong in practice. Gas has to drift to a sensor on the
    ceiling and arrives well after a camera sees the flame, so at the moment a
    report is generated the channel usually still reads normal. Withholding a
    correct smoke description on that basis treats a lagging instrument's silence
    as evidence of absence.

    The asymmetry below is on purpose. A missing smoke box makes a claim
    UNSUPPORTED, not contradicted: smoke is the weaker of the two detector
    classes, which is why Section 3.4.3 reports per-class results rather than a
    mean, and overruling the VLM because a known-weak detector missed a box would
    be the more confident error. A smoke box found while the description denies
    smoke is different -- that is positive evidence, on the same frame, against a
    negative claim.
    """
    present = scene.get("smokePresent")
    if present is None:
        return None
    colour = (scene.get("smokeColour") or "").strip()
    density = (scene.get("smokeDensity") or "").strip()
    detail = ", ".join(p for p in (density, colour) if p)
    text = ("Smoke: " + (detail if detail else "present")) if present \
        else "Smoke: none visible"

    boxes = ev.get("smokeBoxes")

    if boxes is None:
        return _claim("smoke", "Smoke", text, UNSUPPORTED, "none",
                      "No detector output was logged for this frame, so there is "
                      "nothing to check the description against.")
    if present:
        if boxes > 0:
            return _claim("smoke", "Smoke", text, SUPPORTED, "detector",
                          f"The fire detector found {boxes} smoke box(es) in "
                          "the same frame.")
        return _claim("smoke", "Smoke", text, UNSUPPORTED, "detector",
                      "The fire detector found no smoke box in this frame. Smoke "
                      "is the weaker detector class, so this neither confirms nor "
                      "refutes what the description reports.")
    if boxes > 0:
        return _claim("smoke", "Smoke", text, CONTRADICTED, "detector",
                      f"The fire detector found {boxes} smoke box(es) in the "
                      "same frame.")
    return _claim("smoke", "Smoke", text, SUPPORTED, "detector",
                  "No smoke box in the frame either.")


def _check_people(scene, ev):
    """Presence of any person, against the human detector.

    The human detector wins every disagreement here. It is a trained counter
    pointed at the same frame, and the head-count it produces is the number the
    evacuation is run on -- so a scene description that quietly disagrees with it
    is worse than no description.
    """
    visible = scene.get("peopleVisible")
    claimed = scene.get("peopleCount")
    if visible is None and claimed is None:
        return None
    if visible is False:
        text = "People: none visible in the zone"
    elif claimed is not None:
        text = f"People: {claimed} visible in the zone"
    else:
        text = "People: at least one visible in the zone"

    counted = ev.get("occupancy")
    if counted is None:
        return _claim("people", "People", text, UNSUPPORTED, "none",
                      "The human detector had nothing to report for this frame, "
                      "which is not the same as an empty room.")
    if visible is False and counted > 0:
        return _claim("people", "People", text, CONTRADICTED, "human detector",
                      f"The human detector counts {counted} in the zone.")
    if visible is not False and counted == 0:
        return _claim("people", "People", text, CONTRADICTED, "human detector",
                      "The human detector counts nobody in the zone.")
    if claimed is not None and counted is not None and abs(claimed - counted) > 1:
        return _claim("people", "People", text, CONTRADICTED, "human detector",
                      f"The human detector counts {counted}, not {claimed}.")
    return _claim("people", "People", text, SUPPORTED, "human detector",
                  f"The human detector counts {counted} in the zone.")


def build(scene: dict | None, evidence: dict | None, zone: dict) -> dict:
    """Assemble the report, grade every claim, and release only what survives.

    Returns the released text, the full claim list with verdicts, and the
    grounding figures of Section 3.4.7 computed over this one report.
    """
    scene = scene or {}
    ev = evidence or {}

    claims = [c for c in (
        _check_location(zone),
        _check_material(scene, ev),
        _check_size(scene, ev),
        _check_smoke(scene, ev),
        _check_people(scene, ev),
    ) if c]

    released = [c for c in claims if c["category"] != CONTRADICTED]
    withheld = [c for c in claims if c["category"] == CONTRADICTED]

    n = len(claims)
    supported = sum(1 for c in claims if c["category"] == SUPPORTED)
    unsupported = sum(1 for c in claims if c["category"] == UNSUPPORTED)

    # The model's own sentence rides along only as context, never as a finding:
    # it is prose, so it cannot be graded claim by claim, and anything in it that
    # mattered is already a claim above.
    narrative = (scene.get("description") or "").strip()

    return {
        "text": "\n".join(c["text"] for c in released),
        "narrative": narrative,
        "claims": claims,
        "released": [c["id"] for c in released],
        "withheld": [{"id": c["id"], "text": c["text"], "why": c["why"]}
                     for c in withheld],
        "grounding": {
            "claims": n,
            "supported": supported,
            "unsupported": unsupported,
            "contradicted": len(withheld),
            # Section 3.4.7's two figures, over this report.
            "groundingAccuracy": round(supported / n, 3) if n else None,
            "hallucinationRate": round((unsupported + len(withheld)) / n, 3) if n else None,
        },
        "validatedBeforeRelease": True,
        "note": ("Contradicted claims are withheld. Unsupported claims are shown "
                 "but marked: nothing in the system can confirm or deny them."),
    }
