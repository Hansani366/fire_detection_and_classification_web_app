"""
Canned fires, for demonstrating the response path without lighting anything.

WHY THIS EXISTS. Two of the three fuel classes cannot be produced safely in a
room with people in it. A gas fire needs an escaping flammable gas and a liquid
fuel fire needs an open pool of solvent, so the only class anyone can actually
demonstrate is solid combustibles -- which is exactly the limitation Section 5
records for the training data. The consequence for a demonstration is worse than
it looks: the fuel verdict drives the extinguisher guidance, and the one piece of
guidance that matters most (isolate the gas supply BEFORE putting the flame out)
belongs to the class nobody can show.

WHAT A SCENARIO IS, AND WHAT IT IS NOT. Each entry below is the input a real
detection would produce -- the vision model's structured scene, the detector and
sensor evidence logged for the same frame, and the fuel verdict the classifier
would return. It is NOT a pre-written report. The scene still goes through
report.py's grounding check exactly as a live one does, graded against the
evidence beside it and against the fuel verdict read back off the incident row.
A scenario whose numbers did not agree with each other would have its claims
withheld, in the demonstration, in front of everyone. That is deliberate: a
demonstration that cannot fail proves nothing.

HOW THE NUMBERS WERE CHOSEN. Each one is picked so the claim it backs lands in
the band report.py checks it against:

  * `fireAreaRatio` sits inside the `_SIZE_BANDS` window for the `sizeBand` the
    scene claims -- 0.03 is "small", 0.08 is "moderate".
  * `smokeBoxes` agrees with `smokePresent`. The gas fire claims no smoke and
    logs no smoke box, which is a supported negative rather than a missing
    check. A gas jet burns close to clean, so this is also what the detector
    would really return.
  * `materialFamily` matches the family the fuel class maps to in
    `report._FAMILY_BY_FUEL`, so the material claim resolves against the
    classifier instead of going unsupported.
  * `occupancy` is filled in at request time from the head-count the incident is
    opened with, so the people claim is checked against the same number the
    evacuation runs on.

THE GAS SCENARIO IS A FIRE, NOT A GAS WARNING. `gas_fire` is EN 2 class C: a
flame fed by a flammable gas, visible on camera. It is not tier 1b, which is
dangerous carbon monoxide with nothing visible at all and no fuel to classify.
/api/test-alert already covers tier 1b through its `severity` argument, and the
two must not be confused: one recommends isolating a supply, the other has no
fuel verdict to recommend anything about.
"""

# Keyed by the short name a caller passes, valued by everything one simulated
# fire needs. `fuel` is the classifier's own class name, so it lines up with
# extinguishers.EXTINGUISHERS without a translation table in between.
SCENARIOS = {
    "solid": {
        "label": "Solid combustible fire",
        "blurb": "Fabric rolls and packaging alight — EN 2 class A.",
        "fuel": "solid_combustible",
        "fuelConfidence": 0.87,
        "type": "fire",
        "confidence": 0.92,
        "description": (
            "Open flames among the fabric rolls with smoke rising toward the "
            "ceiling."
        ),
        "sensorSummary": "MQ-2 540 ppm (warn), 63 °C (danger), CO 22 ppm (normal)",
        "scene": {
            "description": (
                "Open flames are visible among the fabric rolls with smoke "
                "rising toward the ceiling."
            ),
            "material": "fabric rolls and cardboard packaging",
            "materialFamily": "solid",
            "sizeBand": "moderate",
            "sizeNote": "roughly one pallet width",
            "smokePresent": True,
            "smokeColour": "grey",
            "smokeDensity": "thickening",
        },
        "evidence": {
            "fireAreaRatio": 0.08,   # inside the 0.02–0.25 "moderate" window
            "fireBoxes": 1,
            "smokeBoxes": 2,         # agrees with smokePresent = True
            "gasLevel": "warn",
        },
    },
    "gas": {
        "label": "Gas fire",
        "blurb": "Propane jet at a cylinder coupling — EN 2 class C.",
        "fuel": "gas_fire",
        "fuelConfidence": 0.83,
        "type": "fire",
        "confidence": 0.89,
        "description": (
            "A steady jet flame at a gas cylinder coupling, burning almost "
            "clean with no smoke plume."
        ),
        # The MQ-2 reads high because the leak feeding the flame is also filling
        # the room. That is the whole reason class C is isolated before it is
        # extinguished, and it is why this scenario's gas channel is 'danger'
        # while the solid one's is only 'warn'.
        "sensorSummary": "MQ-2 910 ppm (danger), 48 °C (warn), CO 18 ppm (normal)",
        "scene": {
            "description": (
                "A steady blue jet flame is burning at the coupling of a gas "
                "cylinder. There is almost no smoke."
            ),
            "material": "escaping propane at a cylinder coupling",
            "materialFamily": "gas",
            "sizeBand": "small",
            "sizeNote": "a jet roughly half a metre long",
            # A gas jet burns close to clean. Claiming no smoke and logging no
            # smoke box makes this a SUPPORTED negative, which is the case the
            # grounding check handles differently from a missing observation.
            "smokePresent": False,
            "smokeColour": "",
            "smokeDensity": "",
        },
        "evidence": {
            "fireAreaRatio": 0.03,   # inside the 0.0–0.05 "small" window
            "fireBoxes": 1,
            "smokeBoxes": 0,         # agrees with smokePresent = False
            "gasLevel": "danger",
        },
    },
    # Included because the classifier has three classes and a demonstration that
    # shows two of them invites the question about the third. Not wired to a
    # button on the dashboard; reachable by name through the API.
    "liquid": {
        "label": "Liquid fuel fire",
        "blurb": "Spilled solvent alight — EN 2 class B.",
        "fuel": "liquid_fuel",
        "fuelConfidence": 0.79,
        "type": "fire",
        "confidence": 0.90,
        "description": (
            "A pool of spilled solvent alight on the floor with dense black "
            "smoke above it."
        ),
        "sensorSummary": "MQ-2 700 ppm (danger), 55 °C (warn), CO 41 ppm (warn)",
        "scene": {
            "description": (
                "A spreading pool of burning solvent on the floor, with dense "
                "black smoke rolling off it."
            ),
            "material": "spilled solvent from a drum",
            "materialFamily": "liquid",
            "sizeBand": "moderate",
            "sizeNote": "about two metres across",
            "smokePresent": True,
            "smokeColour": "black",
            "smokeDensity": "dense",
        },
        "evidence": {
            "fireAreaRatio": 0.11,
            "fireBoxes": 2,
            "smokeBoxes": 3,
            "gasLevel": "warn",
        },
    },
}

NAMES = tuple(SCENARIOS)


def get(name: str) -> dict | None:
    """One scenario by name, or None if there is no such fuel."""
    return SCENARIOS.get((name or "").strip().lower())


def catalogue() -> list[dict]:
    """The list a dashboard renders its buttons from.

    Served rather than hard-coded in the page for the same reason the
    extinguisher table is: adding a fourth scenario should not mean editing two
    files that can then disagree about what the third one was called.
    """
    return [
        {
            "name": name,
            "label": s["label"],
            "blurb": s["blurb"],
            "fuel": s["fuel"],
            "fireClass": {"solid_combustible": "A",
                          "liquid_fuel": "B",
                          "gas_fire": "C"}.get(s["fuel"], "—"),
        }
        for name, s in SCENARIOS.items()
    ]
