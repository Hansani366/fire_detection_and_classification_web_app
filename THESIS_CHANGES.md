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

## 8. Ch. 1 RO3.2 — wet chemical and Class F are not covered

**As written:** the recommendation mechanism covers "water, foam, carbon dioxide, dry powder
and **wet chemical** agents" — five agents.

**What exists:** three fuel classes (A, B, C) in `alert-service/extinguishers.py`, covering
water, foam, CO₂ and dry powder. The table documents the gap itself: it has no Class F and
will report a chip-pan fire as liquid fuel.

**Change to make.** Revise RO3.2 to the agents actually supported, and document the excluded
scenarios explicitly rather than leaving them implied.

> RO3.2: To develop a recommendation mechanism that maps the classified fire type to an
> appropriate extinguishing agent across water, foam, carbon dioxide and dry powder, and to
> assess the accuracy of these recommendations against ISO 3941 across all tested fire
> materials. Cooking-oil fires (Class F, requiring wet chemical) and electrical fires are
> outside the classifier's scope and are excluded; Section 3.4.10 records the consequence.

The exclusions to state, in the limitations as well as the objective:

- **Cooking oil / Class F.** No wet chemical agent. A chip-pan fire is reported as liquid
  fuel, and the guidance that follows is wrong for it.
- **Electrical fires.** The model cannot see whether equipment is live, which changes the
  correct agent whatever is burning. `/api/extinguishers` already returns this under
  `modelLimits` — the thesis should say it too.

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

---

## 11. Ch. 1 RO1.1 — MQTT at 1 Hz, which nothing implements

**As written:** the sensor node "publishes synchronised readings over **MQTT** at a fixed
interval of **one second**".

