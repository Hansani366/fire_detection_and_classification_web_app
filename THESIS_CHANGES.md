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

## 13. Ch. 1 RO1.4 and §3.2.4 — four configurations described, six built

**As written**, in four places: RO1.4 compares "the vision only, sensor only, sensor and
vision fusion, and full configuration with vision language model verification"; §3.2.4 says
switching a layer off "makes it possible to compare the four configurations"; §3.3.5 says
each scenario is observed by "all four system configurations"; and §3.3.6 repeats it for the
nuisance runs.

**What was built** — `ablation-service/constants.py`:

| | Combination |
|---|---|
| 1 | sensors only |
| 2 | YOLO only |
| 3 | VLM only |
| 4 | sensors + YOLO |
| 5 | VLM + YOLO |
| 6 | sensors + YOLO + VLM |

Six, not four — a superset rather than a shortfall, so the artefact does more than the
thesis claims, which is the better direction to be wrong in.

**But "vision only" is ambiguous, and that part is not cosmetic.** It could mean combination
2 (the detector alone) or combination 5 (detector plus vision-language verification, still
no sensors). Both hypotheses are stated against it:

> H1: The full system ... produces a lower false alarm rate on the nuisance test set than
> **the vision only configuration**.
>
> H2: The sensor first trigger produces a shorter time to detection than **the vision only
> configuration** for smouldering fires.

Read against combination 2, H1 measures the sensors *and* the verification layer together.
Read against combination 5, it isolates the sensors alone. Those are different hypotheses
with different expected effects, and §3.4.4 commits to a McNemar test on paired runs — a
test whose result cannot be interpreted until the pairing is named.

**Change to make.** Say six, name them, and pin each hypothesis to numbered combinations:

> The prototype supports six configurations, listed in Table X. This study reports
> combination 1 (sensors only), combination 2 (detector only), combination 4 (sensors and
> detector fused) and combination 6 (the full system). H1 compares combination 6 against
> combination 5; H2 compares combination 4 against combination 2.

Substitute whichever pairing you actually intend — the point is that a number appears rather
than a phrase with two readings. `GET /api/ablation/config` renders each rule from the
constants the code executes, so Chapter 4's table can be generated from the running system
instead of transcribed.

---

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

## 17. The mobile app draws one facility, and the alert is now Android's own

**Changed in the app after the chapters were written.** Four decisions there touch what the
thesis can say.

**One layout, not two.** The app carried a drawing of the industrial hall and a switch to
choose between it and the home, and both are gone. No trial could run in those premises —
§5 of the README records that they were never accessible — so the second drawing was artwork
for a building nothing could be measured in. The consequence to state: running the backend
with `SITE_KEY=industrial` now makes the phone refuse to draw the route and say why, so
**every route demonstration and every evacuation run uses the home site**. The refusal itself
is unchanged and still tested; it is now driven by the route's own site key rather than by a
phone setting.

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
