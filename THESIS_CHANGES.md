# Thesis edits required by the built artefact

**Why this file exists.** The evacuation routing described in Chapter 3 has now been
built, and the facility it runs on is your real home layout rather than a sketch of a
factory. Several figures in Chapter 3 no longer describe what the system does. Each
entry below gives the sentence as written, what the artefact actually does, and the
change to make.

Nothing here is a defect. These are places where the written plan and the built thing
diverged, and the thesis is the side that has to move.

---

## 1. §3.3.7 — "six zones, three exits and nine corridor segments"

**As written:**

> We drew a floor plan of the home and encoded it as the facility graph (Assumption A4),
> with rooms as zones, doors to the outside as exits and hallways as corridor segments.
> **The graph has six zones, three exits and nine corridor segments.**

**What was built,** from `home_layout.png`:

| | Written | Built |
|---|---|---|
| Zones | 6 | **8** |
| Exterior exits | 3 | **2** |
| Corridor segments | 9 | **16 graph edges** (see below) |
| Graph nodes | — | 17 (8 room, 5 door, 2 opening, 2 exit) |
| Footprint | — | 13.28 m × 9.68 m |

**Change to make.** Replace that sentence with:

> The graph has eight zones, two exterior exits and sixteen walkable segments, over
> seventeen nodes: one per monitored area, one per internal doorway, one per wide
> opening between the shared spaces, and one per exterior door.

**Why 8 and not 6.** The sketch labels eight distinct areas — Kitchen, Dining Area,
Living Area, Verander, and four Bedrooms — and all eight are modelled, because leaving
two of them out would mean the route generator could not place an occupant in them.

**Why 2 and not 3.** The sketch has four marks on the outer walls. Two are the exterior
doors, one off the dining area at the front and one off the verander at the back. The
remaining marks are windows.

**Why "corridor segments" no longer fits.** A house has no corridors. The circulation
here *is* the dining/living/verander chain, and those are monitored rooms in their own
right. Every edge in the graph therefore touches a room node, and there is no subset
that can honestly be called "corridor segments". "Walkable segments" is the accurate
term and matches §3.2.5.4's own wording ("edges are walkable segments weighted by
physical length").

---

## 2. §3.3.7 — the six route scenarios

**As written**, six combinations are promised. Five of them work on this layout as
described. One does not survive contact with the building.

| # | Scenario | Status | Note |
|---|---|---|---|
| 1 | Fire far from all exits, obvious route correct | **holds** | Fire in Bedroom (NE) → front door, 5.4 m |
| 2 | Fire beside the nearest exit, obvious route wrong | **holds** | Fire in the Dining Area sits 1.1 m from the front door; that exit is cut and the route reverses south, 9.8 m |
| 3 | Fire in a corridor on the shortest path, longer route chosen | **holds, with a caveat** | See below |
| 4 | Two exits blocked, only a distant exit remains | **cannot happen** | There are only two exits. Blocking both gives scenario 5 |
| 5 | All exits cut off, refuge instruction returned | **holds** | And it occurs naturally — see §3 below |
| 6 | Occupants in several areas, different routes each | **holds** | One living-area fire sends the SW bedroom to the back door and the NE bedroom to the front |

**Change to make.** Drop scenario 4, and reword scenario 3:

> Fire across the only path to the nearest exit, so that the longer route must be
> chosen. Note that this applies only to occupants of the shared spaces. Every bedroom
> and the kitchen in this house has a single door onto a shared area, so for their
> occupants the answer is either that one door or a refuge instruction — never a longer
> detour.

Then reduce the promised count. §3.3.7 currently says "at least eight combinations are
tested"; with two exits and eight zones the honest figure is:

> Ten combinations are tested: one fire in each of the eight zones, plus the two
> exit-blocking cases.

---

## 3. §3.3.7 — the refuge case is not staged

**Worth adding**, because it strengthens the claim rather than weakening it. As written,
the refuge scenario is produced by marking exits blocked by hand. On this layout it
arises on its own:

> A fire in the dining area blocks the doorway between the kitchen and the dining area,
> and the kitchen has no second door. The correct output for an occupant in the kitchen
> is therefore a refuge instruction, and the system produces one without any exit being
> marked blocked. This case was not designed into the scenario set; it is a property of
> the building.

The same is true of the living area and the SE bedroom.

---

## 4. §3.2.5.4 — the hazard radius is per-site

**As written**, the hazard radius is a single unqualified value.

**What was built:** 6.0 m for the demonstration facility, **2.0 m for the home**.

**Change to make.** Add after the edge-blocking rule:

> The hazard radius is a property of the facility, not a constant. In the 36 m
> demonstration hall a 6 m radius blocks the segments immediately around the fire. In
> the 13 m home the same value would reach every room from anywhere and every route
> would collapse to a refuge instruction, so 2 m is used there — enough to block the
> doorway a fire stands in without swallowing the building.

---

## 5. §3.2.5.4 — the occupant's position, and what happens inside the radius

**Not currently stated, and it should be.** Two simplifications are load-bearing:

> The system knows which zone an occupant is in, not where in it they are standing, so
> each zone carries one authored position from which its routes are generated.
> Similarly the fire is modelled as a point, at an authored position within the zone;
> the detection pipeline reports which zone is burning, not where in the room.
>
> In a domestic-sized room an occupant of the burning zone is necessarily inside the
> hazard radius. In that case the route is generated from the first reachable point
> outside the radius, and the instruction is prefixed accordingly — "Leave the kitchen
> immediately, then leave through the front door." If no such point can be reached, a
> refuge instruction is returned instead.

---

## 6. Ch. 1 RO2.3 vs §3.3.7 — an existing internal inconsistency

Unrelated to the layout, and present in the text already:

- **Ch. 1 RO2.3** requires "at least **fifteen** fire location and blocked exit combinations".
- **§3.3.7** says "at least **eight** combinations".
- The artefact supports **ten** (above).

**Change to make.** Pick one figure and use it in both places. Ten is what can be tested
on this facility.

---

## 7. Ch. 1 RO3.4 vs §3.3.8 — a second existing inconsistency

- **Ch. 1 RO3.4** requires "at least **eight** qualified participants".
- **§3.3.8** targets "**five** participants".

**Change to make.** Align the two. §3.3.8 already frames the small sample as a stated
limitation rather than a defended statistical sample, so five is the defensible figure —
but RO3.4 must then say five.

---

## 8. Ch. 1 RO3.2 — extinguishing agents

**As written:** RO3.2 covers "water, foam, carbon dioxide, dry powder and wet chemical
agents" — five agents.

**What was built:** three fuel classes (A, B, C) in `alert-service/extinguishers.py`,
covering water, foam, CO₂ and dry powder. There is **no class F and no wet chemical**,
and the guidance table says so explicitly: a chip-pan fire is reported as liquid fuel.

**Change to make.** Either drop wet chemical from RO3.2, or keep it and state the gap in
§3.4.10 alongside the other limitations. The code already records the limitation
honestly; the objective should not claim more than the table delivers.

---

## 9. §3.4.6 — what the delivery-time figure measures

**Built.** `POST /api/incidents/{id}/delivered`, with both ends of the interval stamped by
the server. The wording to use:

> The decision-to-delivery interval is measured as a round trip on the server clock —
> from the moment the message is handed to Firebase Cloud Messaging to the moment the
> device's acknowledgement arrives — and halved. Measuring it this way avoids any
> dependence on the accuracy of the handset's clock. It assumes a symmetric network
> path and includes the application's own handling time in the estimate.

The app acknowledges from three places — a foreground message, a background/terminated
message, and a notification tap — and the backend keeps whichever arrives first. The
background path matters most and is the one a foreground-only implementation would miss:
an alert reaching a phone in somebody's pocket at night is the delivery the measurement is
actually about. Per-incident figures are in the incident report; the distribution across
all incidents is at `GET /api/analysis/delivery`.

**One thing to state plainly in §3.4.10.** A device that never acknowledges is invisible to
the median. `delivery_stats` reports `devices` (pushes sent) alongside `acknowledged`
(round trips closed) for exactly that reason — if those two numbers diverge, the median is
describing the phones that answered, not the phones that were sent to.

---

---

## 10. §3.4.8 — the head-count comparison is now a stored measurement

**As written**, §3.4.8 asks for the head-count and the check-out count "reported side by
side, and every difference listed". Both are now recorded per incident and served together
in the incident record, so the comparison is read from data rather than assembled by hand.

Worth adding to the method, because it is a design decision the numbers depend on:

> A check-out is recorded against the device that sent it, so repeated taps, a reopened
> notification or a retried request all count once. The two figures are never reconciled:
> where the camera's peak head-count exceeds the check-out count, the difference is
> reported rather than resolved in favour of either instrument.

Note also that the synthetic muster constants the prototype shipped with (42 of 45) are no
longer used once real check-outs exist. If any earlier screenshot in the thesis shows
those numbers, it predates this and should be retaken.

## Figures and tables to regenerate

- **Figure of the facility graph** (§3.3.7) — should now show 8 zones, 2 exits,
  17 nodes, 16 edges. The authoritative data is
  `fire_detection_and_classification_web_app/alert-service/sites/home.json`.
- **Route results table** (§3.4.8) — the generator is built and the four measures are
  served by `GET /api/analysis/routes`, computed from stored routes rather than
  recomputed. Hand-derived ground truth for each zone lives in the `groundTruth` block
  of the same site file and in `alert-service/test_routing.py`.

## Route lengths on the built graph, for reference

Fire in each zone, occupant in that zone:

| Fire in | Exit chosen | Route |
|---|---|---|
| Kitchen | Front door | 5.0 m |
| Dining Area | Back door | 9.8 m (front door cut) |
| Living Area | Back door | 4.8 m |
| Verander | Front door | 9.7 m |
| Bedroom (West) | Back door | 10.1 m |
| Bedroom (SW) | Back door | 6.2 m |
| Bedroom (NE) | Front door | 5.4 m |
| Bedroom (SE) | Back door | 10.5 m |

Slowest route generation across all 64 fire/occupant pairs: **under 0.5 ms**, against
RO2.2's five-second budget. The reportable figure is the end-to-end latency from
detection, which the system records per incident as `route_latency_ms`.
