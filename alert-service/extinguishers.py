"""
What to fight each fuel with — and what must never be used on it.

WHY THIS IS A TABLE AND NOT A SENTENCE. The wrong extinguisher does not simply
fail: water on burning liquid throws it across the room, water on a metal fire
reacts violently, and putting out a gas flame while the gas still flows fills
the space with an explosive cloud that a spark then finds. So each fuel carries
a first action, what to use, and — the part that actually saves people — what
NOT to use and why.

WHY IT LIVES IN alert-service. The phone needs it in a push, the dashboard
needs it on screen, and the incident record needs it for the report. One table,
served over /api/extinguishers, so those three cannot drift apart into three
different answers about the same fire.

CLASSES ARE EN 2 (EUROPEAN). A = solids, B = liquids, C = gases, D = metals,
F = cooking oils. American NFPA numbering differs (their C is electrical), so
the letter is always shown together with a plain description rather than on its
own.

WHAT THE MODEL CANNOT TELL YOU, AND WHY IT IS IN HERE. The classifier has three
fuel classes. Real fires have more, and two gaps matter enough to print every
time:

  * Cooking oil is class F, not B. It needs wet chemical. Foam or water on a
    deep-fat fire causes a violent boil-over. The model has no class F and will
    call a chip-pan fire `liquid_fuel`, so a kitchen needs its own judgement.
  * Live electrical equipment changes the answer whatever is burning: only CO2
    or dry powder, never water or foam. The model cannot see whether anything
    is energised.

Neither is a defect to be fixed by tuning — they are limits of a three-class
model, and the operator has to know about them.
"""

# Keyed by the model's class names. `no_fire` deliberately has no entry.
EXTINGUISHERS = {
    "gas_fire": {
        "label": "Gas fire",
        "fire_class": "C",
        "class_description": "Flammable gases — propane, butane, methane",
        # ISOLATE FIRST. This is the one case where putting the fire out is the
        # wrong first move: an unlit leak is more dangerous than a burning one,
        # because the gas keeps filling the room until something ignites all of
        # it at once.
        "first_action": "Isolate the gas supply before anything else.",
        "first_action_why": (
            "Putting out the flame while gas is still flowing lets it fill the "
            "room unburned. The next spark ignites all of it at once. A burning "
            "leak is safer than an unlit one."
        ),
        "use": [
            {"agent": "Dry powder (ABC)",
             "note": "Only once the supply is isolated, or to protect an escape route"},
        ],
        "do_not_use": [
            {"agent": "Water",
             "why": "Does nothing to stop the leak, and can spread burning gas"},
            {"agent": "Foam",
             "why": "Ineffective against a gas jet — it blows straight through"},
        ],
        "short": "Shut off the gas supply FIRST. Do not put the flame out while gas is still flowing.",
    },
    "liquid_fuel": {
        "label": "Liquid fuel fire",
        "fire_class": "B",
        "class_description": "Flammable liquids — petrol, oil, solvents, paint",
        "first_action": "Do not use water. Cut off the air supply instead.",
        "first_action_why": (
            "Burning liquid floats on water and travels with it, so a water jet "
            "spreads the fire across the floor rather than stopping it."
        ),
        "use": [
            {"agent": "Foam (AFFF)", "note": "Best choice — seals the surface and stops vapour"},
            {"agent": "CO2", "note": "Leaves no residue; good near equipment"},
            {"agent": "Dry powder (ABC)", "note": "Fast knock-down, heavy mess afterwards"},
        ],
        "do_not_use": [
            {"agent": "Water",
             "why": "Spreads burning liquid and can cause a violent flare-up"},
        ],
        "short": "Do NOT use water — it will spread burning liquid. Use foam, CO2 or dry powder.",
        # The model has no class F, so every kitchen fire lands here.
        "caution": (
            "If this is cooking oil or fat, it is class F, not B — use a wet "
            "chemical extinguisher. Foam or water on a deep-fat fire causes a "
            "violent boil-over. This model cannot tell the two apart."
        ),
    },
    "solid_combustible": {
        "label": "Solid combustibles",
        "fire_class": "A",
        "class_description": "Solid materials — wood, paper, cloth, most plastics",
        "first_action": "Cool the burning material with water or foam.",
        "first_action_why": (
            "Solids keep re-igniting from their own heat, so the fire is only "
            "out once the material itself has been cooled through."
        ),
        "use": [
            {"agent": "Water", "note": "Most effective — cools the material through"},
            {"agent": "Foam (AFFF)", "note": "Also works, and clings to vertical surfaces"},
            {"agent": "Dry powder (ABC)", "note": "Knocks flames down but does not cool — it can reignite"},
        ],
        "do_not_use": [
            {"agent": "CO2",
             "why": "Knocks the flames down without cooling, so deep-seated material reignites"},
        ],
        "short": "Water or foam is suitable for this fuel.",
    },
}

# Printed alongside every verdict, because neither depends on which fuel the
# model picked and both change the correct answer.
UNIVERSAL_CAUTIONS = [
    {
        "title": "Live electrical equipment",
        "detail": (
            "If anything nearby is still energised, use CO2 or dry powder only — "
            "never water or foam. Isolate the power if you safely can. The "
            "classifier cannot see whether equipment is live."
        ),
    },
    {
        "title": "Only fight a fire you can walk away from",
        "detail": (
            "An extinguisher is for a small fire and an escape route behind you. "
            "If the room is filling with smoke, leave and call the fire service."
        ),
    },
]


def guidance_for(fuel_type: str | None) -> dict | None:
    """The full response guidance for one fuel, or None if it is not a fire."""
    entry = EXTINGUISHERS.get(fuel_type or "")
    if not entry:
        return None
    return {**entry, "universal_cautions": UNIVERSAL_CAUTIONS}


def short_guidance(fuel_type: str | None) -> str:
    """One sentence, for a notification body where there is no room for a table."""
    entry = EXTINGUISHERS.get(fuel_type or "")
    return entry["short"] if entry else ""


def label_for(fuel_type: str | None) -> str:
    entry = EXTINGUISHERS.get(fuel_type or "")
    return entry["label"] if entry else "Fire"