**What exists:** no MQTT anywhere. The whole repository was searched for `mqtt`, `paho` and
`mosquitto` — zero matches, in code, in `requirements.txt` and in `docker-compose.yml`.
Nodes POST JSON over HTTP roughly every three seconds, which is also what §3.3.3 describes
("one JSON message pushed over HTTP to the sensor service", "a fixed interval of about
three seconds"). So Chapter 1 contradicts Chapter 3 as well as the artefact.

**Change to make.** Correct RO1.1 to specify **HTTP JSON transmission approximately every
three seconds**. No MQTT broker is needed or used.

> RO1.1: To design and build an ESP32 based multi sensor node that measures combustible
> gas, carbon monoxide, temperature, humidity and flame radiation, and that publishes
> readings as JSON over HTTP at an interval of approximately three seconds.

Two knock-on edits: drop "synchronised" (the node has no clock — §3.3.3 says the server
adds the wall-clock time on arrival), and check §3.4.6, which already correctly notes that
the time before arrival cannot be measured.

---

## 12. Ch. 1 RO1.2 — an indoor industrial test set that does not exist

**As written:** mAP@0.5 of at least 0.85 "on a held out **indoor industrial** test set".

**What exists:** §3.3.2 states plainly that no industrial imagery could be obtained — the
team had no access to industrial premises, real fires could not be created safely in a
working plant, and companies would not share footage. Both detectors are trained and tested
on public data: HomeFire for fire and smoke, CrowdHuman for people. The controlled fire
trials happened inside a home (§3.3.5).

**Change to make.** Correct RO1.2 to describe **public-dataset evaluation on HomeFire and
CrowdHuman, reported separately from the controlled fire testing carried out inside a
home**, and report the actual mAP figures with the conditions they were measured under.

> RO1.2: To train and optimise a YOLO model for the detection and classification of fire
> and smoke, evaluated on the held-out test split of the HomeFire dataset, and to report
> its performance separately from the controlled fire trials conducted in a domestic
> setting.

Keep the 0.85 target only if the measured figure supports it; §3.4.3 already commits to
reporting per-class results, and smoke is usually the weaker class and the one that appears
first.

---

## 13. Ch. 1 RO1.4 and §3.2.4 — four configurations described, five now built

**Status: the code has changed. The thesis still needs the edit below.**

**As written**, in five places: RO1.4 compares "the vision only, sensor only, sensor and
vision fusion, and full configuration with vision language model verification"; §3.2.4 says
switching a layer off "makes it possible to compare the four configurations"; §3.3.5 says
each scenario is observed by "all four system configurations"; §3.3.6 repeats it for the
nuisance runs; and §3.4.5 runs a Friedman test "across the four configurations".

**What was built, and what changed.** Three components give eight possible subsets. Six
were built; one of those six has now been removed, leaving five:

| | Combination | Status |
|---|---|---|
| 1 | sensors only | kept |
| 2 | YOLO only | kept |
| 3 | sensors + YOLO | kept, renumbered from 4 |
| 4 | YOLO + VLM | kept, renumbered from 5 |
| 5 | sensors + YOLO + VLM | kept, renumbered from 6 |
| — | VLM only | **removed** |

**Why "VLM only" was removed rather than corrected.** It described a configuration this
architecture cannot run. Algorithm 3 opens with `if B is empty: return` — the vision
language model is only ever invoked by a YOLO box and cannot open an incident by itself.
The arm's own printed justification claimed it was "invoked on a FIXED cadence, never on
the YOLO gate", but `ablation-service/vlm_adapter.py` states in its header that the
generator runs the VLM only when YOLO fires and holds the verdict between calls. So the
arm read YOLO-gated evidence while claiming not to, and there was no data behind the thing
it claimed to measure. Its VLM confidence score survives as a feature, `combos._vlm_score`,
because combination 4 scores against it — an observation the study uses is not the same as
a configuration it claims to have measured.

The other two of the eight are excluded for the same architectural reason: the empty set
never alarms, and "sensors + VLM" needs the VLM to run with no detector.

**Change to make.** Say five, name them, and pin each hypothesis to numbered combinations
rather than to the phrase "vision only", which has two readings — combination 2, the bare
detector, or combination 4, detector plus verification without sensors.

> The prototype supports five configurations, listed in Table X. This study reports
> combination 1 (sensors only), combination 2 (detector only), combination 3 (sensors and
> detector fused), combination 4 (detector with vision language verification) and
> combination 5 (the full system).

Each pairing differs by exactly one component, which is what makes it an ablation:

| Comparison | Isolates |
|---|---|
| 5 against 3 | what the verification layer adds when sensors are present |
| 5 against 4 | what the sensors add to a verified vision system |
| 3 against 2 | what the sensors add to a bare detector |
| 2 against 1 | vision against sensing, each alone |

**This reaches RO1.3, and it is the reason to be exact.** RO1.3 promises that verification
cuts false alarms by at least 50 per cent "compared with the vision only configuration".
The comparison that isolates the verification layer is **5 against 3**, because those two
differ by the VLM alone. H1 as written compares the full system against "vision only",
which differs by two components at once, so whatever number it produces cannot be
attributed to the verification layer. Restate H1 as a numbered pair.

`GET /api/ablation/config` renders each rule from the constants the code executes, so
Chapter 4's table can be generated from the running system rather than transcribed.

## 14. Ch. 1 RO3.4 — expert evaluation — **TODO, not software**

**Status: outstanding.** This is the one objective no amount of development satisfies.

Everything RO3.4 needs from the artefact now exists: Presentation B (the situation report,
the head-count, the generated evacuation route, the fuel class and the fire-fighting
guidance) can be shown in full. What remains is the research activity.

- [ ] Recruit participants. Note the unresolved count — Ch. 1 says at least **eight**,
      §3.3.8 targets **five** (see §7 above). Fix the number before recruiting, not after.
- [ ] Prepare the three recorded incident scenarios, each in both presentations.
- [ ] Obtain ethical approval sign-off, information sheets and consent forms.
- [ ] Run the sessions to the written script, alternating presentation order.
- [ ] Analyse: Likert medians and frequencies, Wilcoxon signed rank paired comparison, and
      the six-phase thematic analysis of the open questions.
- [ ] Retain the code book and coded extracts as the audit trail (§3.4.9).

**Track this separately from software development.** It is on the critical path to
submission and it has a lead time that writing code does not — recruitment and ethics are
other people's calendars.

---

## 15. §3.4.7 — the grounding check now runs **inside** the system (RO3.1, built)

This is the one entry where the software moved rather than the prose, and §3.4.7 has to
move with it.

**As written:**

> The check is carried out during the analysis, and **it is not a step inside the running
> system**.

**What was built.** RO3.1 requires that "every generated claim is validated against the
logged detection and sensor evidence **before release**", which an after-the-fact analysis
cannot satisfy — it measures how often the model hallucinates without doing anything about
it at the moment it matters. So Table 3.20's three categories are now applied at release
time, in `alert-service/report.py`:

| Claim | Checked against | Source |
|---|---|---|
| Burning material | the fuel classifier's verdict | `fire-classification-service` |
| Location | the stored zone model | never generated — system-supplied |
| Approximate size | largest fire box as a share of the frame | fire YOLO |
| Smoke characteristics | smoke boxes on the same frame | fire YOLO |
| Presence of any person | the head-count | human YOLO |

**Raw sensor readings grade nothing here, and that is deliberate.** A fire is confirmed by
the fire detector and the vision-language model agreeing on the same frame. The sensors have
two jobs — catching a gas leak, which can kill with nothing visible, and feeding the fuel
classifier — and neither of them is refereeing what a camera saw. A gas reading that
overruled a visual observation would be borrowing an instrument for a task it was never
pointed at.

It would also be wrong in practice. Gas has to drift to a sensor near the ceiling and
arrives well after the camera sees the flame, so at the moment a report is generated the
channel usually still reads normal. Withholding a correct smoke description on that basis
treats a lagging instrument's silence as evidence of absence — the same error the system
refuses elsewhere, where an unknown head-count is never read as an empty room.

The gas level is still **stored** with the incident as logged evidence, so the analysis in
§3.4.7 can use it afterwards. It simply gets no vote on what reaches a responder.

**The release rule**, which is the part to state:

- **Contradicted** → withheld. It never reaches the phone. A report saying nobody is present
  while the human detector counts three is not a nuance, and a responder acting on it
  decides worse than one told nothing. Only **same-frame positive evidence** can contradict:
  a detector box that exists, or a head-count that disagrees.
- **A detector that found nothing does not contradict.** Smoke is the weaker of the two
  detector classes, which is why §3.4.3 already reports per-class results rather than a mean.
  A smoke description with no matching box is recorded as unsupported, not refuted —
  overruling the model because a known-weak detector missed something would be the more
  confident error.
- **Unsupported** → released, but **marked "unverified"** on screen. Dropping these would
  strip out most of the report's content — smoke colour is useful and no sensor observes it
  — but presenting them as findings is exactly the hallucination risk Table 3.20 names.
- **Supported** → released plainly.

**Change to make.** Replace the sentence above with:

> The check is carried out twice, and the two serve different purposes. At **release time**
> it is a control: every claim is graded against the logged evidence before the report
> reaches a responder, contradicted claims are withheld and unsupported claims are marked.
> During **analysis** the same grading is recomputed over the stored reports to produce the
> grounding accuracy and hallucination rate, which are properties of the model rather than
> of any one incident.

Two consequences worth stating with the results:

1. **Grounding accuracy is now reported per incident as well as in aggregate.** Every
   stored report carries its own claim count, supported count and the two rates.
2. **The hallucination rate measured in analysis is the rate *before* filtering.** The rate
   a responder is exposed to is lower, because contradicted claims were removed. Report
   both and say which is which — conflating them would credit the model for a control the
   system provides.

**A smaller gap, worth closing separately.** Algorithm 2 calls the fuel classifier only
when the gas level is above normal — a rule that exists because the sensors lag the camera.
Chapter 3 never states that lag anywhere, so the rule currently appears in the thesis with
no stated justification. Two options: assert the figure where the tier-3 upgrade is
explained in §3.2.5.2, or measure it. The stamps needed are already recorded on every
incident (`detected_at` against `classified_at`, and `durations.fireToClassifiedS` in the
incident report), so it could be a reported result rather than a number carried over from
the build notes.

**Section 3.2.5.3 describes one prompt. There are now four.** It currently documents the VLM
returning three fields (`detected`, `type`, `description`, Table 3.10), which remains correct
for the verification stage and nothing else. The others are undocumented, and two of them
carry results the thesis reports:

| Prompt | Endpoint | Used by | Documented? |
|---|---|---|---|
| `FIRE_PROMPT` | `/describe-image/` | the live alarm (Algorithm 3) | §3.2.5.3, Table 3.10 |
| `DETAILED_PROMPT` | `/describe-image-detailed/` | **the whole ablation study**, and the live fuel classifier | nowhere |
| `SCENE_PROMPT` | `/describe-scene/` | the situation report (RO3.1) | nowhere |
| `SENSOR_WARNING_PROMPT` | `/warn-from-sensors/` | **tier 1a's written warning** | nowhere |

Two of those gaps matter beyond tidiness.

`DETAILED_PROMPT` returns the eleven channels the fusion model consumes, so every ablation
figure in Chapter 5 depends on it — yet §3.2.4 and §3.2.5.2 describe the vision-language
layer purely in terms of the three-field verification answer. It also asks for **observables
rather than a verdict**, on purpose: naming the fuel directly would hand the fusion model
its own job and make combination 3 indistinguishable from combination 6. That is a design
decision the ablation rests on and it should be in the text.

`SENSOR_WARNING_PROMPT` produces the warning Table 3.6 and §3.2.3 describe as "a short
written warning ... generated from the readings". §3.2.3 says the warning exists; nothing
says a language model writes it, or that it is explicitly forbidden to mention fire or to
tell anyone to evacuate.

Give the report stage and the detailed stage a short table each, on the model of Table 3.10.

---

## 16. A detection setting now decides what counts as a fire — and the trials must say which they used

**Built this session, and it has methodological consequences that need stating before any
trial is run.**

The dashboard has a visible switch with two settings. The mobile app used to have its own,
independent switch for the escape-route layout; that switch and the industrial drawing behind
it have since been removed (§17), so only the dashboard setting remains.

| Setting | What alarms |
|---|---|
| **Industrial** (default) | Only unintended fire. A candle, lighter, match, cigarette, pilot light, gas burner or welding torch is a controlled flame in normal use and does **not** alarm. |
| **Home demo** | Any genuine sustained flame, however small and however deliberate — a candle or a lighter alarms. |

The two prompts share one base and differ in exactly one clause, so the nuisance guard and
the JSON contract are provably identical between them. `vlm-service/test_prompts.py` pins
that: without it, a measured difference between settings could be a difference between two
prompts rather than between two definitions of fire.

### What this means for Chapter 5, and it is not small

**Every detection result now belongs to a setting, and the thesis must say which.**

The controlled fire trials (§3.3.5) burn small quantities in a containment tray inside a
home. Under the industrial definition a small deliberate tray fire may read as a controlled
flame and not alarm at all. **Those trials therefore have to run in the home setting** — and
that means:

> The time-to-detection and detection-rate results in §3.4.3 and §3.4.5 are measured under
> the home definition of fire. They characterise the pipeline, not the industrial
> configuration, because the industrial definition deliberately ignores the small controlled
> flames that a domestic trial can safely produce.

The nuisance results (§3.3.6, §3.4.4) are the mirror image. N1's orange lamp and welding-spark
video are meant to test whether a welding arc causes a false alarm — which is an *industrial*
question, and the industrial setting is the one that explicitly names a welding torch as a
normal controlled flame. Running the nuisance battery in the home setting would measure the
wrong configuration.

**Decide and record, per §3.3.9's naming convention:**

- [ ] Which setting each trial family runs in. My reading: fire trials in home, nuisance
      trials in both (the comparison between settings is itself a result worth having).
- [ ] Add the setting to the run filename or the trial log, so a result can never be read
      without it. `<scenario_id>_<configuration>_<run>_...` currently has nowhere to put it.
- [ ] State in §3.4.10 that absolute detection figures are setting-dependent and are not
      transferable between the two.

Every incident record already stores `detectionMode`, so the setting travels with the data
even if a log entry is missed.

### One unresolved confound, flagged earlier and still open

The live alarm verifies through `FIRE_PROMPT` — which now has two settings — while the
ablation arms read `DETAILED_PROMPT`, which has none. So "combination 6" in the ablation is
not the deployed full system, and adding the setting made them diverge further. Whichever
path H1 is measured through determines which artefact the result describes. This needs a
sentence in Chapter 4 either way.

## 17. The mobile app picks its floor plan from the data, and the alert is now Android's own

**Changed in the app after the chapters were written.** Four decisions there touch what the
thesis can say.

**The layout switch is gone; the drawing follows the data.** The app had a switch choosing
between the home and the industrial drawing, set on the phone and read by nothing else. That
was the defect: `alert-service` stamps every route with the site it was generated for
(`routing.py`), and nothing reconciled that stamp with what the phone had been set to, so a
handset could be showing one building while holding a route computed for another. The switch
has been removed and the plan is now selected from the route's own `siteKey`, with the
backend's declared site as the fallback.

**Both drawings are kept, so both sites still work.** `SITE_KEY=home` and
`SITE_KEY=industrial` each run end to end, and nothing has to be changed on the phone to
follow the backend from one to the other. Nothing in the thesis needs to narrow to a single
facility, and §4's per-site hazard radius stands as written.

What is worth one sentence in Chapter 4 is the safety rule underneath it: a route is drawn
only on the plan for its own site, and a site this build has no drawing for makes **both the
route and the floor plan** unavailable, with a line on screen saying why. Withholding only the
route would still put one specific building in front of the reader, with a room highlighted and
their own position marked on it, for a site the app has just admitted it cannot identify. The two plans are at different scales — 25 px/m
for the home, 10 px/m for the hall — so the same coordinates land 2.5 times further into one
building than the other, and a guessed plan would place a confident path through the wrong
walls rather than merely an inaccurate one. `test/route_test.dart` checks every drawing
against its site file, so a site added on this side without artwork on the other fails a test
instead of a trial.

**The fire alert is a real Android notification, presented by Android.** The app also held a
simulated lock screen — a drawn clock and a drawn notification card — reachable from a button
on the dashboard. It has been deleted, and a confirmed fire now carries a full-screen intent
so a locked handset shows the alarm itself. This matters for **RO3.4**: Presentation B must be
the notification the system actually delivers, and a participant shown a mock-up of a
notification would have been rating a picture of the system.

> Add to §3.3.8, in the description of what participants are shown: the fire alert is
> delivered to the handset by Firebase Cloud Messaging and presented by Android on the fire
> channel, full screen on a locked device. No part of the alert presentation is simulated by
> the application.

**One limit worth stating with it.** When the app is backgrounded or terminated, Android draws
the alert from the message's own notification block, which has no field for a full-screen
intent; the takeover therefore applies while the app is running, and a background alert
arrives as a heads-up on the lock screen. The alternative — sending fire pushes as data only
so the app always builds the notification — would put the alarm behind the app's own code
starting first, and was rejected for that reason. §3.4.6's delivery measurement is unaffected:
all three acknowledgement paths are unchanged.

**The backend address is fixed at build time.** The in-app server override behind a long-press
on the dashboard title is gone, because a value typed in earlier outranked the compiled one
and nothing on screen said so. Per §3.3.9's naming convention, the address an APK was built
with is now a property of that artefact and should be recorded with the trial log.

---

## 18. The ablation study has one flicker implementation

**Small, and it removes a risk rather than adding one.** `flame_flicker_hz` was measured twice:
in Python from recorded frames, and in the browser at 16 Hz for the ablation page's live
comparison tab. That tab has been removed — nothing on a live feed carries a ground-truth
label, so it could never produce a number for Chapter 5 — and the browser implementation went
with it.

Nothing in the chapters needs changing: flicker appears only in the literature review
(§2), never as a claim about the built system. Worth knowing when Chapter 4 describes the
channel, though, because the risk it removes is real — two implementations with different
windows or a different peak test would have made the ablation compare the measurement rather
than the system.

One thing to note while writing §3.2.5: the **live dashboard never measured flicker at all**.
`escalation.js` posts no `flicker_hz` to the classifier, so the live fuel verdict uses the
quiet default for that channel while the ablation arms measure it from frames. State this
where the fuel classifier's inputs are listed.

---

## 19. §3.3.7 and §3.4.8 — the route evidence is now equal across both sites

**Status: the code and the site files have changed. Chapter 3 needs the numbers below.**

**What was wrong.** The two site profiles were not equally evidenced, and two measures
Chapter 3 promises could never produce a number.

- The home profile had a written-down answer for all 8 of its zones. The industrial
  profile had 3 of 7, so a wrong route in `cutting-floor`, `sewing-a`, `warehouse` or
  `finishing` would not have been caught while route validity still read 100 per cent.
- No case in either file carried `lengthM`, so the optimality gap of §3.4.8 — generated
  length against the manual best — had no denominator and silently reported nothing.
- No case expected a refuge, so the correct-refusal measure could only ever be zero. The
  refusal behaviour RO2.2 requires was implemented and never exercised.
- The industrial hazard radius of 6.0 m carried no written justification, while the home's
  2.0 m did.

**What was done.** Every expected answer was derived by exhaustive enumeration of all
simple paths — deliberately not by the router, which uses Dijkstra — and then cross-checked
against the router. Both agree on all 15 zones, which is what makes the ground truth a
check rather than a copy.

| | Home | Industrial |
|---|---|---|
| Zones | 8 | 7 |
| Exits | 2 | 4 |
| Baseline cases, all with a hand-derived length | 8 of 8 | 7 of 7 |
| Blocked-exit scenarios | 8 | 9 |
| Of those, expecting a refuge | 3 | 2 |
| **Total combinations** | **16** | **16** |

A new `routeScenarios` block in each site file holds fire location combined with one or
more blocked exits, which the zone-keyed ground truth cannot express because it is keyed by
zone alone. `sites.py` now refuses to load a site whose baseline case declares no length,
or whose scenario names an unknown zone or exit, so this evidence cannot quietly rot.

**One measurement artefact was removed at the same time.** `to_record()` rounded `lengthM`
to one decimal, which is right for a phone showing a distance to walk but put the stored
length on a coarser grid than the ground truth. The optimality gap then read up to 0.4 per
cent against routes that were in fact optimal. The record now keeps two decimals and the
wire still carries one, and the measured gap is exactly 0.00 per cent on all 15 zones.

**Change to make.** §3.3.7 currently says "At least eight combinations of fire location and
blocked exit are tested" while Ch. 1 RO2.3 says "at least fifteen" — the inconsistency
already noted in section 6 above. Both are now satisfied and the sentence can state the
real figure:

> Route generation is tested on 32 combinations of fire location and blocked exit, 16 on
> each site: 15 baseline cases covering every zone of both facilities, and 17 scenarios in
> which one or more exits are blocked, of which 5 expect a refuge instruction because no
> exit remains reachable.

Report the optimality gap as 0.00 per cent across all 15 baseline zones, and say that the
ground truth was derived by exhaustive path enumeration independent of the shortest-path
implementation under test. That sentence is worth more to an examiner than the figure.

**Still open, and not closed by this change.** The home graph is a tree — 17 nodes and 16
edges — so there is exactly one path from any room to any exit and the search never
chooses between alternatives. The industrial graph has two independent cycles and does
choose. That asymmetry is a property of the buildings, not of the code, and Chapter 5
should say which site each route claim rests on. The default site is still `home` while the
stated scope is industrial.

---

## 20. Seven faults fixed in the alarm path, and what Chapter 4 must now say

**Status: the code has changed. Most of these bring the artefact back to what Chapter 3
already describes, so they remove thesis edits rather than creating them.** The two
exceptions are marked. The full audit is in `AUDIT_FINDINGS.md` at the repository root.

| # | What was wrong | Effect on the thesis |
|---|---|---|
| 1 | `sceneEvidence()` was declared inside `reportFire` and called from `detectOnce`, so every call raised a scope error and the camera could never raise an alarm | None. Algorithm 2 now runs as §3.2.5.2 describes |
| 2 | Algorithm 2's safety latch was absent, so one verification timeout with normal gas cleared a standing fire alarm | None. §3.2.5.2 and the README already describe the correct behaviour |
| 3 | The alarm was posted once on the rising edge and never again, so the 30 s watchdog resolved a fire that was still burning | **Chapter 4 must describe the keep-alive** |
| 4 | Of the two posts per fire, the one carrying the description always lost the race, so no live incident ever stored a situation report | None. RO3.1 now produces what it claims |
| 5 | `/api/test-alert` passed no scene, so demo alerts carried no report at all | None |
| 6 | Incidents were seeded with a synthetic muster of 42 present of 45, printed on the officer's report as though measured | **§3.4.8's head-count comparison changes — see below** |
| 7 | The results export read `data_source` while the health payload builds `trainedOn`, so the download returned an error | None |

**Item 3 — the keep-alive, for Chapter 4.** `alert-service` resolves an incident that has
had no fire event for `CLEAR_AFTER_SECONDS` (30 s), which §3.2.5.2 states as "no new event
for 30 s". That rule assumes something keeps reporting. The dashboard now re-posts the open
alarm every 10 s while the alarm stands, giving three chances to land inside the server's
window so one dropped request cannot resolve a live incident. The refresh carries no scene,
so the vision language model is still called once per alarm and the cost per incident in
§3.4.6 is unchanged.

**Item 6 — the muster figures, for §3.4.8.** §3.4.8 compares the camera head-count against
the occupant check-out count. The stored muster columns are no longer seeded with anything:
when the human detector never supplied a count, the API returns `source: "unknown"` with
both figures null and the officer's report prints "No head-count recorded". Any table in
Chapter 5 that would have shown 42 of 45 for an incident the detector never saw must show
that the count was not recorded instead. This is the honest version of the same measure —
an invented occupancy figure on a safety report cannot be told apart from a measured one,
and three people unaccounted for is exactly the number that decides whether anyone goes
back inside.

The same invented constants still sit in the mobile app's own fixtures
(`lib/data/api/api_fire_repository.dart`, `lib/data/mock/mock_data.dart`). They are
unreachable in the interface, because no widget renders the muster roll, so they are listed
as extra code in `AUDIT_FINDINGS.md` rather than fixed here.

---

## 21. The five findings closed without a code change

The audit in `AUDIT_FINDINGS.md` raised fourteen critical problems. Seven were fixed in the
alarm path (section 20), two were the ablation and the route evidence (sections 13 and 19),
and the remaining five were closed **without changing any code**, because none of them is a
software defect. They are recorded here because each still leaves something to write.

| # | Finding | What is left to do, and where |
|---|---|---|
| 8 | The sensor node measures nothing | Wire the four modules, or keep the mock and state it. Already a declared limitation |
| 9 | No bill of materials exists | Write it into Chapter 4. Promised three times, never produced |
| 10 | The detector is 0.4 % under its mAP target | Finish the interrupted training run. See below |
| 11 | No real fire trial data | DS4 to DS8. Already under "Outstanding" below |
| 12 | A Wi-Fi password in the ESP32-CAM history | Keep that repository private, or change the password |

**Item 8 does not weaken the sensor claims as much as it first appears.** The mock state is
declared all the way through: a `mock: true` flag travels with every reading to the
dashboard, so no number is presented as measured when it is not. Chapter 3 already routes
the sensor evidence through the CFAST synthetic set for this reason. What Chapter 4 must not
do is describe the node as measuring anything.

**Item 10 is worth restating accurately, because the first reading of it was too harsh.**
The recorded figure is mAP@0.5 = 0.84635 against a target of 0.85. The checkpoint shows why:
the run was configured for 300 epochs with a patience of 50 and **stopped at 27**, so
neither limit was reached and the run was interrupted rather than completed. Epoch 27 was
the best of the 27 and the curve was still rising. All 109 training arguments are stored
inside `best.pt`, so the recipe survives; what is missing from the repository is the dataset
definition, which points at a Google Drive path, and the Colab notebook.

So two sentences for Chapter 4, and one decision. The sentences: report the measured figure
with the conditions it was measured under, and say that training was stopped early. The
decision: either finish the run and report the figure it reaches, or keep 0.84635 and change
RO1.2's target to match what the artefact achieves. Reporting 0.85 as met is the one option
that is not available.

Recall is 0.777 and no target is set for it. For fire detection that is the figure that
matters most, so Chapter 5 should report it prominently rather than leaving it beside the
mean.

**Item 12 has a condition attached.** The password sits in the history of `esp_32_cam_code`,
which is private, as is `esp_32_sensor_network_code`. The public repositories are the web app
and the mobile app, and neither holds a committed secret. But `esp_32_cam_code/README.md`
says "the repository stays safe to publish", which is not true of its history. Correct that
sentence or change the password before that repository is ever published.

---

## Outstanding, and not an edit to anything

Everything above is a correction to text that already exists. These are different — they are
things the thesis needs that no amount of editing produces, listed here so the two kinds do
not get confused with each other.

**Chapters 4 and 5 are not written.** Only `chapter_1_and_2.docx` and `chapter_3.docx` exist.
§3.6 already promises what Chapter 4 must contain — the tools and technologies, the
architecture as built, the implementation steps for hardware, models, backend, dashboard and
mobile application, and the evaluation protocol. Chapter 5 is where every analysis in §3.4
is reported.

**Five of the eight datasets have not been collected.** DS1 (HomeFire), DS2 (CrowdHuman) and
DS3 (the CFAST synthetic set) are done — the trained weights and `fusion_model.joblib` exist,
with checksums in `fire-classification-service/model/PROVENANCE.md`. The other five are
primary data and exist only once the system is run:

| | | |
|---|---|---|
| DS4 | Sensor readings during the trials | not collected |
| DS5 | Controlled fire trial recordings | not collected — §3.3.5 wants ≥10 repetitions per scenario |
| DS6 | Nuisance scenario recordings | not collected — this is H1 |
| DS7 | Occupancy, route and check-out records | not collected |
| DS8 | Expert evaluation responses | not collected — see §14 |

Without DS4–DS8 there is no §3.4 analysis at all: no time to detection, no false alarm
comparison, no Friedman test, no route validity rate, no head-count comparison, no Likert
results.

**The system has never been run end to end.** Everything is verified by automated tests and
in-process HTTP. The Gemini prompts have never met a real image, FCM has never delivered a
real push, and the home floor plan has never been rendered on a screen. One session with
`docker compose up --build` and a phone answers all three, and should happen before the
trials rather than during them.

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
