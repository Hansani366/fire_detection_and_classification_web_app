# Code audit against the thesis

Date: 26 September 2026

This document lives in `fire_detection_and_classification_web_app` because that is the repo
the findings mostly concern, and because the root folder is not under version control. It
records an audit of the four code repositories against the objectives, the
architecture and the algorithms stated in `chapter_1_and_2.docx` and `chapter_3.docx`. The
aim was to answer three questions: what is correct, what is missing or wrong, and what code
exists that the thesis does not need.

## Scope

| Repository | Role |
|---|---|
| `fire_detection_and_classification_web_app` | Backend services and the safety officer's dashboard |
| `fire_notification_and_evacuation_mobile_app` | Flutter application for occupants |
| `esp_32_cam_code` | ESP32-CAM firmware |
| `esp_32_sensor_network_code` | ESP32 multi-sensor node firmware |

`firewatch-ngrok-files` and `firewatch-private-files` hold configuration and secrets. They
are not repositories and were not audited, except where a value in them explains the
behaviour of a repository.

## Method

Each of the eleven objectives (RO1.1 to RO3.4), the four algorithms and the five
architecture layers was traced through the code by a separate reviewer. A complete
file-by-file inventory was taken of all four repositories, and a separate pass looked for
code that no objective needs. Every blocking finding in the next section was then opened
and confirmed by hand.

## How to read the findings

Each finding falls in exactly one of four groups.

| Group | Meaning |
|---|---|
| Correct | Present, matches the thesis, keep it |
| Gap | The thesis needs it, the code does not deliver it, or delivers part of it |
| Mismatch | Code and thesis both exist but disagree |
| Extra | Code that exists, which no objective or scope item needs |

## Summary

583 findings after removing duplicates.

| Group | Web app | Mobile app | Sensor node | ESP32-CAM | Across repos | Total |
|---|---|---|---|---|---|---|
| Correct | 152 | 28 | 13 | 9 | 19 | 221 |
| Gap | 117 | 7 | 11 | 4 | 2 | 141 |
| Mismatch | 97 | 7 | 6 | 4 | 3 | 117 |
| Extra | 62 | 21 | 11 | 8 | 2 | 104 |

The routing module, the arbitration table, the verification layer, the grounding check and
the two-count check-out design are the strongest parts of the work. The weakest are the
sensor node, which measures nothing, and the evidence base, which is still simulated.

## The fourteen critical problems

The audit returned twenty-one blocking findings, which reduce to fourteen distinct
problems. They are listed here in the order they should be addressed. Items 1 to 7 and
items 13 to 14 have been fixed; the status column records this. Items 8 to 12 are open and
are mostly collection and documentation work rather than repairs.

| # | Problem | Repository | Status |
|---|---|---|---|
| 1 | The camera can never raise the alarm | Web app | Fixed |
| 2 | A verification outage switches off an active alarm | Web app | Fixed |
| 3 | A burning fire is declared over after 30 seconds | Web app | Fixed |
| 4 | The written situation report is never saved | Web app | Fixed |
| 5 | Demo alerts carry no situation report | Web app | Fixed |
| 6 | The officer's report shows invented occupancy numbers | Web app | Fixed |
| 7 | The results download fails | Web app | Fixed |
| 8 | The sensor node measures nothing | Sensor node | Open |
| 9 | No bill of materials exists | Sensor node, ESP32-CAM | Open |
| 10 | The detection model misses its target and cannot be rebuilt | Web app | Open |
| 11 | No real fire trial data has been collected | Web app | Open |
| 12 | A real Wi-Fi password remains in the saved history | ESP32-CAM | Open |
| 13 | Six ablation configurations were built, four are described | Web app | Fixed |
| 14 | The home and industrial profiles are not equally evidenced | Web app | Fixed |

### 13. Six ablation configurations built, four described — Fixed

The ablation now runs five configurations instead of six. The removed arm, "VLM only",
described something the architecture cannot run: Algorithm 3 invokes the vision language
model only on a YOLO box, and the arm's own justification claimed a fixed cadence "never on
the YOLO gate" while its data was generated YOLO-gated throughout. Its confidence score
survives as a feature, because the YOLO + VLM arm scores against it.

The five are numbered so each comparison differs by exactly one component, and the full
system and its comparison arm are now named constants rather than literals — the hardcoded
`6` in the McNemar test was how renumbering would have silently pointed the comparison at
the wrong column.

### 14. The home and industrial profiles are not equally evidenced — Fixed

Both sites now carry 16 combinations of fire location and blocked exit: 15 baseline cases
covering every zone of both buildings, and 17 blocked-exit scenarios, 5 of which expect a
refuge. Every expected answer was derived by exhaustive enumeration of all simple paths,
deliberately not by the router under test, then cross-checked against it; the two agree on
all 15 zones.

Two measures that could never produce a number now do. Every baseline case carries a
hand-derived length, so the optimality gap has a denominator — it reads 0.00 per cent
across all 15 zones. And the refusal cases mean the correct-refusal measure can register a
success rather than only ever reading zero.

One measurement artefact was removed at the same time: the stored route length was rounded
to one decimal, which is right for a phone but put it on a coarser grid than the ground
truth, producing a gap of up to 0.4 per cent against routes that were in fact optimal.

`sites.py` now refuses to load a site whose baseline case declares no length, or whose
scenario names an unknown zone or exit, so this evidence cannot quietly rot.

### 1. The camera can never raise the alarm — Fixed

The dashboard collects a short summary of each frame before it reports a fire. That summary
function was declared inside one function and called from another, so every call raised an
error and stopped the detection tick at that line. The instruction that raises the alarm is
the next line, so it never ran.

Only the gas sensors could trigger anything. The camera path was silent whatever it saw.
The same fault also stopped the written report and the head-count from reaching the server,
so it affected RO1.3, RO3.1 and RO2.1 together.

### 2. A verification outage switches off an active alarm — Fixed

The decision function started from a blank slate on every evaluation and never read the
previous state. Algorithm 2 requires a latch: when verification is unavailable, the system
must hold the higher of the old and new states. Without it, one timeout with gas readings
normal returned "clear" and resolved the incident. `README.md` already described the correct
behaviour, so the document promised something the code did not do.

### 3. A burning fire is declared over after 30 seconds — Fixed

The dashboard reported a fire once, when it started, and never again. The server resolves an
incident after thirty seconds with no fresh event, which is correct only if something keeps
reporting. Nothing did, so a real fire was auto-resolved half a minute in and the phones
were told it was over.

### 4. The written situation report is never saved — Fixed

Two messages were sent for each confirmed fire. The one without the description was sent
first and created the incident; the one carrying the description arrived afterwards and was
ignored, because the incident already existed.

### 5. Demo alerts carry no situation report — Fixed

The test alert endpoint passed no scene, and the report is only written when a scene is
present. This is the path most likely to be used in a demonstration.

### 6. The officer's report shows invented occupancy numbers — Fixed

When the head-count was unknown, stored placeholder constants of 42 present out of 45 were
written into every new incident and printed on the officer's report as though measured.

### 7. The results download fails — Fixed

The export route asked for a field by one name while the health payload provided it under
another, so the download returned an error instead of the provenance file.

### What was changed for items 1 to 7

All seven fixes are in `fire_detection_and_classification_web_app`. No other repository was
touched. Eight files changed, 210 lines added and 53 removed.

| File | Items | Change |
|---|---|---|
| `frontend/static/index.html` | 1 | `sceneEvidence()` moved from inside `reportFire` to the top level, beside `captureBlob` |
| `frontend/static/js/escalation.js` | 2, 3 | Added Algorithm 2's safety latch; added a ten-second keep-alive for a standing alarm |
| `alert-service/intake.py` | 4 | A repeat event carrying a scene now fills in a report the incident is still missing |
| `alert-service/app.py` | 5 | `/api/test-alert` now sends a scene and matching detector evidence |
| `alert-service/db.py` | 6 | Stopped seeding the synthetic 42-of-45 muster; `bump_muster` now counts from zero |
| `alert-service/serializers.py` | 6 | `muster_json` reports "unknown" instead of inventing figures |
| `frontend/static/reports.html` | 6 | Renders "No head-count recorded" rather than a fabricated count |
| `ablation-service/runs.py` | 7 | Reads `trainedOn`, which the health payload actually provides |

Two decisions inside these fixes are worth knowing when Chapter 4 is written.

- The keep-alive interval is ten seconds against the server's thirty. That gives three
  chances to land inside the window, so one dropped request cannot resolve a live incident.
  A keep-alive carries no scene, so the vision-language model is still called once per
  alarm and the reported cost per incident does not change.
- The latch releases on a verification result that was actually received, and holds only
  while verification is unavailable. A rejection still clears the alarm, so the latch
  removes the outage failure without making the alarm impossible to stand down.

### How the fixes were checked

There is no Python test runner installed in this environment, so the existing `pytest`
suites could not be run. Each fix was instead driven directly and the result recorded.

| Item | Check |
|---|---|
| 1 | The function is now declared at the top level and all three call sites resolve to it; the page's script parses |
| 2 | Drove the real `escalation.js`: a confirmed fire with normal gas survives a verification outage, sends no clear event, and still clears on a rejection that was received |
| 3 | Same harness: the rising edge posts once, an immediate repeat does not, and a keep-alive is posted once the interval passes |
| 4 | Drove the real `intake.handle_confirmed_fire`: the late scene post fills in the report, opens no duplicate, and neither a keep-alive nor a later scene overwrites it |
| 5 | Drove the real report builder with the new demo scene: five claims, four supported, material honestly unsupported because no fuel verdict exists yet, nothing contradicted |
| 6 | Drove the real `muster_json`: unknown reports as unknown, a genuine check-in count survives, the vision path is unchanged, and a lost camera still does not read as an empty room |
| 7 | The strict lookup is gone and the key it now reads is the one the health payload builds |

One consequence to be aware of: the phone receives `null` for both muster figures where it
used to receive numbers. Nothing breaks, because the app never displays the muster roll and
its parser turns a null into zero. The same invented constants still sit in the app's own
fixtures at `lib/data/api/api_fire_repository.dart` and `lib/data/mock/mock_data.dart`; they
are unreachable in the interface and are listed under extra code rather than fixed here.

### 8 to 14 — Open

These remain open and are described in the findings below. Items 8, 9 and 11 are collection
and documentation work rather than repairs. Item 12 should be closed by changing the Wi-Fi
password, which takes minutes.

## Gaps — the thesis needs it, the code does not deliver it

A gap is something an objective, an algorithm or a stated deliverable requires, which the code does not provide or provides only in part.


### Web app (117)

- **Zone level seeded 'normal', so an all-stale zone reads normal** — ALG1, blocking  
  Algorithm 1 requires "if now - last[n] > 15 s: L[n] <- unknown // stale, never 'normal'". The server honours this per node (main.py:173-176). The zone step in escalation.js does not: escalation.js:81 seeds the accumulator as var worst = 'normal', and escalation.js:85 only ever raises it (RANK[lvl] > RANK[worst], with RANK.unknown = 0 at escalation.js:46). Since RANK.unknown (0) is below RANK.normal (1), a zone in whi  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:81`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:84`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:85`
- **No backend service holds the decision layer; it lives only in the browser** — ARCH, blocking  
  Table 3.7's decision and application layer names three components: "The escalation logic, which applies the three-poll confirmation and manages the states in Table 3.6; the alert service ...; and the route generator". Two of the three are server-side (alert-service, routing.py). The escalation logic is not: STRIKES=3, RANK, the four-tier ladder, the zone-level worst-of aggregation and the decision to call the classif  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:33-61`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:106-120`, `fire_detection_and_classification_web_app/alert-service/intake.py:1-5`
- **No training configuration in any repo; the model is a black-box binary** — RO1.2, blocking  
  RO1.2's deliverable is "a trained model with reproducible training configuration" (chapter_1_and_2.txt:50). Nothing in any of the four repos trains anything. Searches run across /Users/chanakabandara/Desktop/Fire_Research_All_Codes (excluding node_modules and .git): find -iname '*train*' -o -iname '*.ipynb' -o -iname 'data.yaml' -o -iname '*dataset*' returned ZERO files; grep -rn 'model.train' --include=*.py returned  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:18`, `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (embedded train_args: data, project, name)`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:50`
- **Every Escalation.onVision call throws, so a YOLO box can never raise the alarm** — RO1.2, blocking  
  sceneEvidence() is declared at index.html:1620, nested INSIDE reportFire (which opens at 1612 and closes at 1664, both at column 0 while sceneEvidence is indented two spaces). It is called from runDetection (opens 1693) at three sites: 1779 (VLM confirmed), 1797 (VLM error path) and 1819 (no box, hold expired). All three are outside its scope, so each throws ReferenceError: sceneEvidence is not defined. `grep -rn "sc  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612-1664`, `fire_detection_and_classification_web_app/frontend/static/index.html:1620-1641`, `fire_detection_and_classification_web_app/frontend/static/index.html:1779`
- **A failed verification does clear an active alarm - the latch rule is absent** — RO1.3 / Alg.2, blocking  
  Algorithm 2 has an explicit safety latch: 'if S is FIRE CONFIRMED or GAS DANGER and V = unavailable: S' <- the higher of S and S'', restated in prose at chapter_3.txt:286 and again at :811. Nothing in escalation.js implements it. decide() at escalation.js:142-157 is memoryless - the previous state is read at line 162 only to decide whether to fire onChange. So the sequence is: box + VLM confirms with sensors normal -  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:142`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:168`, `fire_detection_and_classification_web_app/alert-service/intake.py:354`
- **A burning fire is auto-cleared after 30 s because no repeat fire event is ever sent** — RO1.3 / Alg.2, blocking  
  Algorithm 2 re-runs per frame and refreshes the open incident each time; the 30 s rule then means 'no new event'. In code, sendFire is called once only, on the rising edge: evaluate() guards it with 'if (S.alarm && !S.reported)' and sets S.reported = true (escalation.js:167). While the fire keeps burning S.alarm stays true, so S.reported is never reset and no second /api/events/fire is posted. intake.touch_incident -  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:167`, `fire_detection_and_classification_web_app/alert-service/db.py:475`, `fire_detection_and_classification_web_app/alert-service/intake.py:368`
- **No ratchet: a VLM outage clears an active fire alarm when gas is normal** — RO1.3 / Algorithm 2 (failed verification never clears an active alarm), blocking  
  Algorithm 2 says: `if S is FIRE CONFIRMED or GAS DANGER and V = unavailable: S' <- the higher of S and S'`. `decide()` in escalation.js:142-157 is stateless - it never reads the previous state `S`. Trace: gas level normal, YOLO box present, VLM confirmed -> tier 'fire', alarm raised, incident opened. Next frame the VLM times out; index.html:1795-1797 pushes `{yoloHit:true, vlmConfirmed:false, vlmAvailable:false}`. `d  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:142`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:148`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:168`
- **sceneEvidence() is out of scope; vision never reaches the arbitration** — RO1.3 / Algorithm 3 + Algorithm 2, blocking  
  BLOCKING. `sceneEvidence()` is declared INSIDE `async function reportFire(vlm)` (opens index.html:1612, sceneEvidence at :1620, its closing brace at :1641, reportFire's closing brace at column 0 at :1664). `detectOnce()` calls `sceneEvidence()` three times from outside that function: :1779 (VLM confirmed path), :1797 (VLM error path), :1819 (no-box path). A JS function declaration is scoped to the enclosing function,  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1620`, `fire_detection_and_classification_web_app/frontend/static/index.html:1641`
- **mAP is never computed anywhere in any repo** — RO1.4, blocking  
  RO1.4 names 'mean average precision' as a dependent variable and Ch.3 s3.4.3 spells out AP, mAP@0.5 and mAP@0.5:0.95 over IoU >= 0.5 box matches. No code computes AP, mAP, or IoU. I grepped all four repos for 'mAP', 'mean average precision', 'map@0.5', 'map50', 'map_50', 'iou' across *.py/*.html/*.js/*.md/*.yaml/*.json: the only hits are prose in THESIS_CHANGES.md:258 and unrelated uses of the word 'map'. The ablatio  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:214`, `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:45`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:258`
- **No real trial data: the entire ablation runs on CFAST simulation** — RO1.4, blocking  
  RO1.4's deliverable is an evaluation dataset from controlled fire scenarios. ablation-data/ contains only README.md - no experiment folders at all - so the recordings path has never had an input. Both vendored datasets are flagged synthetic:true (REPLAY_SETS) and the model manifest's data_source is ['cfast_v3'] with the warning 'Scores describe a synthetic generator, not real fire behaviour.' The repo's own THESIS_CH  
  Evidence: `fire_detection_and_classification_web_app/ablation-data/README.md:1`, `fire_detection_and_classification_web_app/ablation-service/runs.py:47`, `fire_detection_and_classification_web_app/fire-classification-service/model/manifest.json:6`
- **Export JSON route crashes: health payload has no data_source key** — RO1.4, blocking  
  runs.export_json reads health['data_source'], but the dict passed in is main._health_payload(), which builds 'trainedOn' instead (the classification service also returns 'trainedOn', main.py:183, never 'data_source'). GET /api/ablation/runs/{id}/export.json therefore raises KeyError: 'data_source' and returns 500. The page's 'Export JSON' button calls exactly that URL, so the citable provenance artefact - the 'full r  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/runs.py:317`, `fire_detection_and_classification_web_app/ablation-service/main.py:112`, `fire_detection_and_classification_web_app/fire-classification-service/main.py:183`
- **mAP is never computed, and no box-level ground truth exists to compute it from** — RO1.4, blocking  
  RO1.4 names four metrics: 'precision, recall, mean average precision and time to detection' (chapter_1_and_2.txt:52), and chapter_3.txt:672 spells out AP, mAP@0.5 and mAP@0.5:0.95. Neither mAP variant is computed anywhere in the ablation. I searched the whole web-app repo with grep -rni 'map@|mean average precision|map_50|map50' over *.py, *.html, *.js and *.md: the only hit is THESIS_CHANGES.md:258, prose about RO1.  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:52`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:672`, `fire_detection_and_classification_web_app/ablation-service/data/test_split.csv:1`
- **ablation-data holds only a README; zero real recordings have ever been scored** — RO1.4, blocking  
  RO1.4's first deliverable is 'a complete detection evaluation dataset' from the controlled fire trials (chapter_3.txt section 3.3.5). find ablation-data -type f returns exactly one file: ablation-data/README.md. .gitignore:17-18 ignores everything else and keeps the README so the bind mount has a directory. Every number the service can produce today therefore comes from CFAST simulation, which the code states plainly  
  Evidence: `fire_detection_and_classification_web_app/ablation-data/README.md:1`, `fire_detection_and_classification_web_app/.gitignore:17`, `fire_detection_and_classification_web_app/ablation-service/main.py:33`
- **Export JSON crashes on a missing key, so the citable artefact cannot be produced** — RO1.4, blocking  
  RO1.4's third deliverable is 'the full result set'. export_json reads health['data_source'] at runs.py:317, but _health_payload() (main.py:112-130) builds a dict with no data_source key - it has trainedOn instead (main.py:128) - and the upstream /api/classify/health it mirrors has no data_source either (fire-classification-service/main.py:163-186). GET /api/ablation/runs/{run_id}/export.json therefore raises KeyError  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/runs.py:317`, `fire_detection_and_classification_web_app/ablation-service/main.py:112`, `fire_detection_and_classification_web_app/ablation-service/main.py:128`
- **sceneEvidence is out of scope: the head-count never reaches alert-service at runtime** — RO2.1, blocking  
  sceneEvidence() is declared INSIDE async function reportFire (index.html:1612-1664; the nested declaration is at 1620-1641). runDetection starts at 1693 and calls sceneEvidence() at 1779, 1797 and 1819 - outside that scope, so every call throws ReferenceError. Because the throw happens while building the argument object, Escalation.onVision is never reached, so escalation.js:132 never assigns S.occupancy (and never s  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1620-1641`, `fire_detection_and_classification_web_app/frontend/static/index.html:1664`
- **Shipped person model records recall 0.742, thesis demands 0.90** — RO2.1, blocking  
  RO2.1 (chapter_1_and_2.txt:54) requires "a detection recall of at least 0.90 under the tested lighting conditions". I unzipped the shipped checkpoint human-detection-yolo-service/best.pt and decoded its pickled `train_metrics` dict: metrics/recall(B) = 0.74213, metrics/precision(B) = 0.87056, metrics/mAP50(B) = 0.83770, metrics/mAP50-95(B) = 0.53300. THESIS REQUIRES 0.90, CODE SHIPS 0.742 - a shortfall of 0.158. This  
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/best.pt (best/data.pkl, train_metrics: metrics/recall(B)=0.74213, precision 0.87056, mAP50 0.83770, mAP50-95 0.53300; train_results epoch list length 100, max recall 0.745 at epoch 80)`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:54`, `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:37`
- **Production never routes from the occupant's position, only from the fire zone** — RO2.2, blocking  
  Thesis §3.2.5.4: "A Dijkstra shortest path search is run from the position of the occupant." intake.py:103 calls `routing.route_for_zone(site, fire_zone_id=zone_id)` with no `occupant_zone_id`, so routing.py:312 falls back to the BURNING zone's anchor. One route is generated per incident and the same polyline goes to every handset (intake.py:205, 246 push the same `_route_for_push` block). RO2.1's occupant position i  
  Evidence: `fire_detection_and_classification_web_app/alert-service/intake.py:103`, `fire_detection_and_classification_web_app/alert-service/routing.py:312`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:133`
- **None of RO2.3's evidence has been collected and no push has ever been sent** — RO2.3, blocking  
  Table 3.12 names RO2.3's data as "Delivery logs, route outputs and check-out records" (chapter_3.txt:388). The repo's own THESIS_CHANGES.md records DS7 'Occupancy, route and check-out records | not collected' (line 626) and states plainly: "The system has never been run end to end ... FCM has never delivered a real push, and the home floor plan has never been rendered on a screen." So the delivery p50/p95, the route-  
  Evidence: `fire_detection_and_classification_web_app/THESIS_CHANGES.md:626`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:635`
- **Live dashboard never stores a situation report: the scene POST loses the race** — RO3.1, blocking  
  sendFire issues TWO posts to /api/events/fire. The one carrying the scene is inside the describeScene callback (escalation.js:225-234, post at l.226), so it only fires after the frame capture and the VLM round-trip return. The bare post without a scene runs synchronously at the end of the same function (escalation.js:238). The bare post therefore arrives first and creates the incident; the scene post then finds an ac  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:225`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:238`, `fire_detection_and_classification_web_app/alert-service/intake.py:185`
- **Demo alerts produce no situation report at all** — RO3.1, blocking  
  /api/test-alert calls intake.handle_confirmed_fire with no scene and no evidence argument (app.py:545-549 for the fire tier, l.537-543 for gas_danger). Since _attach_report returns early when scene is falsy (intake.py:68-69), every demo alert - the path most likely to be used in a viva demonstration - opens an incident with situation_report NULL. Combined with the finding above, there is currently no runnable path in  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:545`, `fire_detection_and_classification_web_app/alert-service/app.py:537`, `fire_detection_and_classification_web_app/alert-service/intake.py:68`
- **sceneEvidence() is out of scope at all three call sites, so no evidence is ever sent** — RO3.1, blocking  
  sceneEvidence() is declared inside reportFire() (index.html:1620, inside the function that opens at 1612 and closes at 1664 - verified by brace balance). It is called three times from detectOnce(), which begins after line 1712: lines 1779, 1797 and 1819. A function declaration is scoped to its enclosing function, so each call raises ReferenceError while the Escalation.onVision({...}) argument object is being built -   
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1620`, `fire_detection_and_classification_web_app/frontend/static/index.html:1779`
- **The scene-bearing fire post is always deduped away, so no report is attached** — RO3.1, blocking  
  escalation.js sendFire() fires two posts to /api/events/fire: the scene one only after describeScene()'s VLM round trip returns (l.224-236, l.270-283), and an unconditional one immediately afterwards (l.238-264). The immediate post arrives first and creates the incident with scene=None, so _attach_report returns at intake.py:68. Seconds later the scene post finds an active fire incident and takes the `elif active:` b  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:224`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:238`, `fire_detection_and_classification_web_app/alert-service/intake.py:68`
- **Wet chemical is never an agent; 4 of the 5 agents RO3.2 names are covered** — RO3.2, blocking  
  RO3.2 (ch1 line 65) requires coverage of 'water, foam, carbon dioxide, dry powder and wet chemical agents'. Across all three entries the only agent strings are Water, Foam (AFFF), CO2 and Dry powder (ABC). 'wet chemical' appears twice in the whole codebase and both are prose, never an agent: liquid_fuel['caution'] and app.py's modelLimits. Because the phone builds its lists with _agents(r['use'],'agent') / _agents(r[  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:52-61,73-81,84-88,99-107`, `fire_detection_and_classification_web_app/alert-service/app.py:446-449`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:386-393`
- **No accuracy assessment of the recommendations, and no critical error rate** — RO3.2, blocking  
  RO3.2 requires 'to assess the accuracy of these recommendations', and Table 3.12 names 'Confusion matrix, accuracy, critical error rate'. fuel_scores gives the classifier a 4-class confusion, per-class P/R/F1, macro-F1 and accuracy — but nothing scores the recommendation, and no critical error rate exists: grep -i 'critical' over ablation-service/*.py, alert-service/*.py and frontend/static/ablation.html returns zero  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:278-318`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:4-9`, `scratchpad/thesis/chapter_1_and_2.txt:65`
- **sceneEvidence() out of scope kills the dashboard's whole camera path** — RO3.3 / Alg.1 / Alg.2, blocking  
  `function sceneEvidence()` is declared INSIDE `async function reportFire(vlm)` (opens index.html:1612, body 1620-1664). It is called from three places inside `detectOnce()` - lines 1779, 1797, 1819 - where it is not in scope. `reportFire` is never called anywhere (grep 'reportFire(' returns only the definition at 1612 and a prose comment at 1475), so the only definition is unreachable. Runtime effect, in strict mode   
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1620`, `fire_detection_and_classification_web_app/frontend/static/index.html:1779`
- **Zone aggregation never filters nodes by zoneId** — ALG1, major  
  Algorithm 1 says "for each node n in the zone" and "Z <- worst(L[n] over the nodes of the zone)". The implementation in escalation.js:83-87 iterates payload.nodes - every node the bridge knows about - and never reads n.zoneId. S.zoneId exists (escalation.js:49, set from CAMERA_ZONE_ID at index.html:1135 and 2269-2270) but is used only as a label on outgoing POSTs (escalation.js:187, 195, 226, 239, 289, 359). The serv  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:83`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:49`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:257`
- **Zone aggregation is missing from the sensor service, and ignores zoneId** — ARCH, major  
  Table 3.7 puts "Threshold grading inside the sensor service (normal, warn, danger), with the worst value taken for each node and for the zone" in the intelligence layer. Only half of that is there. esp32-sensor-service does per-channel grading (_level, main.py:112-121) and per-node worst-of with a stale-to-unknown rule (_node_json, main.py:165-193), and /api/sensors/latest returns a flat node list with no zone roll-u  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:253-271`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:165-193`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:73-89`
- **The 0.35 fire gate is not in the detection service and is triplicated** — ARCH, major  
  Algorithm 2 keys on "fire boxes B with confidence >= 0.35" (chapter_3.txt:285), and Table 3.7 puts judgement-forming in the intelligence layer. fire-detection-yolo-service applies no threshold at all: /detect returns every box ultralytics emits, unfiltered (main.py:40-50). The 0.35 gate is applied in the browser (index.html:1131 MIN_CONF, filtered at :1730) and independently re-declared in fire-classification-service  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:40-50`, `fire_detection_and_classification_web_app/frontend/static/index.html:1131`, `fire_detection_and_classification_web_app/fire-classification-service/constants.py:23`
- **The accepted level A is computed but never put on the screen** — Alg.1 / RO3.3 (live sensor data), major  
  Alg.1's output is three things: node level, zone level and the ACCEPTED level A. The dashboard computes A in `applyLevel` (escalation.js:106-120) and exposes it as `sensorLevel` from `state()` (escalation.js:368), but nothing renders it: the only reader of `st.sensorLevel` in the frontend is `sceneEvidence`'s `gasLevel` field (index.html:1638), which is itself unreachable. The `onChange` handler uses only `st.alarm`,  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:106`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:368`, `fire_detection_and_classification_web_app/frontend/static/js/sensor-panel.js:74`
- **Sequence numbers are carried but message loss rate is never computed, and seq is not even stored per sample** — RO1.1, major  
  Table 3.12 (Ch3 line 365) names 'message loss rate from the sequence numbers' as THE analysis for RO1.1, and Ch3 line 505 repeats that the loss rate is reported. The number is transported correctly - ino:185 and :228 emit and increment seq, main.py:102 accepts it, main.py:183 republishes it, sensor-panel.js:96 prints it as '#N'. But grep -rnE '\bseq\b' over all *.py and *.js in the web app returns only those five lin  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:248`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:183`, `fire_detection_and_classification_web_app/frontend/static/js/sensor-panel.js:96`
- **No trial sensor logs and no durable log store - the only history is a 36-minute in-process ring buffer** — RO1.1, major  
  Table 3.12 (Ch3 line 364) lists 'Sensor logs from the trials' as the data for RO1.1. There are none in the repos: ablation-data/ contains only README.md, and find over the whole web app for 'sensors.csv' or 'meta.json' returns nothing. The only store is deque(maxlen=720) per node (main.py:44, 234), about 36 minutes at 3 s, held in a module-level dict that the docstring says must stay single-worker (main.py:26) and th  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:44`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:26`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:273`
- **Message-loss rate is never computed, and history drops seq so it cannot be** — RO1.1, major  
  Table 3.12 gives RO1.1's analysis as 'message loss rate from the sequence numbers' (chapter_3.txt:365) and s3.3.3 repeats it (chapter_3.txt:505). The service stores only the LATEST seq (main.py:241, exposed at main.py:183) and the history ring buffer appends {'t': now_iso, **readings} (main.py:248) — readings is the Readings model, which has no seq field (main.py:79-94). So no gap can be reconstructed even from the s  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:365`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:248`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:241`
- **No persisted sensor log: 36 minutes in RAM, erased on restart** — RO1.1, major  
  Table 3.12 lists RO1.1's collected data as 'Sensor logs from the trials' analysed with descriptive statistics (chapter_3.txt:364-365). The only store is an in-process dict with a per-node deque of HISTORY_MAX=720 samples — about 36 minutes at 3 s, as the comment states (main.py:43-44, 234) — and the service must stay single-worker because of it (Dockerfile:20-23). I read all 299 lines of main.py: there is no file wri  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:43`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:234`, `fire_detection_and_classification_web_app/esp32-sensor-service/Dockerfile:20`
- **Detection service applies no confidence threshold of its own** — RO1.2, major  
  fire-detection-yolo-service/main.py:40 calls model(frame)[0] with no conf= or iou= argument, so Ultralytics defaults apply (conf 0.25, iou 0.7) and every box at or above 0.25 is returned to the caller. The 0.35 gate exists only in the two consumers (index.html:1730, vision.py:73/84). The service that owns the model does not own its own operating point, so the thesis number is enforced by convention across three files  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:40`, `fire_detection_and_classification_web_app/frontend/static/index.html:1730`, `fire_detection_and_classification_web_app/ablation-service/vision.py:73`
- **The mAP figure is recorded nowhere a reader can see it** — RO1.2, major  
  grep -rni 'mAP' across all four repos (excluding node_modules and .git) returns hits only in THESIS_CHANGES.md:258-275, which discusses the objective's wording, never a measured number. No evaluation script, no results file, no per-class precision/recall for the detector, no docs/ entry (docs/ contains one PNG only). README.md:140 gives the provenance in one line - "YOLO11 (Ultralytics), trained on HomeFire and Crowd  
  Evidence: `fire_detection_and_classification_web_app/THESIS_CHANGES.md:258`, `fire_detection_and_classification_web_app/README.md:140`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:225`
- **No held-out test-split evaluation runs anywhere in the code** — RO1.2, major  
  chapter_3.txt:480 commits to using the official HomeFire train/val/test splits unchanged and reporting on the held-out test split (1,300 test images per Table 3.14 at chapter_3.txt:469). Nothing in the repo evaluates the model: no model.val() call (grep -rn 'model.train\|model.val' --include=*.py returns nothing beyond the two inference loads), no test images, no results CSV. The 0.84635 inside best.pt is the validat  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:40`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:469`
- **Training stopped at epoch 27 of a configured 300, patience never reached** — RO1.2, major  
  best.pt records epoch = 26 (0-indexed, so the 27th) and best_fitness = 0.5214, which equals the mAP50-95 of the LAST row of train_results - so the best epoch is also the final epoch. train_args set epochs = 300 and patience = 50, so early stopping cannot have fired by epoch 27; the run was cut short (train_args project/save_dir point at '/content/drive/My Drive/fire_research/working/baseline_training', i.e. a Colab s  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (archive/data.pkl: epoch=26, best_fitness=0.5214, train_args['epochs']=300, train_args['patience']=50, train_results['metrics/mAP50(B)'] 27 entries)`, `thesis/chapter_1_and_2.txt:50`
- **The measured mAP appears nowhere a reader can see, in any of the four repos** — RO1.2, major  
  The only record of 0.84635 is inside a 15 MB pickle. I searched all four repos with `grep -rnI "0\.846|84\.6|mAP50|mAP@0\.5"` (excluding node_modules and .git) and with `grep -rniI "mAP"`: the only prose hits are THESIS_CHANGES.md:258 and :271, which restate the 0.85 TARGET and ask for "the actual mAP figures" to be reported - they never give them. README.md:140 says only "YOLO11 (Ultralytics), trained on HomeFire an  
  Evidence: `fire_detection_and_classification_web_app/THESIS_CHANGES.md:258`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:266-273`, `fire_detection_and_classification_web_app/README.md:140`
- **No training script, notebook, dataset yaml or results file in any repo** — RO1.2, major  
  RO1.2's deliverable is "a trained model with reproducible training configuration". `find . \( -name "*.ipynb" -o -name "data.yaml" -o -name "args.yaml" -o -name "results.csv" -o -iname "*train*" -o -name "*.pt" \)` across all four repos (excluding node_modules/.git) returns exactly two files: the two best.pt binaries. No notebook, no train.py, no dataset yaml, no results.csv, no confusion matrix image, no split manif  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (archive/data.pkl: train_args['data']='/content/drive/My Drive/fire_research/dataset/data.yaml')`, `thesis/chapter_1_and_2.txt:50`, `fire_detection_and_classification_web_app/fire-detection-yolo-service/ (4 files only: Dockerfile, best.pt, main.py, requirements.txt)`
- **Only a val-split number exists; no test-split, per-class or confusion-matrix results** — RO1.2, major  
  train_args records split='val' and val=True, so 0.84635 is a VALIDATION-split figure from the training loop. The thesis promises more: chapter_3.txt:477 "The official training, validation and test splits of the HomeFire dataset are used without change", chapter_3.txt:673 "Metrics are reported on the test split of each public dataset ... Per class results are also reported, because a high mean can hide poor smoke dete  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (archive/data.pkl: train_args['split']='val', train_metrics)`, `thesis/chapter_3.txt:477`, `thesis/chapter_3.txt:673`
- **The >=50 per cent false-alarm reduction claim is not measured on Algorithm 2** — RO1.3, major  
  RO1.3's headline is that fusion plus verification cuts false alarms by at least 50 per cent against vision-only. The only false-alarm machinery is in ablation-service: metrics.py:240-244 computes false_alarm_rate, its Wilson interval and false alarms per hour, and runs.py:342-362 reports them per combination. But every combination is a rule over a feature frame (combos.py:144-250), none of them is Algorithm 2, none m  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:240`, `fire_detection_and_classification_web_app/ablation-service/runs.py:342`, `fire_detection_and_classification_web_app/ablation-service/combos.py:144`
- **No test exercises the arbitration matrix** — RO1.3 / Alg.2, major  
  The repo has four test files: vlm-service/test_prompts.py, alert-service/test_report.py, test_routing.py and test_api.py. test_prompts.py checks prompt text only, and notably never asserts the lamp/torch/camera-flash clause the thesis requires - it checks 'AIRBORNE DUST' and 'STEAM, VAPOUR' instead (test_prompts.py:45-47). test_api.py touches the severity and verification values on stored incidents (test_api.py:131-1  
  Evidence: `fire_detection_and_classification_web_app/vlm-service/test_prompts.py:45`, `fire_detection_and_classification_web_app/alert-service/test_api.py:131`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:142`
- **The Normal-row 'verification unavailable recorded' outcome is never recorded anywhere** — RO1.3 / Alg.2 Table 3.9, major  
  Table 3.9's Normal x unavailable cell reads 'CLEAR, verification unavailable recorded'. In code that path produces state 'clear', and evaluate() posts nothing when the tier is clear (escalation.js:166-168 only post on 'warning' or on an alarm edge). The only trace is an in-memory browser log entry, S.log.push({text: '[vlm error: ...]'}) at index.html:1787, rendered in the VLM Scene Analysis card and lost on reload; S  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:166`, `fire_detection_and_classification_web_app/frontend/static/index.html:1787`, `fire_detection_and_classification_web_app/alert-service/app.py:473`
- **Algorithm 3's latency output is neither returned nor stored** — RO1.3 / Alg.3, major  
  Algorithm 3's OUTPUT line names four things: the verdict, detected, type, description, 'and the latency', with 'V.latency <- latency returned by the service'. /describe-image/ is the one endpoint in vlm-service that returns no latency_ms - compare /warn-from-sensors/ (main.py:288), /describe-image-detailed/ (main.py:386) and /describe-scene/ (main.py:475), all of which time themselves with time.perf_counter(). Nothin  
  Evidence: `fire_detection_and_classification_web_app/vlm-service/main.py:295`, `fire_detection_and_classification_web_app/vlm-service/main.py:386`, `fire_detection_and_classification_web_app/alert-service/db.py:183`
- **Arbitration runs only in the browser tab, so closing the dashboard stops all decisions** — RO1.3 / Algorithm 2, major  
  intake.py's module docstring (:1-5) says the logic is shared by "every fire producer (browser dashboard today, a server-side monitor later)", and that later never arrived: I grepped both repos for 'FIRE CONFIRMED', 'GAS DANGER' and 'gas_danger' and every arbitration decision comes from frontend/static/js/escalation.js. If the dashboard tab is closed or the operator's laptop sleeps, no fire event is ever posted and th  
  Evidence: `fire_detection_and_classification_web_app/alert-service/intake.py:1`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:142`, `fire_detection_and_classification_web_app/frontend/static/index.html:1440`
- **vlm-service has no timeout of its own on the Gemini call** — RO1.3 / Algorithm 3 ("with timeout"), major  
  Algorithm 3 says `raw <- VLM(F, fixed prompt) with timeout`. In vlm-service/main.py the LLM is constructed at :30-33 with only model and api_key - no timeout, no request_timeout, no max_retries. `llm.invoke` at :309 can therefore hang for as long as the SDK default allows. The only real timeout is the frontend proxy's VLM_TIMEOUT, default 60 s (frontend/server.py:22, applied at :125). Because S.pendingVlm stays true   
  Evidence: `fire_detection_and_classification_web_app/vlm-service/main.py:30`, `fire_detection_and_classification_web_app/vlm-service/main.py:309`, `fire_detection_and_classification_web_app/frontend/server.py:22`
- **No test anywhere covers the arbitration matrix or the Algorithm 3 guards** — RO1.3 / Table 3.9, major  
  Algorithm 2 and Algorithm 3's client-side guards live entirely in JavaScript, and there is no JavaScript test in any repo. `find . -name '*test*'` in the web app returns only vlm-service/test_prompts.py (prompt wording only), alert-service/test_api.py, test_report.py, test_routing.py, and an ablation CSV; `ls frontend/static/js` returns camera-sources.js, sensor-panel.js, escalation.js and nothing else. test_api.py:3  
  Evidence: `fire_detection_and_classification_web_app/alert-service/test_api.py:36`, `fire_detection_and_classification_web_app/alert-service/test_api.py:144`, `fire_detection_and_classification_web_app/vlm-service/test_prompts.py:34`
- **None of the non-parametric analysis Ch.3 commits to is implemented** — RO1.4, major  
  Ch.3 line 684 fixes, before data collection: a Friedman test across the four configurations, Wilcoxon signed-rank post hoc with Bonferroni correction, Kendall's W and r effect sizes, and exact p-values. No such code exists - I grepped all four repos for 'friedman', 'wilcoxon', 'kendall', 'bonferroni', 'effect size' and found only prose in THESIS_CHANGES.md:345 and :630. ablation-service/requirements.txt pins pandas a  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/requirements.txt:11`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:190`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:630`
- **Results are never persisted, so no result table survives a restart** — RO1.4, major  
  RUNS is a plain in-process dict and the Dockerfile pins the service to one worker precisely because of it; nothing is written to disk or to a database, and no committed ablation table exists in the repo (docs/ holds only web_app_cover_image.png). A viva demo must therefore re-run the study live, and a number quoted in Chapter 4 has no artefact behind it unless someone manually saves the CSV. Combined with the broken   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/runs.py:70`, `fire_detection_and_classification_web_app/ablation-service/Dockerfile:22`, `fire_detection_and_classification_web_app/ablation-service/main.py:280`
- **End-to-end latency, a named dependent variable, is not aggregated anywhere** — RO1.4, major  
  Ch.3 line 95 lists 'end to end latency' as a dependent variable and Table 3.19 wants median and 95th percentile for the sensor path and the frame-to-detection path. The dashboard only displays the last call's duration per detector (S.fireMs / S.humanMs) and an FPS counter; nothing accumulates or percentiles them, and nothing stores them. The ablation run's timings dict holds classify_ms/score_ms/evaluate_ms, which ar  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:2051`, `fire_detection_and_classification_web_app/frontend/static/index.html:2068`, `fire_detection_and_classification_web_app/ablation-service/runs.py:131`
- **Ablation alarm is binary fire/no-fire, not the four states the thesis counts** — RO1.4, major  
  Ch.3 line 606 and line 682 define a false alarm and a detection as an entry into GAS DANGER or FIRE CONFIRMED, with GAS WARNING recorded separately and never counted as a false alarm. The ablation has no state machine at all: every arm returns one boolean, so a sensors-only arm firing on gas is scored as a fire detection, and the GAS WARNING/GAS DANGER distinction that Alg.2 exists to make is invisible in the result   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:279`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:348`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:33`
- **Nothing in any of the four repos captures a trial into the ablation-data layout** — RO1.4, major  
  To produce the missing recordings, an operator needs frames/000001.jpg..., sensors.csv and meta.json per experiment. No code writes them. grep -rn 'ablation-data' across the whole repo returns three hits only: .gitignore:17-18, the README itself, and docker-compose.yml:136 which mounts it :ro so the service cannot write there either. On the sensor side, esp32-sensor-service keeps samples in a RAM deque of maxlen HIST  
  Evidence: `fire_detection_and_classification_web_app/docker-compose.yml:136`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:44`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:273`
- **No repetition structure, so the repeated-measures design cannot be expressed** — RO1.4, major  
  Ch.1 RO1.4 requires 'at least ten repetitions of each controlled fire scenario' (chapter_1_and_2.txt:52); Ch.3 section 3.1.2 says 'Each scenario is repeated five times' - a thesis-internal contradiction worth flagging on its own. The code supports neither. The only grouping key is experiment_id (metrics.py:36, GROUP = 'experiment_id'); there is no scenario id and no repetition index. grep -rni 'repetition' over ablat  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:52`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:36`, `fire_detection_and_classification_web_app/ablation-service/recordings.py:113`
- **None of the statistical tests section 3.4.5 fixes in advance are implemented** — RO1.4, major  
  chapter_3.txt section 3.4.5 commits, before data collection, to: a Friedman test across the four configurations, Wilcoxon signed-rank post hoc with Bonferroni correction, and an effect size in every case (Kendall's W for Friedman, r for Wilcoxon). It also requires median, interquartile range, minimum and maximum per scenario and configuration. grep -rni 'friedman|wilcoxon|bonferroni|kendall|effect size|effect_size|cl  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:682`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:190`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:268`
- **ROC/PR curves and AUROC are promised in seven places but never computed** — RO1.4, major  
  The code and the UI repeatedly tell the reader an ROC curve exists: 'every arm also yields an ROC/PR curve from its score' (combos.py:7), 'for the ROC curve only' (constants.py:182 and 253), ROC_MIDPOINT = 0.5 described as 'the midpoint drawn on the ROC curve' (constants.py:83-85), 'too coarse to draw an ROC curve from' (combos.py:190), and the page prints 'Score used for the ROC curve' per combination (ablation.html  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:7`, `fire_detection_and_classification_web_app/ablation-service/constants.py:83`, `fire_detection_and_classification_web_app/ablation-service/main.py:166`
- **Results live only in process memory, so no result set survives a restart** — RO1.4, major  
  RUNS is a plain in-process dict (runs.py:70) and the Dockerfile pins one worker because of it (Dockerfile:22-26). Nothing writes a run to disk or a database: grep -rn 'sqlite|json.dump|\.to_csv|write_text' over ablation-service/*.py returns only a prose mention in metrics.py:45. Combined with the broken export.json above, there is currently no way to capture 'the full result set' RO1.4 names - a container restart los  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/runs.py:70`, `fire_detection_and_classification_web_app/ablation-service/Dockerfile:22`, `fire_detection_and_classification_web_app/ablation-service/runs.py:325`
- **No recall or counting-error measurement for the human model, and no training config** — RO2.1, major  
  RO2.1 states recall >= 0.90 and Table 3.18 asks for "Detection recall, counting error" on CrowdHuman test images plus lighting scenarios. Nothing in any repo computes either: grep -rn for recall|mAP over the whole tree hits only ablation-service/metrics.py:226-238, which scores fire windows/events, and ablation-service/main.py:61-62 points only at the fire detector - the human service is never called from the ablatio  
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/Dockerfile:20-22`, `fire_detection_and_classification_web_app/ablation-service/main.py:61-62`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:226-238`
- **Position is drawn but never produced as data: count only past the browser** — RO2.1, major  
  RO2.1 and chapter_3.txt line 135 ask for presence, count AND approximate position; line 609 says true positions were recorded as ground truth. The service does return per-person boxes in native frame pixels (main.py:84-90), and the dashboard draws them with a cover transform onto the human pane (index.html:1863-1874, 1907-1935). That is where position stops. S.lastHumanDets is never posted anywhere; /api/events/fire   
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:84-97`, `fire_detection_and_classification_web_app/frontend/static/index.html:1863-1874`, `fire_detection_and_classification_web_app/frontend/static/index.html:1907-1935`
- **Approximate position is drawn on screen but never recorded or used** — RO2.1, major  
  RO2.1 asks for "presence, count and approximate position". Presence and count are delivered. Position is delivered only as a transient on-screen overlay. The service does return per-person pixel boxes (main.py:84-90, `"box": [x1, y1, x2, y2]`), the proxy passes them through (server.py:105) and the browser draws numbered boxes over the camera pane (index.html:1863-1870). That is where position stops. The POST to alert  
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:84`, `fire_detection_and_classification_web_app/frontend/static/index.html:1660`, `fire_detection_and_classification_web_app/alert-service/routing.py:306`
- **No occupant-detection evaluation exists, only the fire one** — RO2.1, major  
  RO2.1's deliverable is "an occupant detection module AND its evaluation results", and Table 3.16 lists "Occupant detection recall, counting error" as the measure (chapter_3.txt:381, 657). The module exists; the evaluation does not. I grepped `person|occupan|human` across every file in ablation-service/*.py - zero hits; the ablation service scores fire windows and events only (metrics.py:226-238, runs.py:341-365) and   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:226`, `fire_detection_and_classification_web_app/ablation-service/runs.py:341`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:626`
- **Person model has no training config, checksum or provenance in the repo** — RO2.1, major  
  The human detector ships as an opaque 19 MB best.pt. `ls` of human-detection-yolo-service shows four files only: Dockerfile, best.pt, main.py, requirements.txt - no data.yaml, no results.csv, no args.yaml, no model card. The Dockerfile points at a fifth repository that is not in this audit set and not on disk: "crowdhuman_yolo11s_best.pt from the human_detection_yolo_model repo" (Dockerfile:20-21); `find` over Deskto  
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/Dockerfile:20`, `fire_detection_and_classification_web_app/human-detection-yolo-service/best.pt (train_args: data=/content/crowdhuman_yolo/data.yaml, epochs=100, patience=25, imgsz=640, seed=42, name=yolo11s_crowdhuman)`, `fire_detection_and_classification_web_app/fire-classification-service/model/PROVENANCE.md`
- **Occupant counting only runs while a dashboard tab is open** — RO2.1, major  
  Table 3.7 puts the human-detection YOLO service in layer 3 (Intelligence) and the dashboard in layer 5 (Presentation), which reads as a system that counts people whether or not anyone is watching. In the code the counting loop lives entirely in the browser: the only caller of /api/detect anywhere in the four repos is index.html:1563 (grep for `/detect` across all .py/.js/.html returns the service definitions, the pro  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1563`, `fire_detection_and_classification_web_app/frontend/static/index.html:2103`, `fire_detection_and_classification_web_app/esp32-cam-service/main.py:277`
- **home.json's graph is a tree, so Dijkstra has no alternative to choose** — RO2.2, major  
  Q4, home half. Computed from the file: home.json has 17 nodes and 16 edges, is connected, and has ZERO independent cycles - it is a spanning tree. In a tree there is exactly one path between any two nodes, so Dijkstra's shortest-path search is trivially the only path; the only genuine decision left is WHICH of the two exits, and whether an edge or exit is blocked. test_routing.py:92-95 concedes this in a comment ('Ev  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/home.json:86-265`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:90-295`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:85-104`
- **Optimality gap is structurally always null on both sites** — RO2.2, major  
  app.py:302-305 computes `gap = (record["lengthM"] - gt["lengthM"]) / gt["lengthM"]` guarded by `if gt and not gt.get("refugeExpected") and gt.get("lengthM")`. No groundTruth entry in EITHER file carries a `lengthM` key - `grep -n lengthM alert-service/sites/home.json alert-service/sites/industrial.json` returns nothing. So `optimalityGap` is None on every row of GET /api/analysis/routes, for both sites, always. chapt  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:302-305`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:324-361`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:347-363`
- **No ground-truth case expects a refuge, so the refusal metrics are always zero** — RO2.2, major  
  Every one of the 11 groundTruth entries across both files sets `refugeExpected: false` (home.json lines 327, 332, 337, 341, 346, 351, 355, 359; industrial.json lines 350, 355, 360). app.py:306-316 can therefore only ever produce `refusal: "n/a"` or `"false_refuge"`; `correctRefusals` and `missedRefusals` in the summary (app.py:331-333) are structurally pinned at 0. RO2.2 requires a refuge instruction when no exit is   
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/home.json:324-361`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:347-363`, `fire_detection_and_classification_web_app/alert-service/app.py:306-316`
- **Hazard-crossing first leg is outside both the drawn route and the zero-intersection metric** — RO2.2, major  
  When the route re-anchors, the leg from the occupant's real node to the re-anchor node is by construction inside the hazard radius - if the occupant node is within the radius then every edge incident to it was already dropped by `_prune`. That leg is not in `path_nodes`, not in `polyline_px`, and `from_px` is the re-anchor node. `_assert_clear` and `hazard_intersects` both iterate only `path_nodes`, so the hazardInte  
  Evidence: `fire_detection_and_classification_web_app/alert-service/routing.py:193-210`, `fire_detection_and_classification_web_app/alert-service/routing.py:242-244`, `fire_detection_and_classification_web_app/alert-service/routing.py:289-297`
- **Optimality gap can never be computed: no lengthM in any groundTruth entry** — RO2.2, major  
  Section 3.4.8 requires four route measures, one of which is the optimality gap. app.py:303 computes it only `if gt and not gt.get("refugeExpected") and gt.get("lengthM")`, but `grep -n lengthM sites/*.json` returns nothing - neither home.json nor industrial.json declares a hand-derived `lengthM` on any of its 11 groundTruth entries. `optimalityGap` is therefore always null for every row, and the summary block does no  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:302-304`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:324-361`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:347-363`
- **Correct-refusal measure can never register a success** — RO2.2, major  
  Section 3.4.8's fourth measure is "Correct refusal" for the scenarios where all exits are cut off. `/api/analysis/routes` sets `refusal = "correct"` only when `gt["refugeExpected"]` is true, but `grep -c 'refugeExpected": true'` returns 0 in both site files (8 entries in home, 3 in industrial, all false). So `correctRefusals` is structurally pinned at 0 and `falseRefuges` is the only refuge outcome the endpoint can r  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:306-315`, `fire_detection_and_classification_web_app/alert-service/app.py:338-340`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:324-361`
- **Industry path has thin route evidence: ground truth for 3 of 7 zones, no refuge case** — RO2.2, major  
  The user wants both the home and the industry path defensible. home.json declares hand-derived groundTruth for all 8 of 8 zones; industrial.json declares it for only 3 of 7 (fabric-store, dyeing, boiler - cutting-floor, warehouse, finishing and sewing-a have none). `test_declared_ground_truth_matches_what_the_router_does` only iterates declared entries, so those four zones are never checked against a hand-derived ans  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:347-363`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:324-361`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:160-166`
- **The home graph is a tree, so Dijkstra has no alternative path to weigh** — RO2.2, major  
  home.json has 17 nodes (line 86) and 16 edges (line 200), and sites.py:170-178 proves it connected, so it is a tree: exactly one path exists between any two nodes. Dijkstra's optimisation therefore reduces to choosing between the two exits — real and non-trivial (my run shows 4 zones routed north and 4 south, and scenario 3 at test_routing.py:85 genuinely reverses the living area from the back door to the front), but  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/home.json:200`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:214`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:85`
- **No production path produces per-occupant routes or blocks an exit** — RO2.2 / RO2.3, major  
  `route_for_zone` accepts `occupant_zone_id` and `blocked_exit_ids`, but the only caller that passes them is test_routing.py:22. `_attach_route` calls `routing.route_for_zone(site, fire_zone_id=zone_id)` with neither, so the occupant is always assumed to be in the burning zone, and no endpoint among the 19 in app.py exposes either parameter (searched `grep -n "@app\.\(get\|post\|put\|delete\)" app.py` and `grep -n occ  
  Evidence: `fire_detection_and_classification_web_app/alert-service/routing.py:300-319`, `fire_detection_and_classification_web_app/alert-service/intake.py:103`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:21-23`
- **Refuge instruction is unreachable in every shipped configuration** — RO2.2 / RO2.3, major  
  I ran the exact production call (`route_for_zone(site, fire_zone_id=z)`) for all 8 home zones and all 7 industrial zones at their authored radii: every single one returns status "exit". A refuge can only arise when an occupant is in a different zone from the fire (never done in production — see the occupant-position finding) or when exits are marked blocked (no runtime input — see below). Re-running home with HAZARD_  
  Evidence: `fire_detection_and_classification_web_app/alert-service/routing.py:252`, `fire_detection_and_classification_web_app/alert-service/app.py:345`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:113`
- **No runtime way to mark an exit blocked** — RO2.2 / §3.3.7, major  
  Thesis §3.3.7: "A home has fewer exits than a factory, so in some cases we marked an exit as blocked in the system rather than blocking it physically." The `blocked_exit_ids` parameter exists and works (routing.py:171, 216) but I searched every .py/.js/.yml/.env in the web app for a caller: the only non-library uses are test_routing.py:23,81,102,110,148. There is no API endpoint, no env var (sample.env has only SITE_  
  Evidence: `fire_detection_and_classification_web_app/alert-service/routing.py:171`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:23`, `fire_detection_and_classification_web_app/sample.env:24`
- **Optimality gap is always null - no ground truth carries a length** — RO2.2 / §3.4.8, major  
  app.py:302-304 computes the optimality gap only when `gt.get("lengthM")` is truthy: `gap = (record["lengthM"] - gt["lengthM"]) / gt["lengthM"]`. Neither site file has a single `lengthM` key — `grep -n "lengthM" alert-service/sites/*.json` returns nothing across home.json's 8 groundTruth entries (line 324) and industrial.json's 3 (line 347). `optimalityGap` is therefore None on every row of GET /api/analysis/routes, a  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:302`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:324`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:347`
- **The safety officer's printed report shows the muster estimate, not the check-out count** — RO2.3, major  
  Thesis s3.4.8 (chapter_3.txt:733) requires the head-count and "the number of occupants who marked themselves out in the mobile application ... reported side by side, and every difference is listed". /api/incidents/{id}/report serves both — report_json includes checkout_json at serializers.py:399 and occupancy at 394-397 — but the printable report page renders only 'Peak occupancy' as a stat tile (reports.html:286) an  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/reports.html:286`, `fire_detection_and_classification_web_app/frontend/static/reports.html:332`, `fire_detection_and_classification_web_app/alert-service/serializers.py:399`
- **The web dashboard never displays the situation report** — RO3.1, major  
  The report is serialised onto both the live state and the after-action report (serializers.py:272 and :399, via situation_report_json at l.229). But index.html contains no rendering code for it - grep for 'situationReport|grounding|claims' over index.html returns one hit, the comment at l.1613 above the evidence builder. reports.html fetches /api/incidents/{id}/report and renders zone, fuel, occupancy, timeline, exti  
  Evidence: `fire_detection_and_classification_web_app/alert-service/serializers.py:229`, `fire_detection_and_classification_web_app/alert-service/serializers.py:399`, `fire_detection_and_classification_web_app/frontend/static/index.html:1613`
- **No claim-level grounding accuracy measure across trials, as Table 3.12 requires** — RO3.1, major  
  Table 3.12 lists the RO3.1 measures as 'Claim level grounding accuracy, accuracy of the detected and type fields' (chapter_3.txt:393). The code computes groundingAccuracy only per single report, over its own 4-5 claims (report.py:282), which cannot be the study measure - with five claims the only attainable values are 0, 0.2, 0.4, 0.6, 0.8, 1.0. I searched alert-service/app.py and the whole of ablation-service/ with   
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:282`, `fire_detection_and_classification_web_app/alert-service/app.py:279`, `fire_detection_and_classification_web_app/alert-service/app.py:423`
- **Accuracy of the VLM 'detected' and 'type' fields is not measured anywhere** — RO3.1, major  
  The second half of the Table 3.12 RO3.1 measure (chapter_3.txt:393, repeated at :661) asks for the accuracy of the 'detected' and 'type' fields of Table 3.10 against per-trial ground truth. The report grades only the five scene fields; 'detected' and 'type' are consumed for arbitration and classification and never scored. Searched ablation-service/metrics.py (its public functions are build_truth, warmup_profile, wils  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:322`, `fire_detection_and_classification_web_app/alert-service/report.py:249`
- **H3's 90 percent threshold is nowhere in the code** — RO3.1, major  
  chapter_3.txt:112 and :726 accept H3 only if at least 90 percent of claims are supported. grep for '0\.9|90' over alert-service/report.py and alert-service/test_report.py returns zero hits. Nothing computes or asserts a pass/fail against the threshold, in the service or in the tests, so the hypothesis cannot be evaluated from the artefact as it stands.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:276`, `fire_detection_and_classification_web_app/alert-service/test_report.py:142`
- **Material claim can never be supported live, because the report is built before classification** — RO3.1, major  
  _check_material grades against ev['fuelType'] (report.py:82), which _attach_report reads from the incident row's fuel_type (intake.py:75). But the report is built at incident creation (intake.py:234) and the fuel verdict arrives later, on the separate tier-3 path handle_classification (intake.py:314-334), which never rebuilds the report - _attach_report is called from only two places, l.182 and l.234. So fuel_type is  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:82`, `fire_detection_and_classification_web_app/alert-service/report.py:86`, `fire_detection_and_classification_web_app/alert-service/intake.py:75`
- **The situation report is posted but discarded, because the duplicate fire event loses the race** — RO3.1, major  
  Found while tracing the arbitration. sendFire issues two POSTs to /api/events/fire for a tier-2 fire: one inside the describeScene callback carrying the scene (escalation.js:225-235) and one immediately, without it (escalation.js:238-267). The second is issued synchronously while the first waits on captureBlob plus a multi-second /api/describe-scene call, so the scene-free post reaches intake first and creates the in  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:225`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:238`, `fire_detection_and_classification_web_app/alert-service/intake.py:185`
- **Material is graded against a classifier verdict that has not arrived yet** — RO3.1, major  
  _attach_report seeds ev['fuelType'] from the incident row at the moment the fire event lands (intake.py:75). The fuel verdict arrives later on a separate endpoint - escalation.js only classifies while the sensors are warn/danger, and the thesis itself says gas reaches the sensor 14-22 s after the camera sees the flame - and handle_classification (intake.py:314-351) never re-runs _attach_report. So fuelType is None at  
  Evidence: `fire_detection_and_classification_web_app/alert-service/intake.py:75`, `fire_detection_and_classification_web_app/alert-service/intake.py:314`, `fire_detection_and_classification_web_app/alert-service/report.py:85`
- **Ungraded model prose still reaches the responder alongside the graded claims** — RO3.1, major  
  RO3.1 asks that every generated claim is validated before release. Two generated strings bypass the grader. (1) build() returns the model's own sentence as "narrative" (report.py:264-267) and the phone renders it as plain body text with no icon and no unverified pill (situation_report_card.dart:64-71). (2) The VLM's /describe-image/ sentence travels as the incident description into the FCM data payload (fcm.py:167) a  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:264`, `fire_notification_and_evacuation_mobile_app/lib/features/incident/widgets/situation_report_card.dart:64`, `fire_detection_and_classification_web_app/alert-service/fcm.py:167`
- **The dashboard never renders the situation report it already receives** — RO3.1 / RO3.3, major  
  serializers.report_json includes "situationReport" in the payload of /api/incidents/{id}/report (serializers.py:401, app.py:212-228). reports.html fetches exactly that endpoint (l.264) and renders stats, timeline, the raw detection description, the guidance table and caveats - but never touches r.situationReport: grep for situationReport across frontend/static returns only two comment lines (escalation.js:133, index.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/serializers.py:401`, `fire_detection_and_classification_web_app/frontend/static/reports.html:264`, `fire_detection_and_classification_web_app/frontend/static/reports.html:330`
- **No aggregate claim-level grounding accuracy, only per-incident figures** — RO3.1 / Table 3.12, major  
  Table 3.12 RO3.1 (chapter_3.txt:391-393) requires "Claim level grounding accuracy" as the measure, and s3.4.7 aggregates over trials. The code computes the two rates per report only (report.py:282-283) and stores them inside the incident's situation_report blob. alert-service exposes /api/analysis/routes (app.py:279) for RO2.2 and /api/analysis/delivery (app.py:423) for RO2.3 but no equivalent for RO3.1; searched wit  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:282`, `fire_detection_and_classification_web_app/alert-service/app.py:279`, `fire_detection_and_classification_web_app/alert-service/app.py:423`
- **The 'detected' and 'type' field accuracy measure does not exist anywhere** — RO3.1 / Table 3.12, major  
  Table 3.12 RO3.1 names two measures: claim-level grounding accuracy and "accuracy of the detected and type fields" against each trial's ground truth (chapter_3.txt:393, repeated at l.726 and l.661). Searched ablation-service with `grep -rn vlm` filtered on truth/accur/score/correct and read metrics.py's public functions (binary_scores l.214, detection_latency l.250, fuel_scores l.278, evaluate l.322): nothing scores   
  Evidence: `scratchpad/thesis/chapter_3.txt:393`, `scratchpad/thesis/chapter_3.txt:726`, `scratchpad/thesis/chapter_3.txt:112`
- **The raw evidence the claims were checked against is never stored** — RO3.1 / s3.4.7, major  
  report.py:44-48 states "The gas channel is still stored with the incident as logged evidence for the analysis in Section 3.4.7". It is not. _attach_report passes the evidence dict to situation.build and stores only the built report (intake.py:76-77); db.py's incidents schema has no evidence column and the schema comment confirms "What is kept is the graded claim list" (db.py:188-191). Searched with `grep -rn gasLevel  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:44`, `fire_detection_and_classification_web_app/alert-service/intake.py:76`, `fire_detection_and_classification_web_app/alert-service/db.py:188`
- **Wet chemical is never a recommendable agent, only narrative text** — RO3.2, major  
  RO3.2 (chapter_1_and_2.txt:65) requires coverage of 'water, foam, carbon dioxide, dry powder and wet chemical agents' - five. The code delivers four: water, foam, CO2, dry powder. grep -rni 'wet chemical' over all four repos hits only prose - the module docstring (extinguishers.py:25-27), the liquid_fuel 'caution' string (lines 84-88) and the unused modelLimits list (app.py:446-448). No 'use' or 'do_not_use' entry an  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:65`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:84`, `fire_detection_and_classification_web_app/alert-service/app.py:446`
- **No accuracy assessment of the recommendations against the standard** — RO3.2, major  
  RO3.2's deliverable is 'a recommendation module AND its accuracy assessment ... against an established fire classification standard across all tested fire materials'. The module exists; the assessment does not. ablation-service/metrics.py:278-310 (fuel_scores) gives 4-class confusion, per-class precision/recall/F1, macro-F1 and wrong_fuel_given_detected - but that measures the CLASSIFIER, not the mapping. I searched   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:278`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:306`, `fire_detection_and_classification_web_app/README.md:288`
- **Sensors-only model is never scored as a 4-class fuel classifier** — RO3.2, major  
  Table 3.12 lists 'comparison of the sensors only and fusion models' as RO3.2's analysis. score_all returns a fuel frame only from combo6_fusion; combo1_sensors takes the sensor model's own four-class probability vector and immediately collapses it to binary through _collapse_to_binary, so fuel_scores is only ever called on combination 6's output. The sensor_proba is fetched over HTTP, used for a fire/no-fire ROC, and  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:144-155,268,277,283`, `fire_detection_and_classification_web_app/ablation-service/combos.py:95-120`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:404-420`
- **Fuel table carries no bootstrap confidence interval** — RO3.2, major  
  Ch3 line 735 requires the four-class result 'reported as a confusion matrix over the four classes and as the event level macro F1 ... every score is reported with a 95 percent bootstrap confidence interval, resampled by run, and the models are compared on the same runs with McNemar's test'. mcnemar() exists and accuracy_ci is rendered, but both operate on the binary event decision only; fuel_scores returns confusion,  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:305-318`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:190-191,377`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:322-323,506-512`
- **Table 3.11's first actions are missing for two of the three classes** — RO3.2, major  
  Table 3.11's first action for solid combustible is 'Raise the alarm, switch off electrical power to the area if it is safe, and cool the base of the fire' and for liquid fuel 'Raise the alarm, stop the flow of fuel if it is safe, and smother the surface of the burning liquid'. Searched alert-service/ and frontend/static/ with grep -i for 'raise the alarm', 'switch off', 'stop the flow', 'smother' and 'cool the base':  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:68,94`, `fire_detection_and_classification_web_app/frontend/static/index.html:1770,1793,2194`, `scratchpad/thesis/chapter_3.txt:336,341`
- **The grounded situation report is never shown on any web page** — RO3.3 (generated reports) / RO3.1, major  
  RO3.3 says the dashboard presents 'generated reports'. alert-service builds the RO3.1 situation report with per-claim grounding categories and a grounding-accuracy figure (report.py:240-290) and serialises it onto the incident report as `situationReport` (serializers.py:401). `grep -rn 'situationReport' frontend/static/` returns nothing - no hit in index.html, reports.html or any JS file. reports.html renders only `r  
  Evidence: `fire_detection_and_classification_web_app/alert-service/serializers.py:401`, `fire_detection_and_classification_web_app/alert-service/report.py:240`, `fire_detection_and_classification_web_app/frontend/static/reports.html:333`
- **Dashboard state is browser-only; /api/state is never read and live incidents have no report** — RO3.3 (system status / generated reports), major  
  alert-service exposes `/api/state` with every zone and the active incident (app.py:196-200), and the Flutter app uses it. The web dashboard never calls it - the endpoint grep over frontend/static has no `/api/state` hit. All alarm state lives in the browser's `S` object, so a page refresh, a second officer's browser or a laptop reboot mid-incident shows 'All clear' while a fire is still open in the database. Compound  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:196`, `fire_detection_and_classification_web_app/alert-service/db.py:467`, `fire_detection_and_classification_web_app/frontend/static/reports.html:224`
- **No status indicator for alert-service or the classifier; event posts fail silently** — RO3.3 (system status), major  
  The four service pills cover the fire detector, the human detector, the VLM and the camera (index.html:1069-1072). Nothing reports alert-service, which owns incidents, the FCM push and the guidance table, or fire-classification-service. Every event post swallows its failure into `console.warn`: sendWarning (escalation.js:201), the scene report (234), the fire event (267), clear (290) and classification (361). `startS  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1069`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:201`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:267`
- **No evaluation instrument, results or analysis artefact exists anywhere** — RO3.4, major  
  RO3.4's three named deliverables — instrument, results, thematic analysis — exist in no repo. Searches run: (1) `find . -type f` over the whole tree with -iname matching *eval*, *survey*, *question*, *instrument*, *likert*, *consent*, *participant*, *expert*, *interview*, *thematic*, *codebook*, *code_book* (excluding node_modules/.git) → ZERO hits; (2) `grep -rniE "RO3\.4|expert (evaluation|review|panel)|participant  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:67`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:618`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:802`
- **Printable report drops 2 of 5 Presentation B components: situation report and route** — RO3.4, major  
  report_json serves both the situation report (serializers.py:401) and the route (serializers.py:402), but reports.html never reads either. `grep -niE "situationreport|\broute\b|checkedout|checkout|polyline|instruction" frontend/static/reports.html` returns ZERO hits. The page renders r.classification, r.timeline, r.detection, r.muster, r.caveats and r.durations only. The dashboard is no better: `grep -niE "situation|  
  Evidence: `fire_detection_and_classification_web_app/alert-service/serializers.py:401`, `fire_detection_and_classification_web_app/alert-service/serializers.py:402`, `fire_detection_and_classification_web_app/frontend/static/reports.html:325`
- **The only on-demand incident generator yields 2 of 5 Presentation B components** — RO3.4, major  
  §3.3.8 requires "the same set of three recorded incident scenarios, drawn from the controlled trials", each shown twice with order alternated between participants (chapter_3.txt:621-624). The only on-demand stager in any repo is POST /api/test-alert (alert-service/app.py:517-549). It offers three SEVERITIES (fire, gas_danger, warning) — not three recorded scenarios — and its scene text is hard-coded, e.g. "Open flame  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:517`, `fire_detection_and_classification_web_app/alert-service/app.py:548`, `fire_detection_and_classification_web_app/alert-service/intake.py:68`
- **Nothing maps the ten services onto the five Table 3.7 layers** — ARCH, minor  
  README.md:95-108 is the only architecture documentation in any of the four repos, and it is a flat ten-row service/port/responsibility table with no layer column and no reference to Table 3.7. A grep for "five layer", "Table 3.7", "Perception layer" and "Presentation layer" across every *.md in all four repos and both support folders returns zero hits, and the three docs/ directories contain only cover-image PNGs - n  
  Evidence: `fire_detection_and_classification_web_app/README.md:95-115`, `fire_detection_and_classification_web_app/docs/`, `fire_notification_and_evacuation_mobile_app/docs/`
- **No descriptive statistics over sensor channels, the other analysis Table 3.12 names for RO1.1** — RO1.1, minor  
  Table 3.12 (Ch3 line 365) names two analyses for RO1.1: descriptive statistics and message loss rate. grep -rlniE 'descriptive' over all *.py, *.js and *.md in the web app returns nothing. ablation-service/metrics.py does compute medians, p90s and means (lines 253-270, 308-316) but those are detection latency, precision/recall and macro-F1 for RO1.3/RO1.4, not per-channel summaries of MQ-2, MQ-7, temperature, humidit  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:253`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:308`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:365`
- **No test covers the sensor bridge or its published thresholds** — RO1.1, minor  
  esp32-sensor-service contains exactly three files — main.py, Dockerfile, requirements.txt (find over the directory) — and no test. Test files exist only in vlm-service (test_prompts.py) and alert-service (test_api.py, test_report.py, test_routing.py); rg -n 'esp32-sensor|sensors/ingest|SENSOR_MQ2' over every *test* file returns nothing. So the six numbers the thesis publishes in Table 3.8, the worst-of-channels rule   
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:111`, `fire_detection_and_classification_web_app/esp32-sensor-service/Dockerfile:12`, `fire_detection_and_classification_web_app/alert-service/test_api.py:85`
- **Nothing is version-pinned, so the reported behaviour is not reproducible** — RO1.2, minor  
  The checkpoint was written by ultralytics 8.4.12 (best.pt version key). requirements.txt pins only floors: `ultralytics>=8.4.12`, `numpy<2`, `opencv-python-headless<4.11`, and the Dockerfile installs `torch torchvision` from the CPU index with no version at all (lines 13-15). A rebuild months later resolves a different ultralytics and torch, which can change NMS defaults and therefore the boxes the 0.35 gate sees. Ag  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/requirements.txt:1-6`, `fire_detection_and_classification_web_app/fire-detection-yolo-service/Dockerfile:13-15`, `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (archive/data.pkl: version='8.4.12')`
- **Fire service sets no conf, iou or imgsz, so it emits boxes below the thesis gate** — RO1.2, minor  
  main.py:40 calls `model(frame)[0]` with no arguments, so Ultralytics defaults apply: conf=0.25, iou=0.7, imgsz=640. Every box from 0.25 upward is serialised and returned, and the 0.35 rule lives only in the three consumers. The sibling service does the opposite and explains why: human-detection-yolo-service/main.py:10-15 states "THE CONFIDENCE FILTER LIVES HERE, NOT IN THE BROWSER. The fire service returns every box   
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:40`, `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:10-15`, `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:33-43`
- **No single document states the arbitration rule set; it is only in code comments** — RO1.3 (documented arbitration rule set), minor  
  RO1.3's second deliverable is a "documented arbitration rule set". I grepped README.md and THESIS_CHANGES.md for 'arbitration', 'Table 3.9', 'Algorithm 2' and 'Algorithm 3': README.md has zero hits, THESIS_CHANGES.md has two, both incidental (:429 on the classifier gate lacking a stated justification, :445 a prompt inventory table). The rules themselves exist only as the code plus its comment block at escalation.js:1  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:1`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:429`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:445`
- **The 50% false-alarm reduction is measurable but no code states or checks the target** — RO1.3 (false alarms cut >= 50% vs vision-only), minor  
  RO1.3's headline number is a >=50% cut in false alarms versus vision-only. The machinery to measure it exists: metrics.py computes `false_alarm_rate`, its Wilson interval and false alarms per hour per combination (ablation-service/metrics.py:240-244) and a false_alarm_split at :359, and combos.py provides combination 2 (YOLO only, :157-192) and combination 5 (YOLO + VLM, :217-223) which is the vision-only vs with-VLM  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:240`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:359`, `fire_detection_and_classification_web_app/ablation-service/combos.py:157`
- **Censored runs are counted but not analysed as censored** — RO1.4, minor  
  Ch.3 line 687 requires runs where a configuration never alarms within the trial time to be treated as censored rather than deleted. detection_latency() does keep them visible as events_never_detected and refuses to average over survivors, which is the right instinct, but there is no censored estimator (no Kaplan-Meier, no restricted mean), so the median it reports is still a median over detected events only.  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:258`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:268`
- **Event-level CSV export can crash on an undefined rate** — RO1.4, minor  
  metrics.evaluate() returns json_safe(result), which converts every NaN to None. export_csv then calls round() on w['precision'], w['recall'], w['f1'] and w['false_alarm_rate'] unguarded, so any arm whose precision is undefined (tp+fp == 0, i.e. an arm that never fires on the selected dataset) makes round(None, 6) raise TypeError and the export returns 500. The UI tolerates nulls (num() and the false-alarms column bot  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:423`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:40`, `fire_detection_and_classification_web_app/ablation-service/runs.py:357`
- **End-to-end latency, a listed dependent variable, is not measured by the ablation** — RO1.4, minor  
  chapter_3.txt:95 lists 'end to end latency' among RO1.4's dependent variables, and chapter_3.txt:38 lists latency alongside precision, recall, mAP and time to detection. The ablation's result['timings'] is the service's own compute cost - classify_ms, score_ms, evaluate_ms (runs.py:133, 138, 162) - not the frame-to-alarm path section 3.4.6 Table 3.19 defines. The UI even prints it as 'Done in N ms' (ablation.html:434  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:95`, `fire_detection_and_classification_web_app/ablation-service/runs.py:133`, `fire_detection_and_classification_web_app/ablation-service/runs.py:162`
- **Industrial's 6 m hazard radius carries no written justification** — RO2.2, minor  
  Q1, field-by-field. home.json has a `hazardRadiusNote` at line 12 giving a full paragraph of reasoning for 2.0 m ('The rooms here are about 3 m across, so a 6 m radius would reach every room from anywhere'). industrial.json has `hazardRadiusM: 6.0` at line 11 and NO note - `grep -n hazardRadiusNote` finds it only in home.json. sites.py never reads the field (it is documentation), and the README table at sites/README.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/home.json:11-12`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:11`, `fire_detection_and_classification_web_app/alert-service/sites/README.md:8-11`
- **Only two blocked-exit combinations are tested; the thesis claims at least eight** — RO2.2, minor  
  chapter_3.txt:610 states 'At least eight combinations of fire location and blocked exit are tested. We chose the combinations on purpose rather than at random.' In test_routing.py only two tests pass `blocked=`: test_s4 blocks exit-south (line 107) and test_s5 blocks both (line 115). The parametrised sweeps at lines 28-55 cover every fire/occupant pair but always with `blocked=()`. No industrial test uses a blocked e  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:610`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:106-120`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:143-155`
- **Industrial ground truth covers 3 of 7 zones** — RO2.2 / §3.4.8, minor  
  industrial.json:347-363 declares groundTruth for fabric-store, dyeing and boiler only; cutting-floor, warehouse, finishing and sewing-a have none. The analysis endpoint sets `refusal = "n/a"` and skips the optimality gap for any zone with no ground truth (app.py:300, 306), so incidents in four of the seven industrial zones contribute nothing to §3.4.8 beyond validity. home.json:324-361 covers all 8 of its zones, so t  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:347`, `fire_detection_and_classification_web_app/alert-service/app.py:300`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:324`
- **The safety officer's screens never show the check-out count anywhere** — RO2.3, minor  
  Searched frontend/static/index.html, reports.html and js/*.js for `checkedOut|checkout|unaccounted|peakOccupancy` - zero matches. The incident report page shows only the derived muster line. So the only places the two counts appear together are the JSON from /api/incidents/{id}/report and the Flutter report screen. Ch.3 line 250 requires the alert service to keep both counts (it does), and s3.4.8 requires them side b  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/reports.html:332`, `fire_detection_and_classification_web_app/frontend/static/index.html:1657`, `fire_detection_and_classification_web_app/alert-service/serializers.py:399`
- **No test pins the served table to Table 3.11** — RO3.2, minor  
  The only automated check on the guidance table is test_api.py:156, which asserts that the key 'fuels' is present in the /api/extinguishers response. Nothing asserts which classes exist, which agents each carries, that every do_not_use entry has a 'why', or that no_fire is absent. The Flutter test at severity_test.dart:114-131 tests the PARSER against a handwritten fixture, not against the real backend table. A ten-li  
  Evidence: `fire_detection_and_classification_web_app/alert-service/test_api.py:156`, `fire_notification_and_evacuation_mobile_app/test/severity_test.dart:114`
- **No test checks the table against Table 3.11** — RO3.2, minor  
  The only test touching the guidance table asserts that the key 'fuels' is present in the /api/extinguishers response. Nothing asserts that all three classes exist, that each has a non-empty first_action, use and do_not_use, or that the agent lists match Table 3.11. A silent edit to any agent list would pass the suite.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/test_api.py:156`
- **The web dashboard has no idea which site is running** — RO3.3, minor  
  Q3, dashboard half. The dashboard never calls /api/site/plan or /api/state - searched frontend/static/index.html, frontend/static/js/*.js and frontend/server.py for `sitename`, `site_name`, `sitekey`, `facility` and `api/site` (case-insensitive): no matches. Its only alert-service calls are /api/events/fire, /api/events/warning, /api/events/clear, /api/events/classification and /api/extinguishers (index.html:1647, 16  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1647-1672`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:184-358`, `fire_detection_and_classification_web_app/alert-service/serializers.py:427-433`
- **Presentation A baseline is unimplemented, and correctly so — its three fields already exist** — RO3.4, minor  
  `grep -rniE "presentation a|presentation b|baseline presentation|conventional alarm"` across all six directories returns only three prose lines (mobile README.md:42 and THESIS_CHANGES.md:336,559) and no implementation. That is the right call: §3.3.8 defines Presentation A completely as "A conventional alarm presentation, giving only the zone, the device and the time" (chapter_3.txt:622), and all three fields are alre  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:622`, `fire_detection_and_classification_web_app/alert-service/serializers.py:45`, `fire_detection_and_classification_web_app/alert-service/serializers.py:65`
- **No Likert capture and no non-parametric analysis code, which is the right boundary** — RO3.4, minor  
  §3.4.9 requires Likert medians and frequency distributions, a Wilcoxon signed rank paired comparison of Presentation A vs B, and six-phase Braun-and-Clarke thematic analysis with a retained code book (chapter_3.txt:740-741). None of this exists in code: `grep -rniE "wilcoxon|friedman|mann.?whitney|kendall|bonferroni|scipy\.stats"` over all *.py, *.dart and *.js in all four repos returns ZERO hits — the only matches o  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:740`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:741`, `fire_detection_and_classification_web_app/alert-service/db.py:83`

### Mobile app (7)

- **With no generated route the app still draws a hard-coded stock route as the safe route** — RO2.3, major  
  When routing fails or an old record has no route, incident_screen passes route: null to the LocatorCard but keeps mode incidentRoute. In the painter _incident is true and _hasPath is `_incident && !(route?.isRefuge ?? false)` = true, so it draws _line = plan.defaultRoute, YOU at plan.youAt, the fire at plan.fireAt and the muster at plan.musterAt - all const data compiled into the app (home: defaultRoute at floor_plan  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/features/incident/incident_screen.dart:170`, `fire_notification_and_evacuation_mobile_app/lib/features/incident/incident_screen.dart:174`, `fire_notification_and_evacuation_mobile_app/lib/shared/floor_plan/floor_plan_painter.dart:45`
- **One failure in getToken() also kills foreground alerts and tap handling** — RO2.3, major  
  NotificationService.init wraps everything in a single try/catch (notification_service.dart:113-152). The token fetch is at line 130, but FirebaseMessaging.onMessage.listen(_onForeground) is at line 141, onMessageOpenedApp at 144 and getInitialMessage at 145 — all AFTER it. If getToken() or requestPermission() throws (no Play Services, no network at startup, a Firebase project misconfiguration), control jumps to the c  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/core/notifications/notification_service.dart:113`, `fire_notification_and_evacuation_mobile_app/lib/core/notifications/notification_service.dart:130`, `fire_notification_and_evacuation_mobile_app/lib/core/notifications/notification_service.dart:141`
- **The confirmation screen can show 0 check-outs right after a successful check-out** — RO2.3, major  
  ackSafe discards the count the backend returns (api_client.dart:48-57 returns int?, api_fire_repository.dart:206 ignores it) and instead calls refresh(), which reads /api/state (api_fire_repository.dart:213, 108). /api/state serves only the latest ACTIVE incident (app.py:196-200, db.py:436-441), and the watchdog resolves an incident after CLEAR_AFTER_SECONDS=30 with no fresh event (intake.py:23, 496-506). Once that h  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:206`, `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:240`, `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:300`
- **Occupant phone never shows any 'do not use' agent or reason** — RO3.2, major  
  GuidanceCard renders only the one-line 'short' string, the label and the class letter - no first action, no agent list, no prohibition, no reason. For solid_combustible the short string is 'Water or foam is suitable for this fuel.' (extinguishers.py:108), which contains no prohibition at all, so a phone user on a Class A fire receives zero of Table 3.11's last column. The parser also throws the reason away: _agents()  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/features/incident/widgets/guidance_card.dart:60`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:375`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:108`
- **Phone parses the agent lists then never shows them** — RO3.2, major  
  FireClassification.fromJson populates firstAction, useAgents and avoidAgents from the backend response. grep over lib/ and test/ shows the only other references are the constructor defaults, the field declarations and two assertions in severity_test.dart — no widget reads them. GuidanceCard renders only classification.guidance (the one-sentence `short`), the label and the class letter. So the occupant on the phone is  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:349-352,362-364,391-393`, `fire_notification_and_evacuation_mobile_app/lib/features/incident/widgets/guidance_card.dart:60-72,96-99`, `fire_notification_and_evacuation_mobile_app/test/severity_test.dart:129-130`
- **Mock mode shows no situation report, so the app cannot be demonstrated offline** — RO3.1, minor  
  grep for 'situationReport|SituationReport|ReportClaim' over lib/data/mock/mock_data.dart and lib/data/api/api_fire_repository.dart returns zero hits; only incident_screen.dart:161-162 consumes it. MockData never constructs a SituationReport, so Incident.situationReport is null in mock mode and the card is skipped by the null-guard at incident_screen.dart:161. Only the widget test builds one by hand (situation_report_  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/features/incident/incident_screen.dart:161`, `fire_notification_and_evacuation_mobile_app/test/situation_report_test.dart:16`
- **Phone never receives or shows the live-electrical caution** — RO3.2, minor  
  UNIVERSAL_CAUTIONS is attached by guidance_for under the key universal_cautions and rendered by both web pages. grep for 'universal_cautions|universalCautions' across the Flutter lib/ returns nothing, and FireClassification.fromJson does not read the key. The 'if anything nearby is still energised, use CO2 or dry powder only — never water or foam' warning therefore reaches the safety officer's screen but never the oc  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:114-130,138`, `fire_detection_and_classification_web_app/frontend/static/index.html:2265-2266`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:386-393`

### ESP32 sensor node (11)

- **No working hardware firmware: mock mode is on in every config copy, including the private one** — RO1.1, blocking  
  RO1.1's deliverable is 'a working sensor node'. MOCK_MODE is 1 in the committed template (config.example.h:61), in the local config (config.h:53) AND in the private deployment copy used for the real demo (firewatch-private-files/config-sensor-node.h:53). The folder itself is named sensor_node_mock and the README's second paragraph says 'It ships in mock mode' (README.md:13). The readings are a mean-reverting random w  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/config.example.h:61`, `esp_32_sensor_network_code/sensor_node_mock/config.h:53`, `firewatch-private-files/config-sensor-node.h:53`
- **DHT22 is never read even with MOCK_MODE 0 - the two lines are comments** — RO1.1, blocking  
  readRealSensors() reads MQ-2 (ino:133), MQ-7 (ino:134) and the flame DO (ino:139), but the DHT22 lines are commented out: '// #include <DHT.h>; DHT dht(PIN_DHT22, DHT22); ... // tempC = dht.readTemperature(); humPct = dht.readHumidity();' (ino:141-142). With MOCK_MODE 0 the mock stepper is compiled out (ino:302-306), so tempC and humPct stay at their file-scope initialisers 28.0f and 62.0f (ino:75) forever - and they  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:131`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:141`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:75`
- **No bill of materials exists anywhere in the four repos** — RO1.1, blocking  
  RO1.1's deliverable is 'a working sensor node with a documented bill of materials' (chapter_1_and_2.txt:49); the thesis promises it twice more (chapter_3.txt:80, and Table 3.12's data column at chapter_3.txt:364). I searched the entire tree twice: rg -ni 'bill of materials|\bBOM\b|parts list|component list|purchase|datasheet' and grep -ril 'bill of material' — zero hits outside the thesis text. All 16 markdown files   
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:49`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:364`, `esp_32_sensor_network_code/README.md:226`
- **DHT22 is never read: real mode reports frozen 28.0 C and 62 %RH** — RO1.1, blocking  
  readRealSensors() (sensor_node_mock.ino:131-144) reads the two MQ analog pins and the flame DO, but the DHT22 is two comment lines — 'tempC = dht.readTemperature(); humPct = dht.readHumidity();' (ino:141-142) — and no DHT library is included (ino:34-35 is only WiFi.h and HTTPClient.h). With MOCK_MODE 0, stepMockSensors() is skipped (ino:302-306), so tempC and humPct keep their initialisation values 28.0 and 62.0 (ino  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:131`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:141`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:75`
- **Only a mock node is shipped; no evidence a hardware node ever ran** — RO1.1, blocking  
  RO1.1's deliverable is 'a working sensor node'. There is exactly one sketch in the repo (find over esp_32_sensor_network_code: sensor_node_mock/sensor_node_mock.ino, 311 lines) and it is named, foldered and headed as a mock ('mock telemetry over Wi-Fi', ino:2; 'Simulates the four modules in diagram.png', ino:4). MOCK_MODE is 1 in all three config copies that exist — the committed template (config.example.h:61), the l  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:2`, `esp_32_sensor_network_code/sensor_node_mock/config.example.h:61`, `firewatch-private-files/config-sensor-node.h:53`
- **Real ADC counts are discarded: mq2_raw, mq7_raw and flame_raw are all fabricated** — RO1.1, major  
  postReadings() always sends mockRaw(mq2Ppm, 2000.0f) and mockRaw(mq7Ppm, 500.0f) (ino:193-194), which back-computes raw from ppm as ppm/fullScale*4095 (ino:117-121). The genuine analogRead values in readRealSensors() are locals that are thrown away (ino:133-134). flame_raw is the literal pair 400 / 3900 (ino:195); PIN_FLAME_AO on GPIO 32 is never analogRead for a measurement, only as a random seed (ino:286). This mat  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:193`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:117`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:286`
- **No bill of materials exists, although the thesis promises one three times** — RO1.1, major  
  The BOM is named as an RO1.1 deliverable in Ch1 line 49, as a Chapter 6 communication output in Ch3 line 80, and as the data collected for RO1.1 in Table 3.12 (Ch3 line 364). I searched all four repos plus firewatch-ngrok-files and firewatch-private-files with grep -rniE 'bill of material|\bBOM\b|parts list|components|quantity' over *.md, *.py, *.ino, *.h, *.dart, *.html, *.js - zero matches for a BOM. What exists in  
  Evidence: `esp_32_sensor_network_code/README.md:226`, `esp_32_sensor_network_code/README.md:243`, `esp_32_sensor_network_code/diagram.png`
- **No bill of materials anywhere in the repo** — RO1.1, major  
  RO1.1's stated deliverable is "a working sensor node with a documented bill of materials" (chapter_1_and_2.txt:49), repeated at chapter_3.txt:80 and listed as a deliverable at chapter_3.txt:364. I ran grep -rni "bill of material|\bBOM\b|part number|supplier|quantity" over every .md, .h, .ino and .py in this repo: zero hits. README Table 6 (README.md:226-234) is a pin map, not a bill of materials: five rows of module-  
  Evidence: `esp_32_sensor_network_code/README.md:226`, `chapter_1_and_2.txt:49`, `chapter_3.txt:80`
- **No warm-up gate or clean-air calibration in code, although Table 3.15 makes both a procedure** — RO1.1, minor  
  Ch3 Table 3.15 requires MQ-2 'a warm up period of at least 24 hours before first use, and 3 minutes after each power cycle' and MQ-7 'Calibrated in clean air before each session; drift is recorded', and Ch3 line 505 requires the calibration values to be logged with the data. The firmware has neither: setup() ends with lastPostAt = millis() - POST_INTERVAL_MS with the comment 'post immediately on boot' (ino:290), so t  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:290`, `esp_32_sensor_network_code/README.md:247`, `fire_detection_and_classification_web_app/ablation-data/README.md:39`
- **Mock sender and sketch only ship the home zone list** — RO1.1, minor  
  tools/mock_sender.py:42-46 hard-codes `ZONES = ["kitchen", "dining", "living", "verander", "bedroom-west", "bedroom-southwest", "bedroom-northeast", "bedroom-southeast"]` with the comment 'Swap these for the industrial ids when the web app runs the demo hall'. There is no --site or --zone argument - the full argparse list is --url, --key, --nodes, --interval, --scenario, --hold, --timeout (lines 121-129). Both config  
  Evidence: `esp_32_sensor_network_code/tools/mock_sender.py:42-46`, `esp_32_sensor_network_code/tools/mock_sender.py:121-133`, `esp_32_sensor_network_code/sensor_node_mock/config.h:40`
- **No RO1.4 code in the three non-web repos, including the sensor log RO1.4 needs** — RO1.4, minor  
  grep -ril 'ablation|vision-only|sensor-only|sensor only' over esp_32_cam_code, esp_32_sensor_network_code and fire_notification_and_evacuation_mobile_app returns four hits, all in the mobile app and all unrelated prose about a sensor-only alarm having no confidence percentage (detection_panel.dart:13, models.dart:760, dashboard_screen.dart:102, api_fire_repository.dart:260). Nothing in the ESP32 firmware logs a trial  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/features/incident/widgets/detection_panel.dart:13`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:760`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:234`

### ESP32-CAM (4)

- **No bill of materials for the camera unit, which the thesis promises twice** — RO1.1, major  
  chapter_3.txt:80 lists "the documented bill of materials" among the study's deliverables and chapter_3.txt:364 repeats "Sensor logs from the trials, bill of materials". I grepped README.md for 'bill of materials', 'BOM' and 'part number' - zero hits. The nearest thing is the prose requirements list at README.md:98-103, which names the board, the camera module, an ESP32-CAM-MB or USB-serial adapter and a 5 V >= 500 mA  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:80`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:364`, `esp_32_cam_code/README.md:98`
- **Mounting geometry and the reference photograph the protocol depends on are absent** — RO2.1, minor  
  chapter_3.txt:132 specifies "one fixed camera at a raised position"; chapter_3.txt:525 gives the test room as a garage about 4 m by 5 m with a 3 m ceiling and "a camera at a raised position looking down on the floor"; chapter_3.txt:556 makes the trial protocol "verify the camera position against the reference photograph of the room". git ls-files returns exactly two images in this repo and I opened both: diagram.png   
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:132`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:525`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:556`
- **The 2 Hz target is met elsewhere and this repo says nothing about it** — RO1.2, info  
  chapter_3.txt:700 reports "frames per second, against the target of 2 Hz". The firmware fixes VGA / quality 12 / fb_count 2 at .ino:271 and the stream loop at .ino:141-175 has no delay, so the board produces frames as fast as the sensor and TCP backpressure allow. The rate is set entirely on the other side: DETECT_INTERVAL_MS = 500 at fire_detection_and_classification_web_app/frontend/static/index.html:1130, used at   
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:700`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:271`, `fire_detection_and_classification_web_app/frontend/static/index.html:1130`
- **RO1.2 lives in one service only; the other three repos hold nothing for it** — RO1.2, info  
  Tracing RO1.2 across all four repos: fire_detection_and_classification_web_app holds the model, the service, the 0.35 gate and the two label adapters. esp_32_cam_code contributes only the frame source - esp32cam_stream_v2_final_working_code_via_wifi.ino:271 initialises PIXFORMAT_JPEG at FRAMESIZE_VGA (640x480, matching the training imgsz of 640) with jpeg_quality 12, falling back to RGB565 at QVGA and QQVGA (lines 27  
  Evidence: `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:271`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:277`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:283`

### Across repos (2)

- **The live check-out display resets to zero 30 s after the last event** — RO2.3, major  
  The /resolved screen reads RepositoryScope.of(context).activeIncident.checkout. The watchdog auto-clears an incident after CLEAR_AFTER_SECONDS = 30 s with no fresh event, after which /api/state returns activeIncident null and _applyState replaces _active with _placeholder(), whose checkout is the default CheckoutRoll (checkedOut 0, peakOccupancy null). Within one 15 s poll the occupant's screen flips from "Checked ou  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/features/resolved/resolved_screen.dart:62`, `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:241`, `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:301`
- **Without an FCM token a check-out is silently not counted at all** — RO2.3, major  
  ackSafe uses the FCM token as the identity; when _token is null it falls back to _api.ackIncident(id) instead (api_fire_repository.dart:203-209). That hits POST /api/incidents/{id}/ack with no body, so token is '' and the handler calls bump_muster, NOT record_checkout (app.py:382-397, db.py:654-658). bump_muster increments the synthetic muster_present toward muster_total, seeded from DEFAULT_MUSTER_PRESENT=42 / DEFAU  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:203`, `fire_detection_and_classification_web_app/alert-service/app.py:382`, `fire_detection_and_classification_web_app/alert-service/db.py:654`

## Mismatches — code and thesis disagree

Both sides exist but they do not say the same thing. Most of these are closed by correcting the thesis text rather than the code. `fire_detection_and_classification_web_app/THESIS_CHANGES.md` already tracks eighteen of them.


### Web app (97)

- **Flame channel graded danger; Table 3.8 says warn, never danger** — ALG1, blocking  
  Table 3.8 (chapter_3.txt:262 onward) gives the flame row as: warn threshold = "Flame signal present", danger threshold = "Not used", with the reason "A flame signal alone is graded warn, because sunlight, lamps and hot surfaces can also trigger it, so this channel never reaches danger on its own". The code does the opposite: esp32-sensor-service/main.py:148 sets level = "danger" whenever flame is truthy, and the comm  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:143`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:148`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:53`
- **Dashboard hard-codes an industrial zone while the default site is home** — ARCH, blocking  
  The dashboard reports every event for a fixed zone: const CAMERA_ZONE_ID = 'fabric-store' (index.html:1135), also the default in escalation.js:49. 'fabric-store' exists only in sites/industrial.json:15. But SITE_KEY defaults to home in docker-compose.yml:165 and is set to home in all three .env copies (.env:24, sample.env:24, firewatch-private-files/.env:24), and home.json's zones are kitchen/dining/living/verander/4  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1135`, `fire_detection_and_classification_web_app/docker-compose.yml:165`, `fire_detection_and_classification_web_app/.env:24`
- **Shipped model records mAP@0.5 = 0.84635, below the 0.85 target** — RO1.2, blocking  
  The thesis target is stated at chapter_1_and_2.txt:50 - "a mean average precision at an intersection over union of 0.5 of at least 0.85". The shipped checkpoint carries its own recorded metrics inside the pickle. I unpickled archive/data.pkl from best.pt with a stub-class Unpickler (read-only, script at /private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (embedded train_metrics block in archive/data.pkl)`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:50`
- **Shipped model scores mAP@0.5 = 0.84635 against a required 0.85** — RO1.2, blocking  
  Thesis: "achieving a mean average precision at an intersection over union of 0.5 of at least 0.85" (chapter_1_and_2.txt:50). Code: best.pt's train_metrics records metrics/mAP50(B) = 0.84635, metrics/mAP50-95(B) = 0.5214, precision 0.85096, recall 0.77664. Required 0.85, delivered 0.84635 - short by 0.00365, i.e. 0.4 % relative. The objective as written is not met by the artefact that ships, and the gap is small enoug  
  Evidence: `thesis/chapter_1_and_2.txt:50`, `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (archive/data.pkl: train_metrics['metrics/mAP50(B)'] = 0.84635)`
- **README claims the alarm is kept when the VLM is unreachable; the code does not keep it** — RO1.3 / Alg.2, blocking  
  README.md:24-26 states: 'If it cannot be reached, an existing alarm is kept and the incident records that verification was unavailable.' The second half is true (verification:'unavailable' is stored and displayed). The first half is not: with sensors at normal, decide() returns 'clear' and sendClear() resolves the incident, as traced in the latch finding. The same overclaim sits in the in-file comment at escalation.j  
  Evidence: `fire_detection_and_classification_web_app/README.md:26`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:146`, `fire_detection_and_classification_web_app/frontend/static/index.html:1789`
- **Every home route hides a first leg that passes through the hazard** — RO2.2 / Alg.4, blocking  
  routing.py:195-210: when the occupant node is inside the hazard radius the origin is re-anchored to the first reachable node outside it, and that search runs over the UNPRUNED graph (`_dijkstra(site.adj, from_node)`, line 196). The resulting `path_nodes` starts at the re-anchored node, so the walk the occupant must actually make is not in the record. `_assert_clear` (routing.py:289) and `hazard_intersects` (routing.p  
  Evidence: `fire_detection_and_classification_web_app/alert-service/routing.py:195`, `fire_detection_and_classification_web_app/alert-service/routing.py:289`, `fire_detection_and_classification_web_app/alert-service/routing.py:356`
- **The officer's report page shows a synthetic 42-of-45 muster instead of the check-out count** — RO2.3, blocking  
  reports.html renders `${r.muster.present} of ${r.muster.total} accounted for (${r.muster.source})`. muster_json returns the stored synthetic constants when occupancy_peak is null, and create_incident writes DEFAULT_MUSTER_PRESENT = 42 and DEFAULT_MUSTER_TOTAL = 45 into every new incident. So an incident where the human detector never reported prints "42 of 45 accounted for (estimated)" on the incident report page - i  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/reports.html:332`, `fire_detection_and_classification_web_app/alert-service/serializers.py:76`, `fire_detection_and_classification_web_app/alert-service/serializers.py:102`
- **Solid combustible 'do not use' is CO2, but Table 3.11 says water near live electrics** — RO3.2, blocking  
  Thesis Table 3.11 row 'Solid combustible', agents that must not be used: 'Water near live electrical equipment, because of the risk of electric shock'. Code instead lists CO2, 'Knocks the flames down without cooling, so deep-seated material reignites' — a prohibition the thesis never states, replacing the one it does. Worse, it contradicts the code's own UNIVERSAL_CAUTIONS[0], which says that near live equipment you   
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:104-107`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:114-122`, `fire_detection_and_classification_web_app/frontend/static/index.html:2252-2266`
- **Thesis claims PVC is a tested guidance material; the code treats it as never seen** — RO3.2, blocking  
  Ch3 line 510 assigns PVC to the solid combustible training class ('cellulose ... and PVC (C2H3Cl, representing cable insulation) for the solid combustible class'), and line 554 states 'the fire classification service and the guidance mapping are tested with the synthetic CFAST data ... which includes propane, heptane and PVC fuels'. The shipped ood_split describes itself as '90 experiments burning three fuels the mod  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/runs.py:55-66,173-181`, `scratchpad/thesis/chapter_3.txt:510,554`
- **Zone aggregation runs in the browser, not on the server** — ALG1, major  
  chapter_3.txt:190 states "The server grades each reading as normal, warn or danger, and the zone takes the worst level of its nodes (Algorithm 1)", and the pseudocode at chapter_3.txt:260 puts the "// zone aggregation" block before the "// on the dashboard, every 2 s" block - only the 3-poll acceptance is on the dashboard. In the code only per-channel grading and per-node worst-of are server-side (esp32-sensor-servic  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:78`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:253`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:190`
- **Three of ten services have no place in Table 3.7** — ARCH, major  
  Table 3.7 (chapter_3.txt:236-253) names its components explicitly, and three running services are absent from it. nginx (HTTPS reverse proxy) and frontend (dashboard server plus the /api/detect, /api/describe, /api/describe-scene, /api/warn fan-out proxy) are load-bearing - remove either and the dashboard cannot capture a frame - yet the thesis mentions no proxy, no TLS and no backend-for-frontend; grep of both chapt  
  Evidence: `fire_detection_and_classification_web_app/docker-compose.yml:76-90`, `fire_detection_and_classification_web_app/docker-compose.yml:118-143`, `fire_detection_and_classification_web_app/docker-compose.yml:177-196`
- **Sensor service grades flame as danger; Table 3.8 says flame never reaches danger** — ARCH, major  
  Table 3.8's flame row (chapter_3.txt:279-282) gives warn threshold "Flame signal present", danger threshold "Not used", and states "A flame signal alone is graded warn ... so this channel never reaches danger on its own". esp32-sensor-service does the opposite: the flame tile's level is "danger" whenever flame is truthy, with an in-code comment asserting the opposite rule - "Any flame at all is a danger - there is no  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:143-149`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:186-190`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:81-88`
- **Ablation service runs six combinations; the thesis specifies four** — ARCH, major  
  RO1.4 and chapter_1_and_2.txt:52 / chapter_3.txt:94 fix the independent variable at four levels: sensor only, vision only, sensor and vision fusion, and full with VLM verification. ablation-service defines six: COMBOS = {1 sensors only, 2 YOLO only, 3 VLM only, 4 sensors + YOLO, 5 VLM + YOLO, 6 sensors + YOLO + VLM}, with a modality matrix for each. Mapping the thesis onto these gives 1, 2, 4 and 6; combination 3 (VL  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/constants.py:141-161`, `fire_detection_and_classification_web_app/ablation-service/constants.py:214-236`, `fire_detection_and_classification_web_app/docker-compose.yml:118-121`
- **Worst-of runs over every node the service knows, not over one zone** — Alg.1 (zone aggregation), major  
  Alg.1 says 'Z <- worst(L[n] over the nodes of the zone)'. `/api/sensors/latest` returns EVERY node it has ever heard from, with no zone filter and no zone query parameter (esp32-sensor-service/main.py:253-268). `onSensors` then takes the worst level across `payload.nodes` wholesale (escalation.js:81-88) and reports the outcome under the module-level `zoneId: 'fabric-store'` (escalation.js:49), matching the hard-coded  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:253`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:180`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:81`
- **Dashboard clear resolves an incident in seconds, not after the thesis's 30 s** — Alg.2 (30 s to clear), major  
  Thesis Alg.2: 'no new event for 30 s -> CLEAR'. The 30 s exists as `CLEAR_AFTER_SECONDS = 30` in the watchdog (intake.py:23, 365-372), but the dashboard never lets it run. The detection loop declares vision quiet after `DETECTION_HOLD_MS = 2500` (index.html:1133, 1809); the ladder then drops to 'clear' and posts `/api/events/clear` on the falling edge (escalation.js:168, 286-291). `handle_clear` calls `mark_incident_  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1133`, `fire_detection_and_classification_web_app/frontend/static/index.html:1809`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:168`
- **Four states collapse to two, and gas danger is labelled YOLO+VLM confirmed fire** — Alg.2 / RO3.3 (current state), major  
  Alg.2 has four states CLEAR / GAS WARNING / GAS DANGER / FIRE CONFIRMED, and escalation.js computes all four ('clear' | 'warning' | 'danger' | 'fire', escalation.js:142-157). The screen has only two. `render()` branches on the boolean `S.fireAlarm` alone (index.html:1968-1984), and `S.fireAlarm = st.alarm` is true for BOTH 'fire' and 'danger' (escalation.js:164, index.html:2278). So a tier 1b gas-danger alarm - nothi  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:142`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:164`, `fire_detection_and_classification_web_app/frontend/static/index.html:1278`
- **The VLM-only arm is YOLO-gated, contradicting the rule the page prints** — Alg.3, major  
  constants.py:220 prints, and /api/ablation/config serves to the page, that arm 3 is 'Invoked on a FIXED 4s cadence, never on the YOLO gate -- a VLM-only arm that waited for YOLO would not be VLM-only'. VlmHold.due() supports that (gated=True unconditionally), but recordings.build_frame creates exactly ONE VlmHold per recording and calls hold.due(gated=bool(vis['yolo_detected'])) - so on a real recording the VLM is on  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/constants.py:220`, `fire_detection_and_classification_web_app/ablation-service/vlm_adapter.py:165`, `fire_detection_and_classification_web_app/ablation-service/recordings.py:148`
- **Two unreconciled home/industrial axes with opposite defaults** — Alg.3 / RO1.3, major  
  Q6, the real duplicated site logic. Axis A is SITE_KEY: chooses the zone catalogue and the evacuation graph, default `home` (sites.py:34, docker-compose.yml:165). Axis B is the dashboard's `detect-mode` selector, labelled 'Industrial setting' / 'Home demo' (index.html:886), which chooses the VLM prompt clause and is persisted in the browser's localStorage under 'firewatch.detectMode' with default `industrial` (index.  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:879-890`, `fire_detection_and_classification_web_app/frontend/static/index.html:1568-1607`, `fire_detection_and_classification_web_app/vlm-service/main.py:66-80`
- **System claims 7-8 detectors; the thesis scopes ONE monitored zone** — Ch.3 s3.2.1 scope, major  
  Q5 answered. chapter_3.txt:132 states the scope as 'One monitored indoor zone, observed by one fixed camera at a raised position and one fixed multi sensor node.' Both site files give EVERY zone its own `detector_id`: home.json has Detector 01-08 across 8 zones (lines 14-71), industrial.json has Detector 01-07 across 7 zones (lines 13-63). zones_seed.py:24 feeds those straight into ZONES, serializers.py:429 publishes  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:132`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:14-71`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:13-63`
- **Default site is home while the thesis scope is industrial** — Ch.3 s3.2.1 scope, major  
  sites.py:34 defaults SITE_KEY to 'home', docker-compose.yml:165 to 'home', .env:24 and sample.env:24 both set 'home', zones_seed.py:5-6 documents home as the default, and api_fire_repository.dart:35 / fire_repository.dart:46 both default the phone to 'home'. The thesis scope is industrial (chapter_3.txt:132), with home meaning only the HomeFire dataset and a garage test room. The user wants both paths kept, so this i  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites.py:34`, `fire_detection_and_classification_web_app/docker-compose.yml:165`, `fire_detection_and_classification_web_app/sample.env:24`
- **Flame is graded danger; Table 3.8 says flame alone never reaches danger** — RO1.1, major  
  Table 3.8's flame row: warn threshold 'Flame signal present', danger threshold 'Not used', because 'a flame signal alone is graded warn ... so this channel never reaches danger on its own' (chapter_3.txt:282). The service does the opposite: the flame tile is 'danger' whenever flame is 1, with the comment 'Any flame at all is a danger — there is no warn' (main.py:142-148). Because the node level is the worst channel (  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:282`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:142`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:173`
- **Flame channel graded danger, but Table 3.8 says it never reaches danger alone** — RO1.1, major  
  Table 3.8 (chapter_3.txt:262 onward) states for the infrared flame channel: warn threshold "Flame signal present", danger threshold "Not used", with the reason "A flame signal alone is graded warn, because sunlight, lamps and hot surfaces can also trigger it, so this channel never reaches danger on its own". esp32-sensor-service/main.py:148 grades it `"danger" if flame_on else "normal"`, and the comment on :143 state  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:143`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:148`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:172`
- **Flame is graded danger in code; Table 3.8 says it can never reach danger on its own** — RO1.1 / Alg.1, major  
  Thesis Table 3.8, flame row: warn threshold = 'Flame signal present', danger threshold = 'Not used', with the reason 'A flame signal alone is graded warn, because sunlight, lamps and hot surfaces can also trigger it, so this channel never reaches danger on its own.' The code does the opposite: main.py:148 sets 'level': ... ('danger' if flame_on else 'normal'), with the comment on main.py:143 'Any flame at all is a da  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:143`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:148`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:174`
- **Thesis says classes flame and smoke; model emits fire and smoke** — RO1.2, major  
  The thesis says the classes are flame and smoke in three places: chapter_3.txt:191 ("The fire detection model looks for flame and smoke"), chapter_3.txt:469 (Table 3.14: "classes: flame and smoke") and chapter_3.txt:474 ("bounding boxes for two classes, flame and smoke"). The checkpoint's names dict is {0:'fire', 1:'smoke'}. The dashboard is tolerant - index.html:1629 tests label.includes('fire') || label.includes('f  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/vision.py:24`, `fire_detection_and_classification_web_app/frontend/static/index.html:1629`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:474`
- **RO1.2 promises an indoor industrial test set that does not exist** — RO1.2, major  
  chapter_1_and_2.txt:50 requires mAP >= 0.85 "on a held out indoor industrial test set". chapter_3.txt:476 states plainly that no industrial imagery could be obtained, and chapter_3.txt:474 and 469 put the model on the HomeFire home-fire dataset. The checkpoint confirms it: the data config is fire_research/dataset/data.yaml with two classes fire and smoke, and nothing industrial appears anywhere. The repo already carr  
  Evidence: `fire_detection_and_classification_web_app/THESIS_CHANGES.md:256`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:50`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:476`
- **Incident confidence is a hard-coded 0.9, not the YOLO box score** — RO1.2, major  
  escalation.js:240 sends `confidence: tier === 'danger' ? 0.0 : (vlm.confidence || 0.9)` to /api/events/fire, and escalation.js:228 does the same for the scene report. But /describe-image/ returns exactly {description, detected, type} - vlm-service/main.py:102 defines that JSON contract in the prompt, main.py:323 returns those keys, and main.py:145 and :401 both state the shape is fixed because "the live alarm depends  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:238-241`, `fire_detection_and_classification_web_app/vlm-service/main.py:102`, `fire_detection_and_classification_web_app/vlm-service/main.py:145`
- **Model class is named 'fire'; the thesis says 'flame' three times** — RO1.2, major  
  The checkpoint's names are {0:'fire', 1:'smoke'}. The thesis says flame: chapter_3.txt:191 "The fire detection model looks for flame and smoke", chapter_3.txt:469 "(classes: flame and smoke)", chapter_3.txt:474 "bounding boxes for two classes, flame and smoke". This is not only cosmetic: fire-classification-service/vision.py:24 hard-codes `FIRE_LABELS = {"fire"}` and its loop at line 68-69 does `else: continue`, so a  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (archive/data.pkl: names={0:'fire',1:'smoke'})`, `thesis/chapter_3.txt:191`, `thesis/chapter_3.txt:469`
- **RO1.2 claims an indoor industrial test set that does not exist** — RO1.2, major  
  chapter_1_and_2.txt:50 requires the 0.85 figure "on a held out indoor industrial test set". The model was trained and validated on the HomeFire dataset (chapter_3.txt:466-474: 6,500 images of indoor DOMESTIC fires), and the thesis itself concedes at chapter_3.txt:673 "No industrial test set is available, so these results show performance on home and crowd scenes, not on industrial scenes". The artefact agrees with s3  
  Evidence: `thesis/chapter_1_and_2.txt:50`, `thesis/chapter_3.txt:673`, `thesis/chapter_3.txt:474`
- **Every fire incident records confidence 0.9, a literal, not the box confidence** — RO1.3 / Alg.2, major  
  Algorithm 2's input is 'fire boxes B with confidence >= 0.35'. sendFire posts confidence: vlm.confidence || 0.9 at escalation.js:241 (and again at :228). /describe-image/ never returns a confidence field - its response is exactly {description, detected, type, mode} (vlm-service/main.py:323-324) - so vlm.confidence is always undefined and the stored value is always the literal 0.9. The real maximum box confidence is c  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:241`, `fire_detection_and_classification_web_app/vlm-service/main.py:323`, `fire_detection_and_classification_web_app/frontend/static/index.html:1643`
- **The live path clears in about 7 s, not the thesis's 30 s** — RO1.3 / Algorithm 2 (30 s clear), major  
  Thesis: "if no new event for 30 s: S' <- CLEAR". Code: the dashboard drops its boxes after DETECTION_HOLD_MS = 2500 ms of no YOLO hit (index.html:1133, :1808-1809), which pushes yoloHit:false into the ladder; decide() returns 'clear' and evaluate() fires sendClear() (escalation.js:168, 286-291). That POST calls db.mark_incident_idle, which sets last_event_at to '1970-01-01T00:00:00Z' (db.py:499-505), so the next watc  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1133`, `fire_detection_and_classification_web_app/frontend/static/index.html:1808`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:286`
- **The ablation's combination 5 is documented as the deployed rule but is not** — RO1.3 / RO1.4, major  
  combos.py:221 docstrings combination 5 as 'VLM + YOLO - verbatim the rule the dashboard deploys today', and constants.py:242 repeats 'This is verbatim the rule the live system already runs'. The implementation is 'raw2 & confirmed' (combos.py:222-224), i.e. box AND vlm_confirmed. The deployed rule at escalation.js:148 is yoloHit && (vlmConfirmed || (!vlmAvailable && gassy)) - it also has the unavailable-plus-gas bran  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:221`, `fire_detection_and_classification_web_app/ablation-service/constants.py:242`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:148`
- **'CLEAR, verification unavailable recorded' produces the CLEAR but records nothing** — RO1.3 / Table 3.9 (normal + box + unavailable), major  
  Table 3.9 cell (Normal, fire box, model unavailable) reads "CLEAR, verification unavailable recorded". The code produces CLEAR correctly (escalation.js:148 is false because gassy is false, then :156). But nothing is recorded: no event is posted in that branch, so no row anywhere carries the fact that a box was seen and the verifier was unreachable. The only trace is a browser-session log line `[vlm error: ...]` at in  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:148`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:156`, `fire_detection_and_classification_web_app/frontend/static/index.html:1789`
- **Arbitration runs in the browser, not in the decision layer, so it stops when the tab closes** — RO1.3 / architecture Table 3.7, major  
  Table 3.7 puts escalation logic in layer 4 (Decision/application) and the dashboard in layer 5 (Presentation). Algorithm 2 is implemented entirely in layer 5: escalation.js is a classic browser script attached to window (escalation.js:30, 408-412), started from index.html:2269-2286, and fed by SensorPanel's 2 s poll (sensor-panel.js:17, 183). There is no server-side arbitration: docker-compose.yml lists ten services   
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:30`, `fire_detection_and_classification_web_app/frontend/static/index.html:2269`, `fire_detection_and_classification_web_app/frontend/static/js/sensor-panel.js:17`
- **Six arms built, four written in the thesis in four separate places** — RO1.4, major  
  RO1.4, s3.2.4 line 234, s3.3.5 line 564 and s3.3.6 line 606 all say four configurations. The code defines six (COMBOS 1-6), the API default runs all six, the UI pre-checks all six, and README Table 2 documents six. The two beyond the thesis are 3 (VLM only) and 5 (VLM + YOLO). This is a superset, not a shortfall, and THESIS_CHANGES.md:281 already records the fix - but as it stands the page a examiner opens shows six   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/constants.py:141`, `fire_detection_and_classification_web_app/ablation-service/main.py:208`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:332`
- **Fusion arm and full arm differ by model type, not only by the VLM** — RO1.4, major  
  The thesis's third configuration is 'sensor and vision fusion' and its fourth adds VLM verification, so the 4-vs-6 comparison is supposed to isolate the VLM's contribution. In code, arm 4 is a hand rule (alarm(2) AND alarm(1) within 10 windows) while arm 6 is the trained StandardScaler -> MLP(128,64) over 96 features. The manifest's feature_groups.vlm lists 11 VLM channels inside those 96, so no trained fusion model   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:203`, `fire_detection_and_classification_web_app/ablation-service/combos.py:226`, `fire_detection_and_classification_web_app/fire-classification-service/model/manifest.json:38`
- **Reported latency uses a 3 s debounce, not the dashboard's ~6 s three-poll confirmation** — RO1.4, major  
  Ch.3 line 682 states the reported time to detection 'includes the three-poll confirmation on the dashboard'. The ablation's debounce is HOLD_WINDOWS = 3 on a 1 Hz grid, i.e. 3 s. The dashboard's confirmation is STRIKES = 3 at a 2 s sensor poll, which its own comment calls '~6 s of agreement'. (The requirements brief's Alg.1 reads it as ~4 s at 2 s polling - a third number.) So a median_detection_s from this page is n  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/constants.py:77`, `fire_detection_and_classification_web_app/ablation-service/constants.py:24`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:33`
- **Repetition count: 24 simulated runs per class against 5 real runs and 'at least ten'** — RO1.4, major  
  Three numbers disagree. Ch.1 RO1.4 asks for 'at least ten repetitions of each controlled fire scenario'. Ch.3 line 97 and Table 3.16 fix five runs per scenario and record the small number as a limitation. The shipped test split has 24 experiments per fuel class (96 total, 17,280 rows). The code therefore over-satisfies both counts numerically while satisfying neither in substance, because none of the 96 is a physical  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/data/test_split.csv:1`, `fire_detection_and_classification_web_app/ablation-service/runs.py:52`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:621`
- **Reported time to detection uses a 3 s debounce, the deployed dashboard uses about 6 s** — RO1.4, major  
  chapter_3.txt:682 defines time to detection as the interval from t0 to the first alarm and states 'This interval includes the three-poll confirmation on the dashboard'. The ablation's debounce is HOLD_WINDOWS = 3 (constants.py:77) at WINDOW_HZ = 1.0 (constants.py:24), so three consecutive 1 Hz windows = 3 s. The dashboard's confirmation is STRIKES = 3 at a 2 s sensor poll, and its own comment says 'this is ~6 s of ag  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/constants.py:24`, `fire_detection_and_classification_web_app/ablation-service/constants.py:77`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:33`
- **The ablation's alarm is not the four-state arbitration the thesis defines an alarm as** — RO1.4, major  
  chapter_3.txt:682 defines the alarm as entry into GAS DANGER or FIRE CONFIRMED, and chapter_3.txt section 3.4.4 counts a false alarm the same way. Neither state exists in the ablation service: grep -rni 'FIRE_CONFIRMED|fire confirmed|GAS_DANGER|gas danger|gas warning' over ablation-service/*.py returns nothing but three unrelated uses of the word 'clears'. The ablation's alarm is argmax(p) != no_fire for the trained   
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:682`, `fire_detection_and_classification_web_app/ablation-service/combos.py:118`, `fire_detection_and_classification_web_app/ablation-service/combos.py:37`
- **false_alarms_per_hour is a duty cycle, not the count of alarm entries section 3.4.4 defines** — RO1.4, major  
  chapter_3.txt section 3.4.4 defines the false alarm rate as 'The number of alarms, meaning entries into GAS DANGER or FIRE CONFIRMED' - a count of rising edges. metrics.py:244 computes false_alarms_per_hour = fp/n_neg * 3600 * WINDOW_HZ, where fp counts every 1 Hz window the debounced alarm is held true. A single alarm that stays up for ten minutes counts as 600 'false alarms per hour'. The headline claim in the UI n  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:244`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:527`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:682`
- **Combination 6 as evaluated uses a flicker channel the deployed system never measures** — RO1.4, major  
  RO1.4 requires the configurations to be compared 'under identical test conditions', and combination 6 is meant to be the full deployed system. In the ablation recording path, flame_flicker_hz is genuinely measured by a 16 Hz FFT (constants.py:94-96, flicker.py:27-45, recordings.py:190-199). In the live path, fire-classification-service/main.py:261 defaults flicker_hz to K.FLICKER_QUIET_HZ and nothing on the dashboard  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/constants.py:94`, `fire_detection_and_classification_web_app/fire-classification-service/main.py:261`, `fire_detection_and_classification_web_app/ablation-service/recordings.py:190`
- **Dashboard reports the head-count under an industrial zone id while the default site is home** — RO2.1, major  
  The dashboard hardcodes CAMERA_ZONE_ID = 'fabric-store' (index.html:1135) and escalation.js defaults zoneId to the same string (line 49). The default site is home: SITE_KEY defaults to "home" in sites.py:34, docker-compose.yml:165 and sample.env:24. home.json has no fabric-store zone (its zoneAnchors are kitchen, bedroom-west, bedroom-southwest, dining, living, verander, bedroom-northeast, bedroom-southeast; defaultZ  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1135`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:49`, `fire_detection_and_classification_web_app/alert-service/sites.py:34`
- **Muster falls back to invented figures 42 and 45 in the same field** — RO2.1, major  
  §3.4.8 wants the muster derived from the measured head-count. When the camera never produced a count, muster_json silently returns invented constants instead: `present: 42, total: 45` (serializers.py:99-103), seeded from DEFAULT_MUSTER_PRESENT = 42 and DEFAULT_MUSTER_TOTAL = 45 (db.py:23-24) into every new incident (db.py:351). The only thing distinguishing them from real data is `source: "estimated"` versus `"vision  
  Evidence: `fire_detection_and_classification_web_app/alert-service/serializers.py:99`, `fire_detection_and_classification_web_app/alert-service/db.py:23`, `fire_detection_and_classification_web_app/alert-service/db.py:351`
- **home.json contradicts the thesis's own count of zones, exits and segments** — RO2.2, major  
  chapter_3.txt:610 states of the route scenarios: 'We drew a floor plan of the home and encoded it as the facility graph (Assumption A4)... The graph has six zones, three exits and nine corridor segments.' home.json actually defines EIGHT zones (lines 14-71), TWO exits (lines 72-85) and SIXTEEN edges (lines 200-265). Three numbers, three disagreements, in the one part of the thesis that quantifies the home graph. Eith  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:610`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:14-71`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:72-85`
- **Industrial ground truth covers 3 of 7 zones; home covers 8 of 8** — RO2.2, major  
  Q1, the largest structural asymmetry between the two files. home.json's `groundTruth` block has an entry for every one of its 8 zones (lines 324-361). industrial.json's has only 3 of its 7: fabric-store, dyeing and boiler (lines 347-363); cutting-floor, finishing, sewing-a and warehouse have none. test_routing.py:160-166 only iterates `site.ground_truth`, so four industrial zones are never checked against a hand-deri  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/home.json:324-361`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:347-363`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:160-166`
- **Home graph is 8 zones / 2 exits / 16 edges, thesis says 6 / 3 / 9** — RO2.2, major  
  Thesis 3.3.7 states "The graph has six zones, three exits and nine corridor segments." home.json has 8 zones, 2 exits, 17 nodes and 16 edges (counted with python over the file). The 2-vs-3 exit difference is the one that bites: thesis scenario 4 ("Two exits blocked, so that only a distant exit remains") is impossible on a two-exit graph, and the code's test_s4 blocks only ONE exit instead. THESIS_CHANGES.md already r  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/home.json:14-71`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:72-85`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:200-265`
- **Dijkstra does not start at the occupant position on the home site** — RO2.2 / Alg.4, major  
  Thesis 3.2.5.4: "A Dijkstra shortest path search is run from the position of the occupant." The code first RE-ANCHORS: if the occupant node is within the hazard radius it searches the UNPRUNED graph for the nearest non-exit node outside the radius, within `MAX_REANCHOR_M = 25.0` (a constant with no counterpart in the thesis), and runs Dijkstra from there instead. On the home site this fires on EVERY route in producti  
  Evidence: `fire_detection_and_classification_web_app/alert-service/routing.py:36,193-210`, `fire_detection_and_classification_web_app/alert-service/routing.py:212`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:266-323`
- **Refuge branch can choose an exterior door as the shelter point** — RO2.2 / Alg.4, major  
  routing.py:255-259 picks the refuge from `options = [n for n in dist ...]` with no filter on node kind, keyed on (refuge flag, distance from fire, id). Exit nodes are in `dist` whenever the exit was blocked by operator input rather than by the hazard, and they carry `refuge=False` and `zone_id=None`. Running the thesis's own scenario 5 — test_routing.py:113, home, living fire, both exits marked blocked — returns `ref  
  Evidence: `fire_detection_and_classification_web_app/alert-service/routing.py:255`, `fire_detection_and_classification_web_app/alert-service/routing.py:200`, `fire_detection_and_classification_web_app/alert-service/test_routing.py:113`
- **Thesis contradicts itself on when grounding runs; code follows RO3.1, not Section 3.4.7** — RO3.1, major  
  RO3.1 in Chapter 1 requires validation 'against the logged detection and sensor evidence before release'. chapter_3.txt:726 says the opposite: 'The check is carried out during the analysis, and it is not a step inside the running system.' report.py runs it at release time and withholds contradicted claims (l.257-258), and its own docstring (l.15-19) names and defends the deviation. The code choice is the stronger one  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:15`, `fire_detection_and_classification_web_app/alert-service/report.py:257`
- **RO3.1 says 'detection AND sensor evidence'; sensor readings get no vote** — RO3.1, major  
  RO3.1 requires every claim validated against the logged detection and sensor evidence. report.py:42-48 and the _check_smoke docstring at l.148-169 state explicitly that the gas channel takes no part in grading. The four values actually read are fuelType (l.82), fireAreaRatio (l.127), smokeBoxes (l.180) and occupancy (l.222) - three detector outputs and one classifier verdict. Sensor data enters only indirectly, throu  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:42`, `fire_detection_and_classification_web_app/alert-service/report.py:148`, `fire_detection_and_classification_web_app/alert-service/report.py:82`
- **Solid combustible: forbidden agent is CO2 in code, water-near-electrics in thesis** — RO3.2, major  
  Table 3.11, solid combustible, 'Agents that must not be used, and why' = 'Water near live electrical equipment, because of the risk of electric shock'. Code do_not_use = CO2, 'Knocks the flames down without cooling, so deep-seated material reignites'. These are different agents and different reasons - the thesis's item is not in do_not_use at all; it was moved into UNIVERSAL_CAUTIONS[0] 'Live electrical equipment' (l  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:104`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:114`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:328`
- **First action differs from Table 3.11 for solid combustible and liquid fuel** — RO3.2, major  
  Solid combustible - thesis 'Raise the alarm, switch off electrical power to the area if it is safe, and cool the base of the fire'; code 'Cool the burning material with water or foam.' Only the third clause survives. Liquid fuel - thesis 'Raise the alarm, stop the flow of fuel if it is safe, and smother the surface of the burning liquid'; code 'Do not use water. Cut off the air supply instead.' 'Raise the alarm' and   
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:94`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:68`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:46`
- **Liquid fuel first action is a prohibition, not the thesis's first action** — RO3.2, major  
  Thesis: 'Raise the alarm, stop the flow of fuel if it is safe, and smother the surface of the burning liquid'. Code line 68: 'Do not use water. Cut off the air supply instead.' The dashboard prints this as '<b>First: Do not use water.</b>', so the responder's first instruction is a negative and the two positive actions the thesis puts first — raising the alarm and stopping the fuel flow — appear nowhere. The do-not-u  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:68-72,78-81`, `fire_detection_and_classification_web_app/frontend/static/index.html:2243`, `scratchpad/thesis/chapter_3.txt:341`
- **Class A description claims 'most plastics', which the repo's own split contradicts** — RO3.2, major  
  Table 3.11's typical material for solid combustible is 'Wood, paper, cloth, cardboard, packaging'. Code line 93 says 'Solid materials — wood, paper, cloth, most plastics'. 'Most plastics' is not in the thesis table, and the repo's own out-of-distribution split lists PVC and polystyrene as fuels the model never saw. The dashboard prints this string under the verdict, so the card tells the operator the class covers pla  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:93`, `fire_detection_and_classification_web_app/ablation-service/runs.py:55-58`, `fire_detection_and_classification_web_app/frontend/static/index.html:2241`
- **Dashboard hard-codes an industrial zone id while the default site is home** — RO3.3 / Alg.2, major  
  Q3/Q6. frontend/static/index.html:1135 sets `const CAMERA_ZONE_ID = 'fabric-store'` and posts it to /api/events/fire (index.html:1651) and /api/events/clear (index.html:1672); escalation.js:49 independently hard-codes `zoneId: 'fabric-store'` for the gas-warning and classification path. The default site is home (sites.py:34, docker-compose.yml:165, .env:24), whose zones are kitchen/dining/living/verander/bedroom-*. i  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1135`, `fire_detection_and_classification_web_app/frontend/static/index.html:1647-1672`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:49`
- **Switching to the industrial site still labels everything "Home"** — RO3.3 / RO2.3, major  
  docker-compose.yml:166 sets `SITE_NAME=${SITE_NAME:-Home}`, so SITE_NAME is ALWAYS non-empty in the container. zones_seed.py:22 is `SITE_NAME = os.getenv("SITE_NAME") or ACTIVE.name` - the env var always wins, so `ACTIVE.name` ("Industrial Unit", industrial.json:3) can never be reached. Set SITE_KEY=industrial in .env and leave SITE_NAME alone and the system serves the industrial zones and graph while serializers.py:  
  Evidence: `fire_detection_and_classification_web_app/docker-compose.yml:165-167`, `fire_detection_and_classification_web_app/alert-service/zones_seed.py:19-22`, `fire_detection_and_classification_web_app/alert-service/serializers.py:428-429`
- **Participant count: RO3.4 says at least eight, section 3.3.8 targets five** — RO3.4, major  
  Explicit number comparison. Ch.1 RO3.4: "a structured expert evaluation with at least eight qualified participants" (chapter_1_and_2.txt:67). Ch.3 §3.3.8 Sampling: "Purposive sampling is used, with a target of five participants" (chapter_3.txt:620). Thesis values: 8 vs 5. REQUIREMENTS.md:39 carries the 8. No code holds either number — there is no participant register, and alert-service/db.py has exactly five tables (  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:67`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:620`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:147`
- **Humidity is folded into the node worst-of but Table 3.8 does not grade it** — ALG1, minor  
  Table 3.8 lists four graded channels: MQ-2, MQ-7, temperature, flame. _sensor_views returns five tiles and gives humidity a level of "normal" whenever a value is present (main.py:155-161). main.py:173-176 then takes max() over all five levels. Because LEVEL_RANK puts unknown at 0 and normal at 1 (main.py:74), humidity's hard-coded "normal" outranks "unknown". Failure scenario: the MQ-2, MQ-7 and flame modules are unp  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:155`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:160`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:74`
- **Three polls documented as ~6 s in code, ~4 s in the thesis** — ALG1, minor  
  chapter_3.txt:260 annotates the 3-poll rule "if count >= 3: A <- Z // about 4 s" and the prose calls it "three requests in a row" at a 2 s poll. escalation.js:34-35 documents the same constant as "The panel polls every 2 s, so this is ~6 s of agreement". Code number 6 s, thesis number about 4 s. Three polls spaced 2 s apart span 4 s from first to third, so the thesis figure is the right one and the code comment overs  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:34`, `fire_detection_and_classification_web_app/frontend/static/js/sensor-panel.js:17`, `esp_32_sensor_network_code/sensor_node_mock/config.h:45`
- **Zone aggregation ignores zoneId: worst of all nodes, not worst per zone** — Alg.1, minor  
  Algorithm 1 aggregates per zone: 'for each node n in the zone ... Z <- worst(L[n] over the nodes of the zone)' (chapter_3.txt:260). escalation.js:78-88 iterates payload.nodes with no zone grouping at all — 'Worst node wins' across every node the bridge knows. With the one in-scope node this is equivalent, so it is not visible today; but the repo ships a simulator that fans out over eight different zones (mock_sender.  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:260`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:78`, `esp_32_sensor_network_code/tools/mock_sender.py:44`
- **Comment says about 6 s of agreement where the thesis says about 4 s** — Alg.1, minor  
  escalation.js:34-35 reads 'The panel polls every 2 s, so this is ~6 s of agreement'. The thesis pseudocode says 'if count >= 3: A <- Z   // about 4 s' (chapter_3.txt:260), and the brief repeats '~4 s at 2 s polling'. Three polls at a 2 s interval span 4 s from the first observation, so the thesis figure is the right one and the code comment is wrong by one interval. Behaviour is unaffected - STRIKES is still 3 and PO  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:34`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:36`, `fire_detection_and_classification_web_app/frontend/static/js/sensor-panel.js:17`
- **Gas warnings appear only inside a card titled VLM Scene Analysis** — Alg.2 (GAS WARNING) / RO3.3, minor  
  Alg.2's GAS WARNING state is meant to produce a written warning with the zone status staying clear and no alarm. escalation.js does that correctly on the wire (sendWarning, escalation.js:175-202: cooldown, text from /api/warn, no alarm). On screen the only trace is `S.log.push({ text: '[warning] ' + st.warningText })` (index.html:2281-2283), and `S.log` is rendered into the card headed 'VLM Scene Analysis' (index.htm  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:175`, `fire_detection_and_classification_web_app/frontend/static/index.html:2281`, `fire_detection_and_classification_web_app/frontend/static/index.html:1099`
- **The scene call is outside the single-in-flight VLM guard** — Alg.3, minor  
  Algorithm 3 requires only one VLM call in flight at a time. The verification call is guarded by S.pendingVlm, cleared in a .finally() (index.html:1800 area). describeScene (escalation.js:270-283) is invoked from sendFire, which is reached synchronously from the verification call's .then() handler (index.html:1774-1780) - before that .finally() runs - and is not covered by the guard. So at the rising edge of an alarm   
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:270`, `fire_detection_and_classification_web_app/frontend/static/index.html:1774`
- **Humidity is graded, though Table 3.15 only logs it** — RO1.1, minor  
  Table 3.15 gives humidity a collection note of 'Logged continuously' with no thresholds (chapter_3.txt:503-504), and Table 3.8 has no humidity row. The service emits a humidity tile whose level is hard-coded 'normal' whenever a value is present (main.py:155-161). The comment is honest about intent ('this tile never escalates on its own'), but the level participates in the worst-of computation (main.py:173-176), so a   
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:503`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:155`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:173`
- **Sensor service defaults new nodes to an industrial zone id** — RO1.1 / Alg.1, minor  
  esp32-sensor-service/main.py:101 declares `zoneId: str = Field(default="fabric-store", ...)`, an INDUSTRIAL zone, while the default site is home. The sensor service imports nothing from sites.py or zones_seed.py (grep for 'from sites|import sites|zones_seed' over esp32-sensor-service/, frontend/ and the four model services returns nothing), so it cannot validate a zone id against the active site at all - the README s  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:101`, `fire_detection_and_classification_web_app/alert-service/sites.py:34`, `esp_32_sensor_network_code/README.md:164-178`
- **Configured 300 epochs, shipped weights are from epoch 27** — RO1.2, minor  
  The checkpoint's train_args say epochs = 300 with patience = 50, but the checkpoint's own top-level fields say epoch = 26 (zero-based, so the 27th) and train_results carries exactly 27 rows of per-epoch loss and metric history. best_fitness = 0.5214, which equals metrics/mAP50-95(B), so this is the best epoch recorded. Any viva statement of "trained for 300 epochs" would not match the artefact: the delivered weights   
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (epoch, best_fitness, train_results, train_args.epochs in archive/data.pkl)`
- **Ablation gate uses >= for area but > for yolo_detected** — RO1.2, minor  
  ablation-service/constants.py:28-30 claims the 0.35 constant is the same gate as the dashboard's MIN_CONF, and the dashboard tests d.confidence >= MIN_CONF (index.html:1730). Inside vision.py the same constant is applied with two different operators: line 73 uses conf >= K.YOLO_DETECT_THRESHOLD to decide whether a box contributes area, and line 84 uses max(fire_conf, smoke_conf) > K.YOLO_DETECT_THRESHOLD to set yolo_  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/vision.py:73`, `fire_detection_and_classification_web_app/ablation-service/vision.py:84`, `fire_detection_and_classification_web_app/ablation-service/constants.py:28`
- **Thesis says confidence >= 0.35; the classifier's gate uses strictly greater** — RO1.2, minor  
  chapter_3.txt:285 specifies "fire boxes B with confidence >= 0.35". The code disagrees with itself at the boundary: index.html:1730 uses `d.confidence >= MIN_CONF`, ablation-service/recordings.py:187 uses `>= K.YOLO_DETECT_THRESHOLD`, and fire-classification-service/vision.py:73 uses `>=` for box area - but vision.py:84 sets the yolo_detected channel with `max(fire_conf, smoke_conf) > K.YOLO_DETECT_THRESHOLD`, strict  
  Evidence: `thesis/chapter_3.txt:285`, `fire_detection_and_classification_web_app/fire-classification-service/vision.py:73`, `fire_detection_and_classification_web_app/fire-classification-service/vision.py:82-85`
- **combo5's docstring claims it is the deployed rule; it is missing the unavailable branch** — RO1.3 / RO1.4, minor  
  ablation-service/combos.py:221 says combination 5 is "VLM + YOLO - verbatim the rule the dashboard deploys today", and :222-223 implement `raw2 & (features["vlm_confirmed"] > 0.5)`. The deployed rule (escalation.js:148) is `yoloHit && (vlmConfirmed || (!vlmAvailable && gassy))` - it has a second disjunct that combo5 has no term for. It also has no sensor arm, while the deployed rule reads the graded sensor level. On   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:217`, `fire_detection_and_classification_web_app/ablation-service/combos.py:221`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:148`
- **ROC and PR curves are advertised in three places but never computed** — RO1.4, minor  
  combos.py:5 claims 'every arm also yields an ROC/PR curve from its score, which is threshold-free', constants.py:83 keeps ROC_MIDPOINT = 0.5 as 'the midpoint drawn on the ROC curve', describe() ships roc_midpoint to the page, and the page prints 'Score used for the ROC curve' under every rule. No curve, AUROC, TPR/FPR or PR computation exists in the service - grep for 'fpr', 'tpr', 'auroc', 'roc_curve', 'auc' across   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:5`, `fire_detection_and_classification_web_app/ablation-service/constants.py:83`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:354`
- **Six combinations built where the thesis says four, in four places** — RO1.4, minor  
  constants.py:141-148 defines six: 1 sensors only, 2 YOLO only, 3 VLM only, 4 sensors + YOLO, 5 VLM + YOLO, 6 sensors + YOLO + VLM. RO1.4 and sections 3.2.4, 3.3.5 and 3.3.6 all say four. This is a superset rather than a shortfall, and THESIS_CHANGES.md:281-330 already documents it honestly and proposes the exact wording fix, including the point that 'vision only' is ambiguous between combination 2 and combination 5 -  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/constants.py:141`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:281`, `fire_detection_and_classification_web_app/README.md:65`
- **Section 3.5 says the model returns only a count; it also returns boxes** — RO2.1, minor  
  chapter_3.txt line 795 states "The human detection model returns only a count of people." The endpoint returns detections[] with label, confidence and box [x1,y1,x2,y2] alongside count (main.py:86-90). The code is right and the sentence is wrong: RO2.1 (line 135) requires approximate position, which needs boxes, and the boxes are transient - nothing stores or transmits them (see the position finding). The thesis word  
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:86-90`, `fire_detection_and_classification_web_app/alert-service/db.py:125-128`
- **Section 3.5.2 says the model returns only a count; it returns boxes** — RO2.1, minor  
  §3.5.2 (chapter_3.txt:795) states flatly: "The human detection model returns only a count of people." The service returns a `detections` array with a label, a confidence and a four-value pixel box for every person, alongside the count (main.py:83-98), and the proxy forwards the whole thing to the browser (server.py:105). THESIS SAYS COUNT ONLY, CODE RETURNS COUNT PLUS PER-PERSON BOXES. This is a thesis-internal contr  
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:83`, `fire_detection_and_classification_web_app/frontend/server.py:105`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:795`
- **Person confidence 0.40 is undocumented and works against the recall target** — RO2.1, minor  
  The thesis fixes exactly one detection threshold: fire boxes with confidence >= 0.35 (chapter_3.txt:285, Algorithm 2 input). It gives no number for person confidence. The code sets HUMAN_MIN_CONF = 0.40 (main.py:37) and pins it again in docker-compose.yml:26, above the fire detector's 0.35, with the stated reason that a false person inflates a head-count. That reasoning is sound for precision, but RO2.1 is scored on   
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:37`, `fire_detection_and_classification_web_app/docker-compose.yml:26`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:285`
- **Check-out increments a muster field the camera path never reads** — RO2.1, minor  
  A check-out bumps muster_present: `UPDATE incidents SET muster_present = MIN(muster_present + 1, muster_total)` (db.py:656). But muster_json only reads muster_present on the fallback branch, when occupancy_peak is null (serializers.py:99-103); whenever the camera produced any count it computes `present = peak - current` and ignores muster_present entirely (serializers.py:111-113). So on every incident where the human  
  Evidence: `fire_detection_and_classification_web_app/alert-service/db.py:656`, `fire_detection_and_classification_web_app/alert-service/serializers.py:99`, `fire_detection_and_classification_web_app/alert-service/serializers.py:181`
- **Hazard radius is per site (2.0 m home, 6.0 m industrial); thesis gives one value** — RO2.2 / Alg.4, minor  
  Thesis 3.2.5.4 refers to "the hazard radius" as a single unqualified value. The code makes it a site property: `hazardRadiusM: 2.0` in home.json against `6.0` in industrial.json, overridable at container start by the `HAZARD_RADIUS_M` env var (blank in both .env and sample.env, so the file value is used). The home file carries a `hazardRadiusNote` explaining that 6 m in a 13 m house would reach every room and collaps  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites/home.json:11-12`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:11`, `fire_detection_and_classification_web_app/alert-service/sites.py:38,181`
- **Graph size differs from the thesis, already documented with a rewrite** — RO2.2 / §3.3.7, minor  
  §3.3.7 states "The graph has six zones, three exits and nine corridor segments." The built home.json has 8 zones, 2 exits and 16 edges over 17 nodes. Reporting this as reconciled rather than hidden: THESIS_CHANGES.md:13-52 sets out the discrepancy in a table, gives the replacement sentence, and justifies 8 zones (the sketch labels eight areas), 2 exits (the other wall marks are windows) and "walkable segments" over "  
  Evidence: `fire_detection_and_classification_web_app/THESIS_CHANGES.md:13`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:11`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:11`
- **Decision-to-delivery is stamped at FCM handoff and reported as round-trip halved** — RO2.3, minor  
  Table 3.19 defines the interval as "Entry into GAS DANGER or FIRE CONFIRMED to the alert arriving on the mobile device". The code stamps sent_at when alert-service hands the message to FCM (after the dashboard's HTTP post and after _attach_route runs Dijkstra under the intake lock), and reports oneway_ms = rtt_ms / 2 rather than a measured arrival. The choice is defended in the code (the handset clock cannot be trust  
  Evidence: `fire_detection_and_classification_web_app/alert-service/intake.py:249`, `fire_detection_and_classification_web_app/alert-service/db.py:580`, `fire_detection_and_classification_web_app/alert-service/db.py:101`
- **The gas-warning payload carries route:"/incident", contradicting where the app sends it** — RO2.3, minor  
  _build_warning_message sets data['route'] = '/incident', but the app never reads data['route'] (grep for "data['route']" in lib/ returns nothing; the three hits on 'route' are the EvacRoute JSON key). _routeFor decides from data['type'], sending gas_warning to /warning. The field is dead and says the opposite of what happens, which is a trap for anyone reading the payload to explain the two-channel design.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/fcm.py:197`, `fire_notification_and_evacuation_mobile_app/lib/core/notifications/notification_service.dart:161`, `fire_detection_and_classification_web_app/alert-service/fcm.py:159`
- **Decision-to-delivery starts at the push, not at entry into FIRE CONFIRMED** — RO2.3, minor  
  Table 3.19 defines the interval as "Entry into GAS DANGER or FIRE CONFIRMED to the alert arriving on the mobile device" (chapter_3.txt:704). The code stamps sent_at inside alert-service immediately before fcm.send_fire_push (intake.py:198, 248), so the browser-side escalation decision (frontend/static/js/escalation.js:226-243 POSTing /api/events/fire) and that HTTP hop sit outside the measured interval. The other end  
  Evidence: `fire_detection_and_classification_web_app/alert-service/intake.py:198`, `fire_detection_and_classification_web_app/alert-service/intake.py:248`, `fire_detection_and_classification_web_app/alert-service/db.py:625`
- **Gas warning payload says route '/incident' while the app sends it to '/warning'** — RO2.3, minor  
  _build_warning_message sets data['route'] = '/incident' (fcm.py:197), the same value as the fire push (fcm.py:159). The app never reads data['route'] — _routeFor derives the destination from data['type'] instead, sending gas_warning to '/warning' (notification_service.dart:161-162). The field is dead and, read literally, says the wrong thing: anyone reading the payload in a viva would conclude a gas warning opens the  
  Evidence: `fire_detection_and_classification_web_app/alert-service/fcm.py:197`, `fire_detection_and_classification_web_app/alert-service/fcm.py:159`, `fire_notification_and_evacuation_mobile_app/lib/core/notifications/notification_service.dart:161`
- **Size bands disagree between the prompt and the validator, and overlap each other** — RO3.1, minor  
  The prompt tells the model that 'large' means it 'reaches the ceiling or spans more than about a third of the frame', i.e. about 0.33 (vlm-service/main.py:438-439). The validator's _SIZE_BANDS accepts 'large' from 0.15 upward (report.py:67). A model correctly following the prompt and calling a 0.20 fire 'moderate' is graded against a table that also allows 'large' at that value. The bands overlap by construction: sma  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:64`, `fire_detection_and_classification_web_app/vlm-service/main.py:438`
- **Undocumented plus-or-minus-one tolerance on the head-count claim** — RO3.1, minor  
  _check_people treats a claimed count as SUPPORTED unless it differs from the human detector by more than 1 (report.py:233), so a report stating '3 people visible' is released as a confirmed finding when the detector counted 2. test_report.py:40-43 pins this as intended. The thesis defines no tolerance for a claim-level check; Table 3.20 has only supported, contradicted and unsupported. Either state the tolerance in t  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:233`, `fire_detection_and_classification_web_app/alert-service/test_report.py:40`
- **RO3.1 says detection and sensor evidence; sensor readings grade nothing** — RO3.1, minor  
  RO3.1 requires claims validated against "logged detection and sensor evidence". In the code sensor readings are deliberately given no vote: _check_smoke's docstring says so at length (report.py:150-161) and test_report.py:105-115 asserts the smoke verdict is identical for gasLevel normal/warn/danger/empty. Sensors enter only indirectly, through the fuel classifier's verdict on the material claim - and that path is it  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:150`, `fire_detection_and_classification_web_app/alert-service/test_report.py:105`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:381`
- **Withheld claim text is shipped to the client that documents it never arrives** — RO3.1, minor  
  build() returns the full claims list including contradicted ones, and a "withheld" array that carries each withheld claim's text verbatim (report.py:272-275). serializers.situation_report_json returns the stored blob untouched (serializers.py:237-243), so both reach the phone. The app then filters them itself (models.dart:683 shown, card l.27). But models.dart:607-609 says "[contradicted] claims never arrive - the ba  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:272`, `fire_detection_and_classification_web_app/alert-service/serializers.py:237`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:607`
- **Size bands in the validator disagree with the numbers the prompt gave the model** — RO3.1, minor  
  The prompt tells the model "large reaches the ceiling or spans more than about a third of the frame" - about 0.33 of frame area (vlm-service/main.py:439-441). The validator's large band starts at 0.15 and small runs 0.00-0.05, moderate 0.02-0.25, large 0.15-1.01 (report.py:64-68). So a box covering 0.20 supports both "moderate" and "large", and the model is judged against thresholds it was never told. The overlaps ar  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:62`, `fire_detection_and_classification_web_app/alert-service/report.py:64`, `fire_detection_and_classification_web_app/vlm-service/main.py:439`
- **Material check covers three of the classifier's four classes and misreports why** — RO3.1 / RO3.2, minor  
  _FAMILY_BY_FUEL maps only solid_combustible, liquid_fuel and gas_fire (report.py:56-60), but the shipped classifier's class_names are ['no_fire', 'gas_fire', 'liquid_fuel', 'solid_combustible'] (fire-classification-service/model/manifest.json class_names) and the thesis names the same four (chapter_3.txt s3.2.5.4). With fuelType='no_fire' the lookup returns None and the code falls into the branch whose reason reads "  
  Evidence: `fire_detection_and_classification_web_app/alert-service/report.py:56`, `fire_detection_and_classification_web_app/alert-service/report.py:90`, `fire_detection_and_classification_web_app/fire-classification-service/model/manifest.json:104`
- **Table 3.10 says the one-sentence description forms the report; the code demotes it** — RO3.1 / Table 3.10, minor  
  Table 3.10 (chapter_3.txt:315-324) lists three VLM fields and says of description: "Forms the situation report delivered with a fire alarm". The code instead adds a third prompt returning ten structured fields (vlm-service/main.py:400-444) and explicitly refuses to grade the sentence: "The model's own sentence rides along only as context, never as a finding" (report.py:264-267). The structured prompt is the right eng  
  Evidence: `scratchpad/thesis/chapter_3.txt:315`, `fire_detection_and_classification_web_app/vlm-service/main.py:400`, `fire_detection_and_classification_web_app/alert-service/report.py:264`
- **Thesis says the check is not inside the running system; the code runs it at release** — RO3.1 / s3.4.7, minor  
  chapter_3.txt:726 states "The check is carried out during the analysis, and it is not a step inside the running system." report.py applies Table 3.20's categories at release time and withholds contradicted claims before the report leaves alert-service (report.py:15-19, 257). The deviation is deliberate and documented, with the replacement wording already drafted (THESIS_CHANGES.md:355-418). This is prose that must mo  
  Evidence: `scratchpad/thesis/chapter_3.txt:726`, `fire_detection_and_classification_web_app/alert-service/report.py:15`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:355`
- **Gas fire: thesis prohibition is not in do_not_use, two unlisted agents are** — RO3.2, minor  
  Table 3.11's gas-fire prohibition is an ACTION, not an agent: 'Putting out the flame while gas is still flowing, because unburnt gas can build up and cause an explosion'. The code's do_not_use instead lists Water and Foam (lines 56-61), neither of which appears in Table 3.11. The thesis's actual prohibition is present but in different fields - first_action_why (lines 47-51) and 'short' (line 62). The substance reache  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:56`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:47`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:62`
- **Code cites EN 2, thesis and this repo's own README cite ISO 3941** — RO3.2, minor  
  Table 3.11's caption says 'The fuel classes follow the fire classes of ISO 3941 [5]'. extinguishers.py:16 says 'CLASSES ARE EN 2 (EUROPEAN)'. README.md:288 in the same repo says 'following ISO 3941'. Three statements, two standards. The A/B/C letters themselves agree, so no recommendation is wrong - this is a citation inconsistency, and it is inside the same repo as well as against the thesis. Pick one standard and u  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:16`, `fire_detection_and_classification_web_app/README.md:288`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:328`
- **Typical-material lists do not match Table 3.11** — RO3.2, minor  
  Table 3.11 'Typical material' column vs the code's class_description. Solid combustible - thesis 'Wood, paper, cloth, cardboard, packaging'; code 'Solid materials - wood, paper, cloth, most plastics' (drops cardboard and packaging, adds plastics). Liquid fuel - thesis 'Petrol, diesel, solvents, paint, alcohol'; code 'Flammable liquids - petrol, oil, solvents, paint' (drops diesel and alcohol, adds oil). Gas fire - th  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:93`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:67`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:41`
- **Code cites EN 2 while the thesis and README cite ISO 3941** — RO3.2, minor  
  extinguishers.py line 16 states 'CLASSES ARE EN 2 (EUROPEAN)'. Table 3.11's caption says 'The fuel classes follow the fire classes of ISO 3941', and the repo's own README says the guidance follows ISO 3941. The A/B/C letters agree between the two standards, so no recommendation is wrong — but the code header names a different standard from the document it is meant to implement, and RO3.2 is assessed 'against an estab  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:16-19`, `fire_detection_and_classification_web_app/README.md:288`, `scratchpad/thesis/chapter_3.txt:328`
- **Liquid fuel typical materials drop diesel and alcohol, add 'oil'** — RO3.2, minor  
  Thesis: 'Petrol, diesel, solvents, paint, alcohol'. Code line 67: 'Flammable liquids — petrol, oil, solvents, paint'. Diesel and alcohol are gone; 'oil' is added, which is awkward because the same entry's caution warns that cooking oil is class F and needs wet chemical, so the class description now names the material the caution excludes.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:67,84-88`, `scratchpad/thesis/chapter_3.txt:340`
- **Classifier's fire-persistence gate is 0.5, not the thesis's 0.35** — RO3.2, minor  
  The thesis and the rest of the system use a fire box confidence of 0.35 (constants.py YOLO_DETECT_THRESHOLD = 0.35, 'the generator's YOLO_DETECT_THRESHOLD, which also happens to equal the dashboard's MIN_CONF'). The shipped manifest's config.yolo_fire_threshold is 0.5, and _recompute_persistence builds the fire_persistence feature as the rolling mean of yolo_fire_conf > that threshold. So the feature feeding the fuel  
  Evidence: `fire_detection_and_classification_web_app/fire-classification-service/constants.py:21-23`, `fire_detection_and_classification_web_app/fire-classification-service/model/manifest.json (config.yolo_fire_threshold)`, `fire_detection_and_classification_web_app/fire-classification-service/fire_classifier.py:91-94`
- **Code resets the strike counter more strictly than the printed pseudocode** — ALG1, info  
  The thesis pseudocode guards the whole counter block with "if Z is higher than A", so a poll where Z drops to or below A leaves candidate and count untouched. The code resets on any change of level: escalation.js:109-114 compares the incoming level with S.candidate unconditionally. Worked difference with A = normal and the poll sequence warn, normal, warn, warn: the thesis pseudocode ignores the normal poll and accep  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:109`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:118`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:260`
- **Ablation runs six configurations where the thesis specifies four** — RO1.4, info  
  chapter_1_and_2.txt:52 and chapter_3.txt:94 both name four levels: sensor only, vision only, sensor and vision fusion, and the full system with VLM verification. ablation-service/combos.py implements six: combo1 sensors (:144), combo2 YOLO (:157), combo3 VLM alone (:194), combo4 sensors+YOLO (:203), combo5 VLM+YOLO (:217), combo6 fusion (:226). Combinations 3 and 5 have no counterpart among the four stated levels. Th  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:194`, `fire_detection_and_classification_web_app/ablation-service/combos.py:217`, `fire_detection_and_classification_web_app/THESIS_CHANGES.md:281`

### Mobile app (7)

- **Phone paints a hardcoded four-point path labelled "Safe route"** — RO2.2, major  
  floor_plan_painter.dart:48 `_line => (route != null && route!.isDrawable) ? route!.polyline : plan.defaultRoute`, and `defaultRoute` is a literal 4-Offset list per site (floor_plan_data.dart:170 industrial, :258 home). incident_screen.dart:99 sets `drawableRoute = null` whenever the backend route is missing (routing failure, old record, offline demo), and the painter then draws that literal with identical styling, an  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/shared/floor_plan/floor_plan_painter.dart:48`, `fire_notification_and_evacuation_mobile_app/lib/shared/floor_plan/floor_plan_data.dart:258`, `fire_notification_and_evacuation_mobile_app/lib/features/incident/incident_screen.dart:194`
- **Dashboard asserts freshness and health it never measures** — RO2.3, major  
  With no backend reachable the dashboard still paints a confident all-clear. ApiFireRepository seeds `_siteName = MockData.siteName` ('Home', api_fire_repository.dart:28 and mock_data.dart:23), `_health = MockData.health` (api_fire_repository.dart:30) and the eight home zones (api_fire_repository.dart:20), and `refresh()` swallows every failure with a debugPrint (api_fire_repository.dart:110, 117). The dashboard then   
  Evidence: `lib/data/api/api_fire_repository.dart:20`, `lib/data/api/api_fire_repository.dart:28`, `lib/data/api/api_fire_repository.dart:110`
- **App's documented run path is a public tunnel, not the Wi-Fi of Table 3.7** — ARCH, minor  
  Table 3.7's communication layer is "Wi-Fi" on a LAN (chapter_3.txt:244), and docker-compose.yml:147-148 justifies publishing alert-service:8090 precisely so the phone can reach it "over plain HTTP on the LAN". The shipped run script does something else: run-remote.sh sets API_BASE_URL="https://applaud-finite-essential.ngrok-free.dev" and documents starting an ngrok tunnel to localhost:443, with its own comment conced  
  Evidence: `fire_notification_and_evacuation_mobile_app/run-remote.sh:1-28`, `fire_notification_and_evacuation_mobile_app/.gitignore:54-55`, `fire_detection_and_classification_web_app/docker-compose.yml:145-156`
- **History detail calls every past event a fire and labels resolution twice** — NONE, minor  
  history_detail_screen.dart:41 builds the title as '🔥 ${event.zoneName} fire' and line 45 forces `ChipTone.fire` regardless of `event.type`, so a smoke-only event or a false alarm from dust opens a screen headed 'Cutting Floor fire' in red. The event's own `DetectionType.label` (models.dart:26-31) is ignored here even though EventCard uses it correctly one screen earlier (event_card.dart:53). The same file also maps `  
  Evidence: `lib/features/history_detail/history_detail_screen.dart:41`, `lib/features/history_detail/history_detail_screen.dart:44`, `lib/features/history_detail/history_detail_screen.dart:72`
- **Offline demo incident is an industrial zone drawn on the home plan** — RO2.2, minor  
  `MockData.incident` builds the demo alarm with `zone: Zone(id: 'fabric-store', ...)` and no `route`, while `MockData.zones` returns the eight HOME zones and `FireRepository.siteKey` returns 'home'. So in mock/offline mode the incident screen picks `FloorPlan.home`, `roomForZone('fabric-store')` returns null (no room is hatched), and the painter falls back to the home `defaultRoute` with `fireAt: Offset(130, 130)` - t  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/mock/mock_data.dart:108-130`, `fire_notification_and_evacuation_mobile_app/lib/data/mock/mock_data.dart:29-99`, `fire_notification_and_evacuation_mobile_app/lib/data/mock/fire_repository.dart:46`
- **History screen claims a thirty-day window the backend does not apply** — RO2.3, minor  
  history_screen.dart:27 renders the subtitle '<site> · past 30 days · N events'. The backend applies no date window: `/api/history` (alert-service/app.py:455-461) returns whatever `get_resolved_incidents` yields, and that query is 'SELECT * FROM incidents WHERE status = "resolved" ORDER BY resolved_at DESC LIMIT ?' (alert-service/db.py:469) — a row limit, not a time filter. An incident from three months ago appears un  
  Evidence: `lib/features/history/history_screen.dart:27`, `fire_detection_and_classification_web_app/alert-service/app.py:455`, `fire_detection_and_classification_web_app/alert-service/db.py:469`
- **Offline demo data mixes the home catalogue with industrial incidents** — RO2.3 / RO3.3, minor  
  MockData declares `siteName = 'Home'` (mock_data.dart:23) and eight HOME zones - kitchen, dining, living, verander and four bedrooms (lines 28-99) - but the demo incident it ships is a Fabric Store fire with zone id 'fabric-store' (lines 109-120), and all five history entries are industrial rooms: Fabric Store, Boiler Room, Cutting Floor, Dyeing, Finishing (lines 132-200). So the offline/no-backend path shows a home   
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/mock/mock_data.dart:23`, `fire_notification_and_evacuation_mobile_app/lib/data/mock/mock_data.dart:28-99`, `fire_notification_and_evacuation_mobile_app/lib/data/mock/mock_data.dart:109-120`

### ESP32 sensor node (6)

- **Ch1 says MQTT at 1 s, code does HTTP at 3 s - thesis text still uncorrected** — RO1.1, major  
  Ch1 line 49: 'publishes synchronised readings over MQTT at a fixed interval of one second'. Ch3 line 479 and line 244 both say HTTP POST JSON at about three seconds. Code: HTTPClient POST (ino:207) every POST_INTERVAL_MS 3000 (config.example.h:53). Thesis Ch1 values = MQTT, 1000 ms; code values = HTTP, 3000 ms. So Chapter 1 disagrees with both Chapter 3 and the artefact, on protocol and on interval. THESIS_CHANGES.md  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:49`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:479`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:207`
- **Chapter 1 promises MQTT at 1 s; the code is HTTP POST at 3 s** — RO1.1, major  
  Chapter 1 RO1.1: 'publishes synchronised readings over MQTT at a fixed interval of one second' (chapter_1_and_2.txt:49). The code has no MQTT at all — rg -ni 'mqtt|paho|mosquitto' across all four repos returns only prose inside THESIS_CHANGES.md; no broker in docker-compose.yml, no client in requirements.txt (which is two lines: fastapi, uvicorn[standard]). The board uses HTTPClient over plain HTTP to http://<host>:8  
  Evidence: `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_1_and_2.txt:49`, `esp_32_sensor_network_code/sensor_node_mock/config.h:28`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:198`
- **flame_raw is two hard-coded constants, yet the classifier reads it as analog counts** — RO1.1 / RO3.2, major  
  sensor_node_mock.ino:195 emits flame_raw as flameOn ? 400 : 3900. That expression is inside postReadings(), outside any MOCK_MODE guard, so a board with MOCK_MODE 0 and the real IR module wired still sends the same two numbers; tools/mock_sender.py:103 does the same. Downstream this field is not cosmetic. fire-classification-service/sensor_adapter.py:169-189 (_flame_value) documents it as "Analog IR counts -> the mod  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:195`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:131`, `esp_32_sensor_network_code/tools/mock_sender.py:103`
- **The config the board actually compiles documents the wrong site** — RO1.1, minor  
  sensor_node_mock/config.h is present on disk (gitignored, byte-identical to firewatch-private-files/config-sensor-node.h; verified with diff, exit 0). Its lines 34-38 say zoneId "should match an id from alert-service/zones_seed.py (fabric-store, cutting-floor, dyeing, sewing-a, warehouse, boiler, finishing)" while line 40 sets ZONE_ID "kitchen", a home zone. Two things are wrong. First, alert-service/zones_seed.py no  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/config.h:34`, `esp_32_sensor_network_code/sensor_node_mock/config.h:40`, `esp_32_sensor_network_code/sensor_node_mock/config.example.h:34`
- **Ch.1 promises MQTT at one second; the node posts HTTP at three** — RO1.1, minor  
  chapter_1_and_2.txt:49 states RO1.1 as publishing "over MQTT at a fixed interval of one second". I grepped -ri "mqtt" across the whole repo: zero hits. The node uses HTTPClient POST (sensor_node_mock.ino:198-207) at POST_INTERVAL_MS 3000 (config.example.h:53). The code agrees with Ch.3, which says "Sensor nodes send JSON messages by HTTP POST to the sensor service" (chapter_3.txt:244) and "a fixed interval of about t  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:198`, `esp_32_sensor_network_code/sensor_node_mock/config.example.h:53`, `chapter_1_and_2.txt:49`
- **mq2_raw and mq7_raw are reconstructed from ppm, not reported ADC counts** — RO1.1, minor  
  The service labels these fields 'raw ADC, kept for calibration work' (main.py:88) and the classifier prefers them because 'the training channel is ADC-shaped, with a baseline around 300 counts' (sensor_adapter.py:50-60). But the firmware never sends the ADC value: it derives raw back from ppm via mockRaw(ppm, fullScale) in both modes (ino:114-121, 193-194). It round-trips today only because readRealSensors uses a lin  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:114`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:135`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:88`

### ESP32-CAM (4)

- **README claims the repo is safe to publish while git history still holds the Wi-Fi password** — NONE, major  
  README.md:224-227 states "The credentials are in a file that Git ignores ... The repository stays safe to publish." The working tree is clean, but the history is not. git log -p over the sketch shows the real credentials committed in plain text: commit ec6adff added placeholders, commit ad268eb ("Updated the SSID and Password") replaced them with the live values, and commit c0ac041 removed them. Both the added and th  
  Evidence: `esp_32_cam_code/README.md:224`, `esp_32_cam_code/.gitignore:3`, `firewatch-private-files/config-esp32-cam.h:17`
- **Sketch filename does not match its folder, so the Arduino IDE cannot open it** — NONE, minor  
  The Arduino IDE requires a .ino to sit in a folder of the same name. The folder is esp_32_cam_code and the sketch is esp32cam_stream_v2_final_working_code_via_wifi.ino (git ls-files confirms it is at the repo root, with no subfolder). Opening the repo therefore makes the IDE offer to move the file instead of opening the project. The README's flashing steps at README.md:124-135 never mention this - I grepped README.md  
  Evidence: `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:1`, `esp_32_cam_code/README.md:124`
- **README states 4 MB PSRAM as fact; the sketch is written not to need it** — NONE, minor  
  README.md:81 (Table 3, Board row) asserts "AI Thinker ESP32-CAM, ESP32 with 4 MB PSRAM" as a property of the hardware. The sketch deliberately does not depend on it: .ino:235 sets fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM, and .ino:268 prints "PSRAM: found / NOT found" as a boot diagnostic. README.md:154-155 then correctly explains the degraded behaviour. The code is right; Table 3 is the li  
  Evidence: `esp_32_cam_code/README.md:81`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:235`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:268`
- **The one real hardware diagram is named in prose but never shown** — RO1.1, minor  
  README.md:7 says "the firmware for the camera board in `diagram.png`", in backticks as a filename, but no markdown image line points at it. I grepped every .md, .txt and .html in all four repos for 'diagram.png': the only two hits are this line and the identical line in esp_32_sensor_network_code/README.md:7. So a reader on GitHub is told a diagram exists and never sees it, while the 1.86 MB decorative banner at READ  
  Evidence: `esp_32_cam_code/README.md:7`, `esp_32_cam_code/README.md:3`, `esp_32_cam_code/diagram.png`

### Across repos (3)

- **flame_raw is fabricated in both modes and the classifier calibrates against it** — RO1.1, major  
  The payload always sends flame_raw as 400 when the flame bit is set and 3900 when it is not (ino:195) — in real mode too, since PIN_FLAME_AO GPIO 32 (config.h:80) is analogRead only once, as a random seed (ino:286), and readRealSensors reads only the digital DO (ino:139). The service documents the field as a measurement: 'analog AO, lower = brighter IR source' (main.py:92). Worse, fire-classification-service converts  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:195`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:286`, `fire_detection_and_classification_web_app/fire-classification-service/constants.py:51`
- **Default zone disagrees across the home/industrial split: kitchen on the node, fabric-store on the server** — RO1.1 (home/industry), minor  
  The sketch and its private copy default ZONE_ID to 'kitchen', a home zone (config.example.h:48, config.h:40, config-sensor-node.h:40), and mock_sender.py hard-codes only the eight home zones (mock_sender.py:44-46). But the receiving service defaults zoneId to 'fabric-store', an industrial zone (main.py:101). Nothing validates the zone against the active SITE_KEY - the service never reads SITE_KEY at all (grep of esp3  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/config.example.h:48`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:101`, `esp_32_sensor_network_code/tools/mock_sender.py:44`
- **fcm.py's channel-fallback comment contradicts the manifest default channel** — RO2.3, minor  
  fcm.py:28-29 says: "The app must create this channel; until it does, Android falls back to its default channel, which is still quieter than the fire one." But the manifest sets com.google.firebase.messaging.default_notification_channel_id to 'fire_alerts' (AndroidManifest.xml:49-51). On a handset where the app has never been launched, so createNotificationChannel (notification_service.dart:122-123) has never run, a g  
  Evidence: `fire_detection_and_classification_web_app/alert-service/fcm.py:28`, `fire_notification_and_evacuation_mobile_app/android/app/src/main/AndroidManifest.xml:49`, `fire_notification_and_evacuation_mobile_app/lib/core/notifications/notification_service.dart:122`

## Extra code — candidates for removal

Code that exists but which no objective, algorithm or scope item needs. Nothing in this list touches the home or the industrial site profiles, which stay.


### Web app (62)

- **Second YOLO and second VLM invocation path opens during FIRE CONFIRMED** — ARCH, major  
  Once the ladder reaches tier 'fire', escalation.js opens a classifier session and ticks it once per second (CLASSIFY_INTERVAL_MS=1000, escalation.js:44,386), posting the frame to /api/classify/sessions/{sid}/tick. That tick does not reuse the detection loop's results: session.py:152 POSTs the same frame to FIRE_YOLO_URL again, and session.py:168-175 calls VLM_DETAILED_URL on the session's own VlmHold cooldown. So dur  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:311-346`, `fire_detection_and_classification_web_app/fire-classification-service/session.py:136-180`, `fire_detection_and_classification_web_app/frontend/static/index.html:1754-1758`
- **557 lines of feature-adapter code duplicated byte-for-byte between two services** — NONE, major  
  ablation-service/sensor_adapter.py and fire-classification-service/sensor_adapter.py are byte-identical (259 lines, md5 94a12a03593f0be44a77d9ec225ff7f3 for both). ablation-service/vision.py and fire-classification-service/vision.py are byte-identical (86 lines, md5 bb610eafd1474ed8e32b93e16bad4ae1 for both). ablation-service/vlm_adapter.py and fire-classification-service/vlm_adapter.py (212 lines each) differ on lin  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/sensor_adapter.py:1`, `fire_detection_and_classification_web_app/fire-classification-service/sensor_adapter.py:1`, `fire_detection_and_classification_web_app/ablation-service/vision.py:1`
- **Laptop webcam is a second camera source and is the shipped default** — NONE, major  
  Chapter 3 Table 3.7 puts one ESP32-CAM in the perception layer, and the scope is one fixed camera in one zone. The dashboard ships two interchangeable frame sources: `createWebcamSource` (camera-sources.js:25-69, getUserMedia on the laptop) and `createEsp32Source` (:71-148). The webcam is the default - `sourceId: lsGet('fw.cameraSource') || 'webcam'` (index.html:1201) - and the toggle marks "Laptop Camera" as active   
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/camera-sources.js:25`, `fire_detection_and_classification_web_app/frontend/static/js/camera-sources.js:149`, `fire_detection_and_classification_web_app/frontend/static/index.html:1201`
- **sendFire posts the same fire event twice, and the second post's scene is discarded** — RO1.3 / RO3.1, major  
  escalation.js sendFire issues two POSTs to /api/events/fire for a camera fire: one inside the describeScene callback (:225-235) carrying the scene, and one immediately afterwards (:238-267) without it. The immediate post lands first (describeScene must first capture a frame and wait on /api/describe-scene), so it creates the incident with scene=None. When the scene post arrives, handle_confirmed_fire finds the incide  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:224`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:238`, `fire_detection_and_classification_web_app/alert-service/intake.py:185`
- **813-line real-recordings pipeline that has never been given an input** — RO1.4, major  
  recordings.py (258), flicker.py (84), vlm_adapter.py (212) and sensor_adapter.py (259) exist to score the user's own recorded experiments - 1 Hz resampling, zero-order hold with arrival-based rates, a 16 Hz FFT flicker estimator with a glare-rejection peak ratio, three baseline estimators, a VLM sample-and-hold with two clocks. It is the most sophisticated code in the objective and the only path that could produce a   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/recordings.py:126`, `fire_detection_and_classification_web_app/ablation-service/flicker.py:27`, `fire_detection_and_classification_web_app/ablation-service/vlm_adapter.py:143`
- **Overall: about 3,470 lines for an objective that needs a four-row table** — RO1.4, major  
  RO1.4 asks for four configurations, precision/recall/mAP/time-to-detection, and a result table. The feature is 2,717 lines of Python plus a 753-line page: six arms instead of four, two datasets, two ground-truth modes, Wilson intervals, exact McNemar, warm-up bands, a 4-class fuel confusion matrix, an FFT flicker estimator, and an async job registry with two export formats. It is genuinely oversized for the objective  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/main.py:1`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:753`, `fire_detection_and_classification_web_app/nginx/nginx.conf:90`
- **About 550 lines duplicated verbatim between ablation-service and fire-classification-service** — RO1.4, major  
  I diffed the four shared filenames. vision.py is byte-identical in both services (86 lines). sensor_adapter.py is byte-identical (259 lines). vlm_adapter.py differs by exactly one docstring line (212 lines, diff at line 144). constants.py overlaps heavily but has genuinely diverged. The two services went to real trouble to avoid duplicating the model weights (classifier_client.py:4-9, PROVENANCE.md:3-5) and then dupl  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/vision.py:1`, `fire_detection_and_classification_web_app/fire-classification-service/vision.py:1`, `fire_detection_and_classification_web_app/ablation-service/sensor_adapter.py:1`
- **Synthetic muster 42/45 can print on the report shown to participants** — RO3.4, major  
  db.py:22-24 declares `DEFAULT_MUSTER_PRESENT = 42` and `DEFAULT_MUSTER_TOTAL = 45` under the comment "Muster head-count is not tracked by the vision backend — we synthesize it", and create_incident writes both constants into EVERY incident row (db.py:351). muster_json falls back to them whenever occupancy_peak is None, returning source "estimated" (serializers.py:101-105). reports.html:332 then prints `${r.muster.pre  
  Evidence: `fire_detection_and_classification_web_app/alert-service/db.py:22`, `fire_detection_and_classification_web_app/alert-service/db.py:351`, `fire_detection_and_classification_web_app/alert-service/serializers.py:101`
- **Per-node ring buffer and /api/sensors/history have no running consumer** — ALG1, minor  
  Algorithm 1 needs only the latest sample per node. The service also keeps a 720-sample deque per node (main.py:44, allocated at main.py:234, appended at main.py:248) and exposes GET /api/sensors/history (main.py:273-283), plus a sampleCount field in the node JSON (main.py:189). Searched every repo with grep -rn "sensors/history|sampleCount": the only hits outside esp32-sensor-service/main.py are ablation-data/README.  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:44`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:273`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:189`
- **Flat node list means the accepted zone level dies with the browser tab** — ALG1, minor  
  Not extra code but extra consequence of where ALG1 lives: the accepted level A exists only as a JavaScript variable (escalation.js:52, exposed at escalation.js:368) and is passed on solely as an evidence field on outgoing events (index.html:1638 gasLevel). Nothing stores it, so the ablation service, alert-service history and the situation report cannot reconstruct what the zone level was at any past moment. For a viv  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:52`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:368`, `fire_detection_and_classification_web_app/frontend/static/index.html:1638`
- **Config comments document a third site key, unit7, that does not exist** — NONE, minor  
  Q6 answered. .env:21 says 'Which facility to load from alert-service/sites/. `unit7` is the demonstration hall' and .env:30 says 'Blank uses the radius in the site file: 6 m for unit7, 2 m for home'. The same two lines appear in firewatch-private-files/.env:21 and :30. There is no unit7.json - `find . -name '*.json' -path '*sites*'` returns exactly home.json and industrial.json. sample.env:21 and :30 were already cor  
  Evidence: `fire_detection_and_classification_web_app/.env:21`, `fire_detection_and_classification_web_app/.env:30`, `fire_detection_and_classification_web_app/sample.env:21-30`
- **HAZARD_RADIUS_M override is a demo knob no objective requires** — NONE, minor  
  sites.py:38 reads `_RADIUS_OVERRIDE = os.getenv("HAZARD_RADIUS_M", "")` and line 181 lets it replace the per-site `hazardRadiusM` for whichever site loads. It is plumbed through docker-compose.yml:167 and .env:33, and both ship it blank. No objective, algorithm or scope item in the brief calls for a runtime radius override, and it directly undercuts the argument the code itself makes at sites/README.md:13-19 and .env  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites.py:36-38`, `fire_detection_and_classification_web_app/alert-service/sites.py:180-181`, `fire_detection_and_classification_web_app/docker-compose.yml:167`
- **zero_vlm_channels is dead code** — NONE, minor  
  combos.zero_vlm_channels() is defined and documented at length but is never called - grep for 'zero_vlm_channels' across the repo returns only the definition. The modality matrix it was written to enforce (COMBO_MODALITIES) is only rendered in the UI as dots; no arm's input is ever masked. Nothing breaks today because the arms that exclude the VLM read either sensor_model's own probabilities or raw YOLO columns, but   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:287`, `fire_detection_and_classification_web_app/ablation-service/constants.py:150`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:339`
- **Warm-up false-alarm profile serves no objective** — NONE, minor  
  warmup_profile() computes each arm's false-alarm rate in six bands of session position (0-5, 5-15, 15-30, 30-60, 60-120, 120+ s) and the page renders it as a colour-graded heat table. No objective, algorithm or Ch.3 analysis asks for it; s3.4.4 asks for a false-alarm rate, a per-source breakdown and a paired comparison. It is a genuinely interesting finding about the model's rolling features, but it is roughly 105 li  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:136`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:400`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:562`
- **Out-of-distribution split is a second study bolted onto RO1.4's page** — NONE, minor  
  ood_split.csv is 16,200 rows / 90 experiments of three untrained fuels (PVC, polystyrene, magnesium/lithium), 3.0 MB, all labelled 'unknown'. RO1.4 asks for an ablation over four configurations on the evaluation dataset; novelty detection belongs to Ch.3's RQ3 row (AUROC for out-of-distribution detection). It also forces special-case code: degenerate_binary handling, dropping the fuel table, a fuel_note, and a warnin  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/runs.py:56`, `fire_detection_and_classification_web_app/ablation-service/runs.py:176`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:472`
- **557 lines duplicated byte-for-byte between ablation-service and fire-classification-service** — NONE, minor  
  sensor_adapter.py (259 lines) and vision.py (86 lines) are identical files in both services (diff -q reports no difference), and vlm_adapter.py (212 lines) differs only in one docstring word at line 144. vision.py:12 claims 'the live path and the recordings path compute them identically, from the same code' - they are two copies of the same text, not the same code, so a fix to one silently leaves the other behind. Tw  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/sensor_adapter.py:1`, `fire_detection_and_classification_web_app/fire-classification-service/sensor_adapter.py:1`, `fire_detection_and_classification_web_app/ablation-service/vision.py:12`
- **Two ground-truth modes where the thesis defines one** — NONE, minor  
  build_truth() supports 'strict' (pre-ignition windows are negatives, the thesis definition via t0) and 'as_trained' (the whole fire run positive, to reproduce the published metrics.csv). The API validates it, the UI offers a selector, and every export records which was used. Ch.3 line 682 fixes one definition, so the second mode exists purely to cross-check the training metrics - honest, but one more switch to defend  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:70`, `fire_detection_and_classification_web_app/ablation-service/main.py:212`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:247`
- **Sensor history endpoint and its 720-sample ring buffer have no consumer** — NONE, minor  
  `GET /api/sensors/history` (esp32-sensor-service/main.py:273-283) is documented in its own docstring as "for sparklines and debugging". I searched all four repos with `rg -n "sensors/history"` and `rg -n "sampleCount"`: the only hits are the definition itself and a passing mention in ablation-data/README.md:62. No dashboard code, no nginx route (nginx.conf:74 proxies the whole /api/sensors/ prefix but nothing calls t  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:273`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:278`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:234`
- **SQLite migration block is a no-op on every fresh clone** — NONE, minor  
  `_ADDED_COLUMNS` (alert-service/db.py:204-227) lists 22 incident columns and `_migrate` (:230-236) ALTERs each one in if it is absent. I checked every one of the 22 names against the `CREATE TABLE IF NOT EXISTS incidents` DDL at db.py:113-198: all 22 are already declared there. On any fresh clone `_migrate` reads PRAGMA table_info and adds nothing. It exists only for a developer's own alert-data volume left over from  
  Evidence: `fire_detection_and_classification_web_app/alert-service/db.py:204`, `fire_detection_and_classification_web_app/alert-service/db.py:230`, `fire_detection_and_classification_web_app/alert-service/db.py:113`
- **Unreferenced esp32 still-image endpoint** — NONE, minor  
  `GET /api/esp32/still` (esp32-cam-service/main.py:275-305, 31 lines) proxies one higher-quality JPEG from the board. I searched all four repos with `rg -n "esp32/still"`: the only hits are the definition and the module docstring. No frontend JS or HTML fetches it, no test, and nginx.conf has no exact-match route for it (it is reachable only incidentally through the /api/esp32/ prefix at nginx.conf:57). The detection   
  Evidence: `fire_detection_and_classification_web_app/esp32-cam-service/main.py:275`, `fire_detection_and_classification_web_app/esp32-cam-service/main.py:292`, `fire_detection_and_classification_web_app/esp32-cam-service/main.py:335`
- **Certificate script superseded by the nginx Dockerfile** — NONE, minor  
  nginx/generate-certs.sh (19 lines) generates a self-signed cert into ./certs on the host. `rg -n "generate-certs" .` across the repo returns no hit other than the file itself - not in nginx/Dockerfile, not in docker-compose.yml, not in README.md. nginx/Dockerfile:8-17 already runs openssl at build time and writes the cert to /etc/nginx/certs, which is where nginx.conf:13-14 reads it from. The script also writes to a   
  Evidence: `fire_detection_and_classification_web_app/nginx/generate-certs.sh:1`, `fire_detection_and_classification_web_app/nginx/Dockerfile:8`, `fire_detection_and_classification_web_app/nginx/nginx.conf:13`
- **python-multipart declared but never used in two services** — NONE, minor  
  alert-service/requirements.txt:4 and ablation-service/requirements.txt:19 both declare `python-multipart`, which FastAPI needs only for `Form`/`File`/`UploadFile` parameters. `rg -n "UploadFile|File\(|Form\(" alert-service/ ablation-service/` returns nothing at all: both services take JSON bodies only. The three services that do need it (frontend, vlm-service, fire-classification-service) declare it correctly.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/requirements.txt:4`, `fire_detection_and_classification_web_app/ablation-service/requirements.txt:19`, `fire_detection_and_classification_web_app/alert-service/app.py:15`
- **1.6 MB decorative cover image tracked for one README line** — NONE, minor  
  docs/web_app_cover_image.png is 1.6 MB, the fourth-largest tracked file after the two model weights and the two CSV splits. Its only reference is the banner at README.md:3. No objective, algorithm or Chapter 3 figure depends on it, and docs/ holds nothing else.  
  Evidence: `fire_detection_and_classification_web_app/docs/web_app_cover_image.png:1`, `fire_detection_and_classification_web_app/README.md:3`
- **Dead CORS middleware on a service no browser can reach** — RO1.2, minor  
  fire-detection-yolo-service/main.py:10-15 installs CORSMiddleware with allow_origins=["*"]. No browser ever calls this service: docker-compose.yml:9-10 uses expose (not ports), so port 8000 is not published to the host, and nginx/nginx.conf has no route to it (grep for 'fire-detection-yolo-service' in nginx.conf returns nothing; its proxy_pass targets are frontend, esp32-cam-service, esp32-sensor-service, ablation-se  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:10`, `fire_detection_and_classification_web_app/docker-compose.yml:9`, `fire_detection_and_classification_web_app/nginx/nginx.conf:22`
- **best.pt carries optimizer, EMA and scaler state that inference never reads** — RO1.2, minor  
  The tracked 15.9 MB checkpoint holds keys epoch, best_fitness, model, ema, updates (1738), optimizer (full SGD momentum buffers for ~190 parameter groups), scaler, train_args, train_metrics, train_results, date, version, git, license, docs. Inference reads only `model`/`ema`; a stripped yolo11n detection checkpoint is roughly a third of the size. This is the largest binary in the repo and it is versioned, so every re  
  Evidence: `fire_detection_and_classification_web_app/fire-detection-yolo-service/best.pt (archive/data.pkl top-level keys; 15,914,465 bytes)`, `fire_detection_and_classification_web_app/fire-detection-yolo-service/main.py:18`
- **The YOLO label-and-threshold adapter exists twice, byte for byte** — RO1.2, minor  
  `diff fire-classification-service/vision.py ablation-service/vision.py` reports no differences: two identical 86-line copies define FIRE_LABELS/SMOKE_LABELS, the union-area computation and the 0.35 gate. RO1.2's contract with the rest of the system - what a class is called and when a box counts - is therefore defined in two files that must be edited together, and the class-name coupling described in the 'flame' findi  
  Evidence: `fire_detection_and_classification_web_app/fire-classification-service/vision.py:1-86`, `fire_detection_and_classification_web_app/ablation-service/vision.py:1-86`
- **reportFire() is dead code: 53 lines, no caller anywhere** — RO1.2, minor  
  `grep -rn "reportFire"` over the whole web app repo returns exactly one line - the definition at index.html:1612. Nothing calls it. Its job was taken over by escalation.js:206 sendFire(), which posts to the same /api/events/fire endpoint. Its sibling reportClear (index.html:1667) is likewise superseded by escalation.js:286 sendClear; escalation.js:1772 comments "Reporting to alert-service moved there too, so one plac  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612-1664`, `fire_detection_and_classification_web_app/frontend/static/index.html:1667-1675`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:206`
- **Dead pre-escalation alarm path: reportFire, reportClear and S.reported** — RO1.3, minor  
  `reportFire()` (index.html:1612-1664) has no caller anywhere - grep 'reportFire' in the whole repo returns only the definition at :1612. `reportClear()` (:1667-1675) has exactly one call site, `if (S.reported) reportClear();` at :2094, and `S.reported` is never assigned true: grep 'S.reported' returns :2094, :2096 (= false), :2125 (= false) and nothing else. Both are the pre-ladder alarm path that escalation.js repla  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1667`, `fire_detection_and_classification_web_app/frontend/static/index.html:2094`
- **reportFire() in index.html is dead code superseded by escalation.js sendFire** — RO1.3, minor  
  index.html:1612-1664 defines an async reportFire(vlm) that posts /api/events/fire with the real box confidence but no severity, no verification and no scene. grep for 'reportFire(' over index.html returns only the definition at :1612 - no call site. The comment at index.html:1767-1772 confirms reporting moved to Escalation. Its sibling reportClear() at :1667-1675 is still live (called at :2094), so only reportFire is  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1767`, `fire_detection_and_classification_web_app/frontend/static/index.html:2094`
- **A debug constant can switch the whole verification layer off** — RO1.3, minor  
  index.html:1134 declares const VLM_CONFIRM_REQUIRED = true with the comment 'set false to alarm on YOLO alone (useful for debugging)'. It is read once, at index.html:1775, where setting it false makes vlmConfirmed unconditionally true - which turns every YOLO box into a FIRE CONFIRMED and deletes RO1.3's verification layer from the running system. It is currently true, so the shipped behaviour is correct, but it is a  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1134`, `fire_detection_and_classification_web_app/frontend/static/index.html:1775`
- **Debug flag that would bypass the verification layer RO1.3 is about** — RO1.3, minor  
  `const VLM_CONFIRM_REQUIRED = true; // set false to alarm on YOLO alone (useful for debugging)` (index.html:1134). It is used once, at index.html:1775, as `vlmConfirmed: VLM_CONFIRM_REQUIRED ? (vlm.detected === true) : true`. Shipped as `true`, the false branch is unreachable. Its only purpose is to let a developer switch off exactly the VLM confirmation that RO1.3 claims cuts false alarms by 50 per cent and that Alg  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1134`, `fire_detection_and_classification_web_app/frontend/static/index.html:1775`
- **The 60 s proxy timeout means one hung call blocks verification for a minute** — RO1.3 / Alg.3, minor  
  Not a thesis mismatch - the thesis gives no VLM timeout number - but worth a decision before the viva. VLM_TIMEOUT is 60 s (server.py:22), and the single-in-flight guard S.pendingVlm is only released in .finally() (index.html:1801). So a single hung Gemini call blocks all verification for up to 60 s while the detection loop keeps running at 500 ms. During that window vlmAvailable and vlmConfirmed hold their previous   
  Evidence: `fire_detection_and_classification_web_app/frontend/server.py:22`, `fire_detection_and_classification_web_app/frontend/static/index.html:1801`, `fire_detection_and_classification_web_app/vlm-service/main.py:30`
- **The 'rejected' verification branch in sendFire is unreachable** — RO1.3 / Algorithm 2, minor  
  sendFire is only called from evaluate() when `S.alarm && !S.reported` (escalation.js:167), and S.alarm is true only for tier 'fire' or 'danger' (:164). Tier 'fire' requires `S.vlmConfirmed || !S.vlmAvailable` (:148) and tier 'danger' short-circuits to 'not_applicable'. So the `: 'rejected'` arm of the ternary at :258 (and its twin at :230-231) can never be taken. Harmless, but it is three lines of arbitration code th  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:164`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:167`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:230`
- **zero_vlm_channels in combos.py is never called** — RO1.4, minor  
  `zero_vlm_channels` (ablation-service/combos.py:287-304, 18 lines) builds a frame with the eleven VLM channels zeroed, for a combination that excludes the VLM. `grep -rn "zero_vlm" .` over the whole repo returns exactly one hit: the definition. The combinations that exclude the VLM never call it - combo1 (:144) goes straight to the classifier client for the sensors-only probabilities, and combo2 (:157) and combo4 (:2  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:287`, `fire_detection_and_classification_web_app/ablation-service/combos.py:144`, `fire_detection_and_classification_web_app/ablation-service/combos.py:157`
- **zero_vlm_channels is dead code, defined and never called** — RO1.4, minor  
  combos.py:287-304 defines an 18-line helper with a careful docstring explaining that it sets the eleven VLM channels to their never-invoked values. grep -rn 'zero_vlm_channels' across every .py file in the repo returns exactly one hit: the definition. Modality isolation is achieved structurally instead - combination 1 reads sensor_model's own probabilities (combos.py:152), and combinations 2 to 5 are rules over expli  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:287`, `fire_detection_and_classification_web_app/ablation-service/combos.py:152`
- **ClassifierClient.score returns an alignment frame that nothing reads** — RO1.4, minor  
  classifier_client.py:116-117 builds an 'order' DataFrame from the service's returned experiment_id and window_idx, and the docstring at classifier_client.py:71-73 claims 'Rows are realigned against that here rather than assuming the input order survived'. No realignment happens: runs.py:129 calls sorted_like_service(frame) and reproduces the sort locally instead. grep for '\["order"\]' over ablation-service returns o  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/classifier_client.py:116`, `fire_detection_and_classification_web_app/ablation-service/classifier_client.py:71`, `fire_detection_and_classification_web_app/ablation-service/runs.py:129`
- **Combination 3, a VLM-only arm, is not required by any objective and contradicts Algorithm 3** — RO1.4, minor  
  Algorithm 3 states the VLM cannot create a fire event on its own, only confirm or reject a YOLO box. combo3_vlm (combos.py:194-200) does exactly that: it alarms on max(vlm_flame_conf, vlm_smoke_conf) > 0.30 with no YOLO gate, and constants.py:220-223 says so outright - 'Invoked on a FIXED 4s cadence, never on the YOLO gate - a VLM-only arm that waited for YOLO would not be VLM-only.' It is scientifically interesting   
  Evidence: `fire_detection_and_classification_web_app/ablation-service/combos.py:194`, `fire_detection_and_classification_web_app/ablation-service/constants.py:220`, `fire_detection_and_classification_web_app/ablation-service/constants.py:141`
- **The warm-up false-alarm profile serves no objective** — RO1.4, minor  
  warmup_profile (metrics.py:136-169, 34 lines) bins false-alarm rate by position in the session across six bands, and ablation.html:563-600 renders it as a heatmap card with explanatory prose. No objective, algorithm or analysis-plan row in chapter_3.txt asks for it. It is a genuinely good finding - the code says combination 6's quiet-room false-alarm rate is 0.72 between windows 5 and 30 and exactly 0.00 after window  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/metrics.py:136`, `fire_detection_and_classification_web_app/frontend/static/ablation.html:563`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:400`
- **Dead pre-escalation reporting path in the dashboard** — RO2.1, minor  
  reportFire (index.html:1612-1664) is never called - grep for reportFire finds only the definition and one comment at 1475. reportClear (1667-1676) is called once, at 2094, guarded by S.reported, which is only ever assigned false (2096, 2125) because escalation.js took over reporting (its own S.reported at evaluate(), escalation.js:166-168). Both duplicate escalation.js sendFire/sendClear, including a second occupancy  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612-1664`, `fire_detection_and_classification_web_app/frontend/static/index.html:1667-1676`, `fire_detection_and_classification_web_app/frontend/static/index.html:2094-2096`
- **Synthetic 42-of-45 muster machinery duplicates the real head-count** — RO2.1, minor  
  Alongside occupancy{current,peak} and the check-out table, a third representation exists: DEFAULT_MUSTER_PRESENT=42 / DEFAULT_MUSTER_TOTAL=45 (db.py:22-24), the muster_present/muster_total columns written on every incident (db.py:125-126, 351), bump_muster (db.py:654-659), the deprecated POST /api/incidents/{id}/ack that drives it (app.py:382-397), muster_json with its 42/45 fallback (serializers.py:100-105), and Mus  
  Evidence: `fire_detection_and_classification_web_app/alert-service/db.py:22-24`, `fire_detection_and_classification_web_app/alert-service/db.py:351`, `fire_detection_and_classification_web_app/alert-service/db.py:654-659`
- **Two tuning env vars on the person service that nothing ever sets** — RO2.1, minor  
  main.py:40-43 exposes HUMAN_IOU (default 0.7) and HUMAN_IMGSZ (default 640) as environment overrides "exposed for tuning". Nothing sets them: I grepped for HUMAN_IOU and HUMAN_IMGSZ in docker-compose.yml, .env and sample.env and there are no hits; docker-compose.yml:23-26 passes HUMAN_MIN_CONF only. Both values must in fact stay at their training values for the recorded metrics to mean anything, which the comments th  
  Evidence: `fire_detection_and_classification_web_app/human-detection-yolo-service/main.py:40`, `fire_detection_and_classification_web_app/docker-compose.yml:23`
- **Per-edge wM weight override is unused by both site files** — RO2.2, minor  
  `sites.load` supports an explicit `wM` per edge with a validation guard that rejects a weight shorter than the straight line. `grep -c wM sites/*.json` returns 0 for both files, so all 16 home edges and all 20 industrial edges take the Euclidean default. The feature is documented in sites/README.md as the way to model a segment that is honestly longer to walk than it looks, so it is a small, explainable config path r  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites.py:134-144`, `fire_detection_and_classification_web_app/alert-service/sites/home.json:200-265`, `fire_detection_and_classification_web_app/alert-service/sites/industrial.json:214-295`
- **FCM polyline-truncation path can never fire** — RO2.2, minor  
  fcm.py:112 sets `_MAX_POLYLINE_CHARS = 900` and fcm.py:119-123 blanks the polyline and sets a `routePolylineTruncated` flag when it is exceeded. I measured the serialised string over all 113 fire/occupant pairs on both sites: the longest is 47 characters. The flag is also never read — grepping both repos for `routePolylineTruncated` returns only the line that writes it (fcm.py:135), and models.dart:504-538 `fromFcm`   
  Evidence: `fire_detection_and_classification_web_app/alert-service/fcm.py:112`, `fire_detection_and_classification_web_app/alert-service/fcm.py:135`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:504`
- **Two evidence fields are assembled and posted but never read** — RO3.1, minor  
  sceneEvidence() builds five fields (index.html:1634-1640): fireAreaRatio, smokeBoxes, fireBoxes, gasLevel and occupancy. report.py reads only fuelType, fireAreaRatio, smokeBoxes and occupancy - I grepped report.py for every 'ev.get' and 'ev[' and those four lines (82, 127, 180, 222) are all of them. fireBoxes and gasLevel travel over the wire on every fire event and are never used. gasLevel is arguably worth keeping   
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1637`, `fire_detection_and_classification_web_app/alert-service/report.py:82`, `fire_detection_and_classification_web_app/alert-service/report.py:222`
- **reportFire() is dead code and holds the only copy of sceneEvidence** — RO3.1, minor  
  async function reportFire(vlm) (index.html:1612-1664) posts its own /api/events/fire without scene or evidence, duplicating what escalation.js sendFire now owns ("Reporting to alert-service moved there too, so one place owns the decision", index.html:1770-1772). grep for reportFire across frontend/static finds the definition and no call site. It survives only because sceneEvidence is nested inside it - which is preci  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1646`, `fire_detection_and_classification_web_app/frontend/static/index.html:1770`
- **Two evidence fields are produced, never read and never stored** — RO3.1, minor  
  sceneEvidence returns five keys (index.html:1635-1639). report.py reads only fireAreaRatio (l.127), smokeBoxes (l.180), occupancy (l.222) and fuelType (l.85). fireBoxes and gasLevel are read by nothing: grep across the web app and the mobile app finds gasLevel only in sceneEvidence, report.py's docstring and test_report.py:110 (the test that proves it is ignored), and fireBoxes only at its own definition. Since the e  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1635`, `fire_detection_and_classification_web_app/alert-service/report.py:127`, `fire_detection_and_classification_web_app/alert-service/test_report.py:110`
- **modelLimits is returned by /api/extinguishers and read by nobody** — RO3.2, minor  
  app.py:444-450 adds a 'modelLimits' list to the response. grep -rn for 'modelLimits' and 'model_limits' across *.py, *.html, *.dart and *.js in all four repos returns exactly one hit: the line that creates it. Its two sentences duplicate the liquid_fuel 'caution' (extinguishers.py:84-88) and UNIVERSAL_CAUTIONS[0] (lines 115-122), both of which ARE rendered on the dashboard. No objective needs a third copy.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:444`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:84`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:114`
- **modelLimits is produced by the API and consumed by nothing** — RO3.2, minor  
  GET /api/extinguishers returns a modelLimits list of two sentences. A grep for 'modelLimits|model_limits' across all four repos returns exactly two hits: this definition and a mention in THESIS_CHANGES.md. No dashboard, reports page or Flutter model reads it. Both sentences already exist twice over — in the extinguishers.py module docstring and, for the class F one, in liquid_fuel['caution'] which IS rendered.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:444-449`, `fire_detection_and_classification_web_app/alert-service/extinguishers.py:21-33,84-88`
- **Second universal caution has no thesis anchor** — RO3.2, minor  
  UNIVERSAL_CAUTIONS[1], 'Only fight a fire you can walk away from', is general fire-safety advice. Nothing in Table 3.11, RO3.2, the five-layer architecture or the four algorithms asks for it. UNIVERSAL_CAUTIONS[0] by contrast does carry a Table 3.11 cell (water near live electrical equipment), so only the second entry is unanchored.  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:123-129`, `scratchpad/thesis/chapter_3.txt:327-348`
- **Dead pre-escalation reporting path: reportFire, reportClear, S.reported, S.tier** — RO3.3, minor  
  escalation.js took over all reporting to alert-service in commit bf13b76, and the dashboard's own copy was left behind. `reportFire` (index.html:1612-1664) is never called - grep gives only the definition and a prose comment at 1475. `reportClear` (1667-1676) is called once, at 2094, guarded by `if (S.reported)`, and `S.reported` is only ever assigned false (1173, 2096, 2125) - never true - so that call is unreachabl  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1612`, `fire_detection_and_classification_web_app/frontend/static/index.html:1667`, `fire_detection_and_classification_web_app/frontend/static/index.html:2094`
- **VLM_CONFIRM_REQUIRED debug switch on the alarm path** — RO3.3, minor  
  `const VLM_CONFIRM_REQUIRED = true;` with the comment 'set false to alarm on YOLO alone (useful for debugging)' (index.html:1134). Its single use is `vlmConfirmed: VLM_CONFIRM_REQUIRED ? (vlm.detected === true) : true` (index.html:1775). No objective needs a switch that turns off VLM verification, and Alg.2 requires a box plus a VLM confirmation, or a box plus sensors when the VLM is unavailable - a build flag that f  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/index.html:1134`, `fire_detection_and_classification_web_app/frontend/static/index.html:1775`
- **Dashboard carries a laptop-webcam frame source beyond the one fixed camera** — ARCH, info  
  Table 3.7's perception layer is one "ESP32-CAM module for the video stream", and Ch.3 s3.2.1 scopes the prototype to one fixed camera. camera-sources.js exposes two interchangeable sources behind one interface: createEsp32Source (the proxied MJPEG, in scope) and createWebcamSource, a getUserMedia/<video> laptop webcam with its own track-ended handling. The second source is what makes the dashboard demonstrable with n  
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/camera-sources.js:25-67`, `fire_detection_and_classification_web_app/frontend/static/js/camera-sources.js:149`, `fire_detection_and_classification_web_app/nginx/Dockerfile:8-17`
- **Empty .gitkeep alongside two tracked CSVs in the same directory** — NONE, info  
  ablation-service/data/.gitkeep is a zero-byte tracked placeholder. Its job is to keep data/ present in a fresh clone, but the same directory now tracks ood_split.csv and test_split.csv, so the directory cannot be empty. ablation-service/Dockerfile:15 copies `data/` wholesale, so the placeholder also ships into the image.  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/data/.gitkeep:1`, `fire_detection_and_classification_web_app/ablation-service/data/test_split.csv:1`, `fire_detection_and_classification_web_app/ablation-service/data/ood_split.csv:1`
- **Commented-out COPY in the frontend Dockerfile contradicts the real build** — NONE, info  
  frontend/Dockerfile:16-17 carries `# Optional: copy fire_alarm.mp3 if it exists next to the Dockerfile` and a commented `# COPY fire_alarm.mp3 static/`. The file actually lives at frontend/static/fire_alarm.mp3 and is already copied by `COPY static/ static/` at line 19, so the comment describes a layout the repo does not have and would mislead anyone editing the image.  
  Evidence: `fire_detection_and_classification_web_app/frontend/Dockerfile:16`, `fire_detection_and_classification_web_app/frontend/Dockerfile:19`, `fire_detection_and_classification_web_app/frontend/static/fire_alarm.mp3:1`
- **Demo test-alert endpoint with a cooldown bypass, kept alive by the test suite** — NONE, info  
  `POST /api/test-alert` (alert-service/app.py:517-549) fabricates an incident with a hard-coded occupancy of 7, a hard-coded confidence of 0.92 and a hard-coded description about fabric rolls, and calls handle_confirmed_fire with `force=True`, which skips the cooldown (intake.py:132-133, :221). It is pure demo scaffolding - no objective needs it. But it is not freely removable: alert-service/test_api.py drives its che  
  Evidence: `fire_detection_and_classification_web_app/alert-service/app.py:517`, `fire_detection_and_classification_web_app/alert-service/intake.py:132`, `fire_detection_and_classification_web_app/alert-service/intake.py:221`
- **GET /api/sensors/history and its 720-sample buffer have no consumer** — RO1.1, info  
  main.py:273-283 serves per-node sample history, backed by the 720-deep deque (main.py:44, 234, 248). rg -n 'sensors/history' across all four repos finds only the endpoint itself and one prose mention in ablation-data/README.md:62; the dashboard never calls it — rg -n 'history' over frontend/static/js/sensor-panel.js and frontend/static/index.html returns nothing, and sensor-panel.js polls only /api/sensors/latest (se  
  Evidence: `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:273`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:248`, `fire_detection_and_classification_web_app/frontend/static/js/sensor-panel.js:152`
- **Client hard-codes a 120 s warning cooldown the server already enforces and can retune** — RO1.3, info  
  escalation.js:40 sets `WARNING_COOLDOWN_MS = 120000` with the comment "Matches alert-service's COOLDOWN_SECONDS", and gates sendWarning at :177. alert-service already gates the same thing in handle_warning at intake.py:287 against `COOLDOWN_SECONDS`, read from the environment at intake.py:22 and exposed as a tunable at sample.env:38. Set COOLDOWN_SECONDS=60 in .env and the browser still refuses to send for 120 s, so   
  Evidence: `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:40`, `fire_detection_and_classification_web_app/frontend/static/js/escalation.js:177`, `fire_detection_and_classification_web_app/alert-service/intake.py:22`
- **Real-recording ablation path is wired up but ships with no data to run it on** — RO1.4, info  
  ablation-service/recordings.py (258 lines) and flicker.py (84 lines) implement the recordings branch: runs.py:40 imports recordings, :88 lists them, :202-250 runs them, and nginx.conf:90-97 carries a 600 s timeout and a 512 M body cap specifically for it. But .gitignore:17-18 excludes `ablation-data/*` except its README, and `ls ablation-data/` shows only README.md. On any fresh clone this whole branch has zero input  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/recordings.py:90`, `fire_detection_and_classification_web_app/ablation-service/flicker.py:27`, `fire_detection_and_classification_web_app/ablation-service/runs.py:40`
- **Overall: the service is not oversized, but about 15 percent of it answers questions RO1.4 did not ask** — RO1.4, info  
  Judging size honestly: ablation-service is 2,717 lines of Python plus a 753-line page. Most of it is load-bearing for RO1.4 and RO1.3 - the six arms, the two-level metrics, the two ground-truth definitions, the provenance in every export, the recordings pipeline. The parts that exceed the objective are the two extra combinations (3 and 5), the warm-up profile, the two-sided false-alarm split, the fuel confusion table  
  Evidence: `fire_detection_and_classification_web_app/ablation-service/main.py:1`, `fire_detection_and_classification_web_app/ablation-service/metrics.py:404`, `fire_detection_and_classification_web_app/ablation-service/combos.py:252`
- **A GAS DANGER incident also gets a full hazard-pruned route** — RO2.2, info  
  `severity="gas_danger"` flows through `handle_confirmed_fire`, so `_attach_route` runs and a route is generated around the zone's authored `firePoint` even though nothing is burning and no fire position was detected. RO2.2 scopes the route to "a confirmed detection" and Algorithm 2 makes GAS DANGER a separate state. It is defensible - GAS DANGER raises an alarm and opens an incident, so occupants still need a way out  
  Evidence: `fire_detection_and_classification_web_app/alert-service/intake.py:232`, `fire_detection_and_classification_web_app/alert-service/app.py:538-546`, `fire_detection_and_classification_web_app/alert-service/routing.py:309-311`
- **Two configuration knobs no objective needs** — RO2.2, info  
  sites.py:135 supports a per-edge `wM` weight override with a typo guard at sites.py:136-141, documented at sites/README.md:47-51 — but `grep -c wM sites/*.json` returns 0 for both files, so every edge in the system uses the straight-line default. Separately, `HAZARD_RADIUS_M` (sites.py:38, docker-compose.yml:167, sample.env:33) and `compute_route`'s `hazard_radius_m` parameter (routing.py:170) let a demo retune the b  
  Evidence: `fire_detection_and_classification_web_app/alert-service/sites.py:135`, `fire_detection_and_classification_web_app/alert-service/sites/README.md:47`, `fire_detection_and_classification_web_app/alert-service/sites.py:38`
- **first_action_why is a fourth column Table 3.11 does not ask for** — RO3.2, info  
  Table 3.11 has four columns and attaches a reason only to the 'must not be used' column. The code adds a first_action_why paragraph to every entry, rendered on both the dashboard and the reports page. For gas fire it must stay — it is the only place the thesis's 'unburnt gas can build up and cause an explosion' reason lives. For solid combustible and liquid fuel it is prose beyond the table, and the liquid-fuel one d  
  Evidence: `fire_detection_and_classification_web_app/alert-service/extinguishers.py:47-51,69-72,95-98`, `fire_detection_and_classification_web_app/frontend/static/index.html:2244`, `fire_detection_and_classification_web_app/frontend/static/reports.html:339`

### Mobile app (21)

- **Offline demo route draws a path Dijkstra never produced** — Alg.4, major  
  Each FloorPlan carries a hard-coded `defaultRoute`, `youAt`, `fireAt` and `musterAt` (floor_plan_data.dart:62-65; industrial values at 170-178, home values at 258-266). When an incident arrives with no route, incident_screen.dart:99 sets `drawableRoute = null` but still renders the plan (incident_screen.dart:186). FloorPlanPainter then falls back to those constants: `_line` returns `plan.defaultRoute` (floor_plan_pai  
  Evidence: `lib/shared/floor_plan/floor_plan_data.dart:60`, `lib/shared/floor_plan/floor_plan_data.dart:170`, `lib/shared/floor_plan/floor_plan_data.dart:258`
- **Fake "Call emergency services" dialog, duplicated in two screens** — NONE, major  
  `_callEmergency` shows an AlertDialog reading 'Dialing fire & rescue service…' and then does nothing. The body is byte-identical in two files (I diffed resolved_screen.dart:43-58 against incident_screen.dart:50-63; only the signature differs). Nothing can actually dial: `grep -rn "url_launcher|tel:|launchUrl" lib pubspec.yaml` returns no matches, and pubspec.yaml:30-40 declares no dialling package. On the incident sc  
  Evidence: `lib/features/resolved/resolved_screen.dart:43`, `lib/features/resolved/resolved_screen.dart:48`, `lib/features/resolved/resolved_screen.dart:130`
- **MusterRoll model is dead and injects a fabricated 42-of-45 head count** — RO2.3, major  
  `MusterRoll` (models.dart:293-307) is required on every `Incident` (models.dart:707, 721) and parsed on every fetch (models.dart:768), but no widget ever reads it: `grep -rnw "MusterRoll" lib test` and `grep -rn "\.muster\b|\.present\b|\.total\b|\.missing\b" lib/features lib/shared` return only the model definition and construction sites — never a render. `missing` (models.dart:299) has zero references anywhere. Beca  
  Evidence: `lib/data/models/models.dart:293`, `lib/data/models/models.dart:299`, `lib/data/models/models.dart:302`
- **Nine dead toJson methods in a read-only client** — NONE, minor  
  models.dart defines ten `toJson()` methods (lines 242, 282, 306, 329, 397, 596, 787, 819, 869, 1001). `grep -rn "toJson()" lib test` outside models.dart returns exactly one hit: severity_test.dart:102 calling `Zone.toJson()`. `Incident.toJson` (787-798) calls six of the others, but `Incident.toJson` itself is never called by anything. The app never POSTs a model — ApiClient only sends `{token, platform, label}`, `{to  
  Evidence: `lib/data/models/models.dart:282`, `lib/data/models/models.dart:306`, `lib/data/models/models.dart:329`
- **Lock-screen mock-up leftovers survive after the screen was deleted** — NONE, minor  
  The app used to draw its own fake lock screen; notification_service.dart:204-208 records that it was removed because it 'would have put a mock-up in front of the RO3.4 participants'. Its support code was left behind. Zero references outside their own declarations: `AppColors.lockGlass` (app_tokens.dart:63), `AppGradients.lock` (app_tokens.dart:175-181), `lockDate` (format.dart:29-31), `clockTime` (format.dart:33-37)   
  Evidence: `lib/core/notifications/notification_service.dart:204`, `lib/core/theme/app_tokens.dart:63`, `lib/core/theme/app_tokens.dart:175`
- **Unused PillVariant.brand drags three unused design tokens with it** — NONE, minor  
  `PillVariant.brand` (pill_button.dart:9, switch arm 55-61) is never passed by any screen. I counted `PillVariant.<v>` outside pill_button.dart: primary 1, danger 2, safe 1, ghost 1, brand 0. That arm is the sole consumer of `AppGradients.brand` (app_tokens.dart:153-158) and `AppShadows.brand` (app_tokens.dart:123-129) — confirmed by `grep -rn "AppGradients.brand|AppShadows.brand" lib`, which returns only pill_button.  
  Evidence: `lib/shared/widgets/pill_button.dart:9`, `lib/shared/widgets/pill_button.dart:55`, `lib/core/theme/app_tokens.dart:26`
- **Six never-read convenience getters and three never-passed widget params** — NONE, minor  
  Verified one by one with `grep -rnw <name> lib test --include="*.dart"`, each returning only its own declaration. Getters: `IncidentSeverity.isAlarm` (models.dart:57), `Incident.isAlarm` (models.dart:756 — its only caller would have been the UI), `IncidentSeverity.isSensorOnly` (models.dart:60), `Verification.isDoubleChecked` (models.dart:89), `ZoneStatus.isAlert` (models.dart:118), `MusterRoll.missing` (models.dart:  
  Evidence: `lib/data/models/models.dart:57`, `lib/data/models/models.dart:60`, `lib/data/models/models.dart:89`
- **Unreachable test-alert hook wired from the phone to the backend** — NONE, minor  
  `ApiClient.testAlert` POSTs `/api/test-alert` and its own doc comment calls it 'a demo alert without a real flame' (api_client.dart:82-89). `ApiFireRepository.testAlert` wraps it (api_fire_repository.dart:216). `grep -rn "testAlert" lib test` returns only those two lines — no screen, no button, no test calls either. The backend endpoint exists (alert-service/app.py:517), so this is a dead client stub for a demo hook   
  Evidence: `lib/data/api/api_client.dart:82`, `lib/data/api/api_fire_repository.dart:216`, `fire_detection_and_classification_web_app/alert-service/app.py:517`
- **Seventy-four lines of invented incident history with fabricated AI notes** — NONE, minor  
  `MockData.incident` (mock_data.dart:108-130) and `MockData.history` (132-205) hold a made-up Fabric Store fire at 92% confidence and five invented past events — Boiler Room, Cutting Floor ('dust'), Dyeing, Finishing ('steam') — with hand-written scene notes presented as AI output ('Flames persist at the roll racks; thick smoke now filling the upper half of the store', 151-153). These reach the UI only through MockFir  
  Evidence: `lib/data/mock/mock_data.dart:108`, `lib/data/mock/mock_data.dart:132`, `lib/data/mock/mock_data.dart:151`
- **DetectionEvent.detected duplicates the verification field it predates** — RO1.3, minor  
  DetectionEvent carries `final bool detected; // VLM confirmation (stage 2)` (models.dart:266, parsed at :275). That is the old single-bit view of Algorithm 3, superseded by the four-value Verification enum on Incident (:727, parsed at :770). The bool is still constructed everywhere - api_fire_repository.dart:256 and :303, mock_data.dart:119, and four test files - but I found no widget that reads it: grep for '.detect  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:266`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:275`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:727`
- **originReanchored is parsed and never used** — RO2.2, minor  
  `EvacRoute.originReanchored` is declared, defaulted and parsed from JSON, but `grep -rn "originReanchored|reanchor" lib/ test/` finds only those three lines in models.dart - no widget, screen or painter reads it. It is also absent from `fcm.py _route_fields`, so an offline route would not carry it anyway. The information the occupant needs is already inside `instruction` ("Leave the kitchen immediately, then ...").  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:443,463,495`, `fire_detection_and_classification_web_app/alert-service/fcm.py:115-137`, `fire_detection_and_classification_web_app/alert-service/routing.py:92`
- **originReanchored parsed from the wire and then thrown away** — RO2.2, minor  
  `EvacRoute.originReanchored` is declared (models.dart:443, 463) and parsed on every route (models.dart:495), but `grep -rnw originReanchored lib test` shows no reader anywhere in the UI. The backend does compute it — routing.py:46 declares the field, routing.py:92 serialises it, routing.py:241 and 272 set it, and serializers.py:174 puts it on the wire — and it means the occupant's own position was inside the hazard s  
  Evidence: `lib/data/models/models.dart:443`, `lib/data/models/models.dart:463`, `lib/data/models/models.dart:495`
- **Dead demo hook in the app: testAlert is defined but never called** — RO2.3, minor  
  ApiClient.testAlert and ApiFireRepository.testAlert wrap POST /api/test-alert, but grep for 'testAlert' across lib/ and test/ finds only those two definitions - no screen, no button, no test calls either. The backend /api/test-alert is genuinely used to run demos and RO3.4 sessions and should stay; the Flutter-side wrappers are dead weight.  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/api/api_client.dart:83`, `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:216`, `fire_detection_and_classification_web_app/alert-service/app.py:517`
- **Occupant app carries safety-officer screens that RO2.3 does not ask for** — RO2.3, minor  
  Ch.3 line 253 splits the roles: the WEB dashboard gives the officer the live view, sensor panel, head-count and state; the Flutter app "shows the alert, the evacuation route, the fuel class and the fire fighting guidance, and lets each occupant mark that they are out". The app additionally ships a site-status dashboard (174 lines) with zone cards, health row and status hero, and a per-zone detail screen (125 lines) -  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/features/dashboard/dashboard_screen.dart:1`, `fire_notification_and_evacuation_mobile_app/lib/features/zone_detail/zone_detail_screen.dart:1`, `fire_notification_and_evacuation_mobile_app/lib/core/router/app_router.dart:46`
- **testAlert client method is never called from the app** — RO2.3, minor  
  ApiClient.testAlert POSTs /api/test-alert (api_client.dart:83-89) and ApiFireRepository.testAlert forwards it (api_fire_repository.dart:216). Grepping lib/ and test/ for 'testAlert|test-alert' returns only those two definitions — no UI or test calls either. The backend hook itself (app.py:517-518) is used from the web dashboard, so only the Dart side is dead.  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/api/api_client.dart:83`, `fire_notification_and_evacuation_mobile_app/lib/data/api/api_fire_repository.dart:216`
- **About 670 lines of occupant dashboard, history and zone-detail beyond the objective** — RO2.3, minor  
  Thesis s3.2.4 (chapter_3.txt:253) describes the occupant app as showing "the alert, the evacuation route, the fuel class and the fire fighting guidance, and lets each occupant mark that they are out of the building" — five things, all delivered by the incident, warning, resolved and report screens. The multi-zone dashboard (dashboard_screen.dart, 174 lines), history list (history_screen.dart 43 + event_card.dart 105)  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/features/dashboard/dashboard_screen.dart:1`, `fire_notification_and_evacuation_mobile_app/lib/features/history/history_screen.dart:1`, `fire_notification_and_evacuation_mobile_app/lib/features/zone_detail/zone_detail_screen.dart:1`
- **groundingAccuracy is parsed on the phone but never shown** — RO3.1, minor  
  SituationReport carries a groundingAccuracy field, declared at models.dart:679 and parsed at l.694-696. grep for 'groundingAccuracy' across the whole of lib/ returns only those four lines in models.dart - no widget reads it. situation_report_card.dart shows per-claim marks and the withheld count but no accuracy figure. It is dead weight on the model unless you decide the responder should see the figure.  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:679`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:694`, `fire_notification_and_evacuation_mobile_app/lib/features/incident/widgets/situation_report_card.dart:72`
- **Phone parses firstAction, useAgents and avoidAgents but renders none of them** — RO3.2, minor  
  FireClassification declares firstAction, useAgents and avoidAgents (models.dart:350-352, 362-364) and fills them from the response sub-object (lines 391-393) via the _agents helper (lines 375-379). grep -rn over lib/ and test/ shows the only reader of any of them is the test at severity_test.dart:129-130. The one field of the four that a widget actually uses is fireClass (guidance_card.dart:98). So three parsed field  
  Evidence: `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:350`, `fire_notification_and_evacuation_mobile_app/lib/data/models/models.dart:375`, `fire_notification_and_evacuation_mobile_app/lib/features/incident/widgets/guidance_card.dart:98`
- **Unreachable switch arms label home as "Home demo" in a warning nobody sees** — NONE, info  
  `_NoPlanForSite` renders only when `FloorPlan.forSiteKey(claimedSite)` is null (incident_screen.dart:98, 176). `forSiteKey` returns non-null for exactly the keys in `FloorPlan.byKey`, which is {'home', 'industrial'} (floor_plan_data.dart:183-186, 197-198). So the `'home' => 'Home demo'` and `'industrial' => 'Industrial'` arms at incident_screen.dart:440-441 can never execute — only the `''` and `_` arms can. The 'Hom  
  Evidence: `lib/features/incident/incident_screen.dart:98`, `lib/features/incident/incident_screen.dart:176`, `lib/features/incident/incident_screen.dart:440`
- **Home zone table copied from the backend site file** — NONE, info  
  `MockData.zones` (mock_data.dart:27-100) hard-codes all eight home zones with their ids, names, floors, detector ids and glyphs. I loaded alert-service/sites/home.json and the eight tuples match exactly: kitchen/Kitchen/Detector 01/Ground floor through bedroom-southeast/Bedroom (SE)/Detector 08/Ground floor. The same table is owned by the backend (alert-service/zones_seed.py). The file's own doc comment calls it a 'M  
  Evidence: `lib/data/mock/mock_data.dart:5`, `lib/data/mock/mock_data.dart:27`, `lib/data/api/api_fire_repository.dart:18`
- **A 1.7 MB README illustration and template scaffolding still tracked** — NONE, info  
  `docs/mobile_app_cover_image.png` is 1,719,539 bytes — larger than every Dart file in the repo combined — and `grep -rn mobile_app_cover_image` finds exactly one reference, README.md:3. It is not under `flutter.assets` in pubspec.yaml (there is no assets section at all), so it never ships in the APK. Alongside it: pubspec.yaml:2 still reads `description: "A new Flutter project."`; analysis_options.yaml has 28 lines o  
  Evidence: `docs/mobile_app_cover_image.png`, `README.md:3`, `pubspec.yaml:2`

### ESP32 sensor node (11)

- **Simulator fans out to 8 zones and N nodes; scope is one node** — RO1.1 (scope Ch.3 s3.2.1), major  
  Ch.3 s3.2.1 fixes the prototype at "One monitored indoor zone, observed by one fixed camera at a raised position and one fixed multi sensor node" (chapter_3.txt:132) and puts "Multi zone coordination" outside the scope (chapter_3.txt:143). tools/mock_sender.py carries a hard-coded 8-entry ZONES list (lines 44-46) and a --nodes argument (line 124), and line 133 round-robins simulated nodes across those zones: nodes =   
  Evidence: `esp_32_sensor_network_code/tools/mock_sender.py:44`, `esp_32_sensor_network_code/tools/mock_sender.py:124`, `esp_32_sensor_network_code/tools/mock_sender.py:133`
- **1.6 MB decorative banner is 88 percent of the repo and shows an outdoor fire** — NONE, minor  
  docs/esp_32_sensor_cover_image.png is 1,633,534 bytes of the repo's 1,856,136 tracked bytes (88 percent). I grepped "esp_32_sensor_cover_image" across all four repos: the only hit is README.md:3, the title banner. I also grepped "docs/" across this repo: the only hit is that same line, so nothing else in the repo reads the docs/ directory. I opened the image: it is an AI-generated marketing banner showing an ESP32 bo  
  Evidence: `esp_32_sensor_network_code/docs/esp_32_sensor_cover_image.png`, `esp_32_sensor_network_code/README.md:3`, `chapter_3.txt:144`
- **tools/mock_sender.py is a second full reimplementation of the same mock in Python** — RO1.1, minor  
  178 lines that duplicate the sketch's mock wholesale: the same three scenarios with identical numbers (mock_sender.py:35-39 vs ino:63-68), the same drift() with the same 0.18 pull (mock_sender.py:49-57 vs ino:91-98), the same raw_of/mockRaw derivation (mock_sender.py:60-62 vs ino:117-121), the same flame flicker probabilities 0.08/0.997 (mock_sender.py:87 vs ino:111). No objective needs a host-side simulator; its sta  
  Evidence: `esp_32_sensor_network_code/tools/mock_sender.py:35`, `esp_32_sensor_network_code/tools/mock_sender.py:49`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:63`
- **Serial scenario console and auto-cycle engine are demo scaffolding, not part of the objective** — RO1.1, minor  
  About 60 lines of the sketch exist only because the node is a mock: the Scenario enum and Targets table (ino:55-69), setScenario/handleSerial with the n/s/f/a/? keys (ino:234-262), the autoScenario timer in loop() (ino:296-298), and the AUTO_SCENARIO / SCENARIO_HOLD_MS settings (config.example.h:67-68) plus README Table 2 (lines 76-84). RO1.1 asks for a node that measures and publishes at a fixed interval; nothing in  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:55`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:234`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:296`
- **PIN_FLAME_AO exists only to seed the random generator** — RO1.1, minor  
  PIN_FLAME_AO is defined at config.example.h:88 and config.h:80 and documented as a wiring requirement in README Table 6 (README.md:233). I grepped PIN_FLAME_AO across the whole repo: it has exactly one compiled use, sensor_node_mock.ino:286, randomSeed(analogRead(PIN_FLAME_AO) ^ micros()). readRealSensors() (sensor_node_mock.ino:131-144) never reads it, so no flame value ever comes from that pin. config.example.h:88   
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/config.example.h:88`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:286`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:131`
- **tools/mock_sender.py is the same mock written a second time in Python** — RO1.1, minor  
  178 lines that duplicate the sketch's mock exactly: the same three scenario target sets (mock_sender.py:35-39 vs ino:63-68), the same mean-reverting drift with the same 0.18 pull (mock_sender.py:49-57 vs ino:91-98), the same raw-from-ppm derivation (mock_sender.py:60-62 vs ino:117-121), the same 400/3900 flame values and the same 0.08/0.997 flicker probabilities (mock_sender.py:87, 103 vs ino:111, 195), the same 3 s   
  Evidence: `esp_32_sensor_network_code/tools/mock_sender.py:35`, `esp_32_sensor_network_code/tools/mock_sender.py:49`, `esp_32_sensor_network_code/tools/mock_sender.py:133`
- **The simulator fans out to eight zones, beyond the one-zone one-node scope** — RO1.1 (scope), minor  
  Ch3 s3.2.1 scopes the prototype to one monitored indoor zone with one fixed multi-sensor node. mock_sender.py --nodes N spreads simulated nodes round-robin over all eight home zones (mock_sender.py:44-46, 133), and the service allows up to SENSOR_MAX_NODES 32 (main.py:50). The 32-node cap is a defensible memory bound on an open LAN port and Algorithm 1 genuinely aggregates 'over the nodes of the zone', so the server   
  Evidence: `esp_32_sensor_network_code/tools/mock_sender.py:44`, `esp_32_sensor_network_code/tools/mock_sender.py:133`, `fire_detection_and_classification_web_app/esp32-sensor-service/main.py:50`
- **The mock engine is implemented twice, in C++ and again in Python** — RO1.1 / RO3.3, minor  
  tools/mock_sender.py is a second full implementation of the generator already inside the sketch, with the constants copied by hand. Scenario targets: sensor_node_mock.ino:65-67 (120/4/28/62, 550/45/43/44, 950/140/68/27) against mock_sender.py:36-38, identical. Random walk: .ino:91-98 against mock_sender.py:49-57, same 0.18 pull and same noise amplitudes 18.0 / 3.0 / 0.6 / 1.2. Raw derivation: mockRaw() at .ino:117-12  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:63`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:91`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:117`
- **Scenario auto-cycle and serial console are a demo path no objective requires** — NONE, info  
  The sketch carries an operator console no objective asks for: AUTO_SCENARIO and SCENARIO_HOLD_MS at config.example.h:67-68, the auto-advance at sensor_node_mock.ino:296-298, setScenario() and handleSerial() at lines 234-262 (29 lines), and the okCount/failCount counters at line 83 printed only by the '?' key at lines 253-257. README Table 2 (README.md:76-84) documents the five keys. None of RO1.1 to RO3.4 mentions op  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:234`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:296`, `esp_32_sensor_network_code/sensor_node_mock/config.example.h:67`
- **PIN_DHT22 is a define that only a comment references** — RO1.1, info  
  PIN_DHT22 is defined at config.example.h:89 and config.h:81 and documented as a wiring requirement at README.md:234. I grepped PIN_DHT22 across sensor_node_mock.ino: one hit, line 141, and that line is a comment ("// #include <DHT.h>; DHT dht(PIN_DHT22, DHT22); dht.begin() in setup();"). No compiled statement uses it, which is the same fact as the DHT22 real-mode gap seen from the configuration side: in MOCK_MODE 0 t  
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/config.example.h:89`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:141`, `esp_32_sensor_network_code/README.md:234`
- **Serial scenario console and auto-cycling demo engine in the firmware** — RO1.1, info  
  RO1.1 asks for measurement and publication at a fixed interval. The sketch additionally carries a scenario state machine with three named target sets (ino:55-69), a mean-reverting generator (ino:86-121), a five-key serial command interface with its own status report (ino:234-262, documented at ino:29-31 and README Table 2), and AUTO_SCENARIO cycling every 30 s (config.h:55-60, ino:296-298). That is roughly 90 of the   
  Evidence: `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:55`, `esp_32_sensor_network_code/sensor_node_mock/sensor_node_mock.ino:234`, `esp_32_sensor_network_code/sensor_node_mock/config.h:55`

### ESP32-CAM (8)

- **1.86 MB decorative cover banner is 91% of the repo and shows a forest fire** — NONE, minor  
  docs/esp_32_cam_cover_image.png is 1,859,338 bytes of the repo's 2,031,296 tracked bytes (91.5%); all source and documentation text together is 23,993 bytes. It is an AI-generated marketing banner embedded at README.md:3. Beyond carrying no objective, its content works against the thesis: it shows a forest at dusk with a fire-lookout tower, while chapter_3.txt:144 puts "Outdoor fires, vehicle fires" out of scope and   
  Evidence: `esp_32_cam_code/README.md:3`, `esp_32_cam_code/docs/esp_32_cam_cover_image.png`, `/private/tmp/claude-501/-Users-chanakabandara-Desktop-Fire-Research-All-Codes/3a73feb6-87a0-4e57-b4a3-10525693afb1/scratchpad/thesis/chapter_3.txt:144`
- **hardwareJpeg is write-only: declared once, assigned three times, never read** — NONE, minor  
  grep -n "hardwareJpeg" over the only source file returns exactly four lines: the declaration at .ino:50 and the three assignments at .ino:273, :279 and :285. No conditional, no Serial.printf argument and no handler ever reads it. The stream and still handlers decide the JPEG path from fb->format instead (.ino:117, .ino:149), so the flag is genuinely redundant rather than a spare copy of live state.  
  Evidence: `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:50`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:273`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:279`
- **Built-in preview web page: 42 lines no part of the system ever requests** — NONE, minor  
  PAGE_HTML (.ino:64-98, 35 lines of HTML/CSS/JS), index_handler (.ino:103-106) and the route registration (.ino:187-189, :200) serve GET / . I searched every consumer in the other three repos and the support folders with grep -rn for '/stream', '/still' and 'ESP32_CAM': the only requests made to the board are f"{origin}/stream" at esp32-cam-service/main.py:210, f"{origin}/still" at main.py:292 and main.py:335. Even th  
  Evidence: `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:64`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:103`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:187`
- **About 50 lines support camera sensors the project never uses** — NONE, minor  
  The sketch carries a full software-JPEG path for non-OV2640 sensors. The thesis names one sensor - chapter_3.txt:241 says "ESP32-CAM module for the video stream" - and this repo's own diagram.png labels the board "ESP32-CAM (OV2640)". The fallback path is: the img_converters.h include (.ino:15), the RGB565 else-branch in still_handler (.ino:120-128), the software-JPEG branch plus mustFree bookkeeping in stream_handle  
  Evidence: `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:15`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:120`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:152`
- **Config template duplicated outside the repo, second copy holds the live password** — NONE, minor  
  firewatch-private-files/config-esp32-cam.h is a byte-for-byte copy of esp_32_cam_code/config.example.h apart from three lines. diff between them reports only: line 2 ("REAL configuration (do not commit)" vs "configuration TEMPLATE") and lines 17-18 (the real SSID and password vs the YOUR_2GHZ_SSID / YOUR_WIFI_PASSWORD placeholders). Every one of the 28 comment lines, including the stale instruction "Copy this to conf  
  Evidence: `esp_32_cam_code/config.example.h:2`, `esp_32_cam_code/config.example.h:9`, `esp_32_cam_code/config.example.h:17`
- **Server sized for 8 URI handlers when only 3 exist** — NONE, info  
  startCameraServer sets config.max_uri_handlers = 8 at .ino:184, then registers exactly three handlers at .ino:200-202. The five spare slots reserve RAM on a board the README itself describes as memory-constrained (README.md:13, "a board with very little memory"). config.ctrl_port = 32768 at .ino:182 is also the ESP-IDF default, so that line changes nothing.  
  Evidence: `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:182`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:184`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:200`
- **.gitignore ignores build output the Arduino IDE never writes here** — NONE, info  
  .gitignore:6-9 ignores build/, *.bin, *.elf and *.hex. The Arduino IDE compiles into a system temp directory, not the sketch folder, so these four rules never match anything in this project. git status --porcelain --ignored on the repo confirms it: the only ignored entry reported is '!! config.h', from .gitignore:3. The rules are template scaffolding carried in from a generic embedded .gitignore.  
  Evidence: `esp_32_cam_code/.gitignore:3`, `esp_32_cam_code/.gitignore:6`
- **The board serves its own HTML viewer page that no objective needs** — RO3.3, info  
  The firmware embeds a 40-line `PAGE_HTML` viewer with a live img, a Reload stream button and a Take photo button, served from `/` by `index_handler` and registered as `index_uri` (esp32cam_stream_v2_final_working_code_via_wifi.ino:63-97, 103-106, 187-189). The thesis puts the camera stream through the backend to the dashboard (chapter_3.txt:244), and esp32-cam-service only ever fetches `/stream` and `/still` from the  
  Evidence: `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:63`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:104`, `esp_32_cam_code/esp32cam_stream_v2_final_working_code_via_wifi.ino:187`

### Across repos (2)

- **A third 'muster roll' count duplicates the head-count and is invisible in the app** — RO2.3, major  
  The thesis needs two counts. The muster apparatus is a third, derived one (present = peak - current, total = peak, falling back to 42/45). On the phone it is parsed into every Incident and hard-coded into the two fallback constructors, but NO widget renders it - grep for '.muster' across lib/ hits only comments and the unrelated musterAt map coordinate. It survives only because reports.html prints it (see the blockin  
  Evidence: `fire_detection_and_classification_web_app/alert-service/serializers.py:76`, `fire_detection_and_classification_web_app/alert-service/db.py:125`, `fire_detection_and_classification_web_app/alert-service/db.py:654`
- **A third, synthetic muster count (42 of 45) that no objective asks for** — RO2.3, major  
  The thesis defines exactly two counts: the camera head-count and the check-out count (chapter_3.txt:354, 733). The code carries a third. DEFAULT_MUSTER_PRESENT=42 / DEFAULT_MUSTER_TOTAL=45 are written into every new incident (db.py:23-24, 351) into columns muster_present/muster_total (db.py:125-126); muster_json serves them verbatim with source 'estimated' when no occupancy was ever recorded (serializers.py:99-105) a  
  Evidence: `fire_detection_and_classification_web_app/alert-service/db.py:23`, `fire_detection_and_classification_web_app/alert-service/serializers.py:99`, `fire_detection_and_classification_web_app/frontend/static/reports.html:332`

## Confirmed correct

These parts match the thesis and should be kept. They are grouped by repository and objective.


### Web app (152)


**ALG1**

- Per-channel grading matches the pseudocode comparisons exactly
- All three numeric threshold pairs match Table 3.8 in every copy
- Node level is the worst channel, never an average
- 15 s stale limit turns a node's level into unknown, not normal
- Zone level is the worst node and is never averaged
- Higher level accepted only after 3 consecutive 2 s polls

**ALG2**

- Fuel verdict upgrades the same incident in place, with no duplicate incident

**ARCH**

- Ten compose services, all reachable, none dangling
- fire-classification-service really is the only place the two joblibs load
- One source per service holds for Gemini and for the three graded thresholds
- nginx and esp32-cam-service are both justified, not redundant

**ARCH-L3**

- fire-classification-service is genuinely the only place both models load
- Both models are used, not merely loaded: sensor probabilities feed the fusion model

**Alg.1 (dashboard half)**

- 3-consecutive-poll escalation and 2 s polling are both implemented as written

**Alg.2 (GAS WARNING cooldown)**

- Dashboard warning cooldown matches the server's incident cooldown exactly

**NONE**

- None of the five out-of-scope features from Ch.3 s3.2.1 appear in the code

**RO1.1**

- Transport is HTTP POST JSON, matching Chapter 3's architecture table
- The Ch1-vs-Ch3 MQTT contradiction is already found and a corrected wording drafted
- Every grading threshold matches Table 3.8 exactly, in four places
- Clockless node, server timestamp, 15 s stale, unknown never normal

**RO1.1 / Alg.1**

- Server timestamps the message and MQ-2, MQ-7, temperature thresholds match Table 3.8

**RO1.2**

- Trained model is present, wired in and served as its own service
- Model has exactly two classes and exposes them at runtime
- The 0.35 confidence gate exists, at the same value, in both consumers
- Hyperparameters are recoverable from the checkpoint, so partial reproducibility exists
- Detector behaves identically for the home and industrial profiles
- Trained fire/smoke detector ships in-repo, loads and serves boxes
- Exactly two detection classes, discoverable at runtime via /health
- The 0.35 confidence gate matches the thesis and is applied in three places
- The full training configuration is embedded in best.pt, so the model is not a black box

**RO1.3**

- The 'documented arbitration rule set' deliverable exists in README.md Table 1

**RO1.3 (0.35 box confidence)**

- The 0.35 fire-box threshold matches in the dashboard and the ablation constants

**RO1.3 (home and industry paths in the verification layer)**

- Home and industrial verification modes share one prompt body and differ in one clause

**RO1.3 / Alg.2**

- Open incident is refreshed quietly, with no second incident
- The 30 s clear constant matches the thesis exactly
- FIRE CONFIRMED plus gas above normal upgrades the same incident with a fuel class
- GAS WARNING is a quiet written warning on a separate channel with the zone left clear

**RO1.3 / Alg.2 Table 3.9**

- All twelve cells of the Table 3.9 arbitration matrix match decide()

**RO1.3 / Alg.3**

- Algorithm 2 arbitration is implemented in frontend/static/js/escalation.js decide()
- VLM is never called on an empty frame and only one call is ever in flight
- The VLM call does not block the detection loop
- Timeout and parse error both resolve to 'unavailable', not to a rejection

**RO1.3 / Alg.3 Table 3.10**

- Fixed prompt names lamp, torch, LED, camera flash and phone screen as not fire
- Strict JSON with detected, type and description, and no free text accepted
- The VLM cannot create a fire event on its own

**RO1.3 / Algorithm 2 (30 s clear)**

- CLEAR_AFTER_SECONDS is 30, matching the thesis exactly

**RO1.3 / Algorithm 2 (GAS WARNING branch)**

- Written warning on a separate channel, with cooldown, zone stays clear, no alarm

**RO1.3 / Algorithm 2 (record 'verification unavailable')**

- The verification verdict is stored and travels end to end to the phone

**RO1.3 / Algorithm 2 (refresh I quietly, no second incident)**

- An open incident is refreshed silently instead of duplicated

**RO1.3 / Algorithm 2 (tier 3 upgrade in place)**

- Classifier is called only during an open fire with gas above normal, and upgrades the same incident

**RO1.3 / Algorithm 2 + Table 3.9**

- decide() reproduces all twelve Table 3.9 cells; the file is escalation.js

**RO1.3 / Algorithm 3**

- Fixed verification prompt names lamp, torch, camera flash and phone screen as not fire

**RO1.3 / Algorithm 3 (never verify an empty frame)**

- VLM is only called inside the has-a-box branch

**RO1.3 / Algorithm 3 (one call at a time, non-blocking)**

- Single in-flight VLM call, fire-and-forget, with a staleness guard

**RO1.3 / Algorithm 3 (parse error and timeout -> unavailable)**

- Parse failure and timeout both become 'unavailable', not a rejection

**RO1.3 / Algorithm 3 + Table 3.10**

- Strict JSON contract with exactly detected, type, description

**RO1.3 / Table 3.10**

- The VLM cannot create an incident on its own

**RO1.4**

- All four thesis configurations are implemented as executable arms
- Precision, recall, F1 and accuracy computed at window and event level
- Time to detection measured from ignition, median and p90
- Paired McNemar test against the full configuration is implemented
- An ablation result table exists in the UI and as an event-level CSV
- Service is fully wired into compose, nginx, the frontend route and the nav
- Detection threshold 0.35 is identical in the ablation and in the dashboard
- One shared debounce makes the four arms' latencies comparable
- Held-out evaluation dataset is vendored, counted and checksummed
- Each arm's printed rule and the limitations list are served from the executing constants
- All four thesis configurations implemented as paired ablation arms
- Precision, recall, F1 and false-alarm rate computed at two levels with confidence intervals
- Time to detection measured from ignition, with never-detected runs censored not dropped
- Ablation result table exists, is rendered and exports as one row per combination
- Ablation service fully wired into compose, nginx and the dashboard nav
- Held-out evaluation splits vendored in-repo and verifiable, with full provenance on every export
- Ablation thresholds match the deployed system and the thesis, number for number
- Synthetic provenance is flagged everywhere and the limitations are honest

**RO2.1**

- Dedicated human-detection YOLO service returns count plus boxes, no identity
- Head-count is genuinely outside the alarm decision
- No face recognition, re-identification or tracking anywhere in the four repos
- Smoothed head-count: 5-frame rolling median, threshold held server-side
- Unknown count is never read as an empty room, in every layer
- Count stored per incident as current + peak, exactly what section 3.5 allows
- Head-count is genuinely kept out of the alarm decision
- No face recognition, re-identification or tracking exists anywhere
- Only the count is persisted, as current and peak, per section 3.5.2
- Head-count reaches the alert service with unknown kept distinct from zero
- Camera head-count and occupant check-out are kept as two separate numbers
- Smoothed head-count implemented as a five-frame rolling median
- Dashboard and mobile app both show the head-count as the thesis describes
- The detector, not the VLM, is the authority on how many people are present

**RO2.2**

- The 5 s budget is measured per incident and counted, not just claimed
- Documented facility graph model exists, and geometry is deliberately not in the DB
- Five-second budget is measured end to end, not asserted
- Site files are validated at import and refuse to start on a broken graph
- Documented facility graph model deliverable exists

**RO2.2 / Alg.4**

- Site selection is a fail-fast env var, validated at import
- Both site files are real weighted graphs; the industrial one is not degenerate
- Genuine Dijkstra with a binary heap, not a hardcoded path list
- Real weighted undirected graph, weights are physical length in metres
- Node kinds cover all four thesis categories on both sites
- Whole edges are blocked by point-to-segment distance, not just the fire node
- Nearest reachable exit, with blocked and unreachable exits separated
- Refuge instruction when no exit is reachable
- Post-hoc safety assertion on every returned route
- It is genuinely Dijkstra, not a hardcoded path list
- Facility really is a weighted undirected graph with the four node kinds
- Whole edges are blocked by perpendicular distance, not endpoint testing
- Nearest reachable exit, deterministically chosen, with blocked exits named

**RO2.2 / RO2.3**

- Route is generated inside the intake lock and rides the first push

**RO2.3**

- Check-out count kept separate from the camera head-count, one device counted once
- Check-out is stored in its own table, keyed by device, and never folded into occupancy
- Check-out endpoint and serializer return both counts side by side, unreconciled
- Check-out is stored in its own table, never in the head-count columns
- POST /api/incidents/{id}/checkout is idempotent per device and returns both counts
- An unknown head-count stays unknown instead of reading as an empty building
- Decision-to-delivery is instrumented on one clock, as Table 3.19 needs

**RO3.1**

- All five required report fields exist as separately graded claims
- Grounding is real: claims are compared to evidence values, not just concatenated
- Validation runs server-side and re-reads evidence off the incident row
- Evidence is captured from the same frame the description is written from
- Table 3.20's three categories and both Section 3.4.7 figures are computed
- Location claim is system-supplied from the zone model, not generated
- Report generation can never suppress the alarm, and costs one VLM call per alarm
- Dedicated test suite pins the grounding invariant
- VLM people claim is validated against the head-count before release
- Grounding is real evidence comparison, not string assembly
- Three verdict categories and both figures match Table 3.20 and s3.4.7 word for word
- Two evidence channels are read from the incident row, not trusted from the caller
- A dedicated VLM prompt asks for the five fields and is allowed to answer null
- Grounding invariants are unit tested, and the location claim is site-aware

**RO3.2**

- Extinguisher guidance is site-independent, as it should be
- Guidance is a fixed table served from one place, exactly as the thesis states
- Agents-to-use column matches Table 3.11 exactly for all three fuel classes
- Every prohibition and every first action carries a reason
- Class 'no fire' gives no guidance, enforced in two independent places
- Dashboard renders all five Table 3.11 columns for the live incident
- fire-classification-service loads both joblibs and is the only place that does
- Sensors-only model is a real sub-model and its own probabilities are exposed for the comparison
- Guidance is a fixed table with the three columns Table 3.11 requires
- All four fuel classes present, and no_fire correctly gives no guidance
- Liquid fuel row matches Table 3.11 on both agent lists
- Solid combustible agents-to-use list matches Table 3.11 exactly
- Gas fire row matches Table 3.11 on first action, agent and the explosion reason
- One table, three consumers, no duplicated copy
- Dataset counts in the manifest match the thesis numbers exactly

**RO3.3**

- Dashboard and phone both show presence and count as the architecture requires

**RO3.3 (detection results)**

- Detection results render correctly: two overlays, 0.35 confidence gate, per-model latency

**RO3.3 (generated reports)**

- Reports page delivers a real per-incident record with timeline, guidance and print

**RO3.3 (live sensor data)**

- Live sensor panel shows all four modules as five graded tiles

**RO3.3 (system status)**

- Four service dots plus a camera watchdog give a usable health strip

**RO3.3 / Table 3.7 Presentation row**

- Every element Table 3.7 names for the officer's screen is present

**RO3.4**

- RO3.4 is correctly tracked as a non-software deliverable with a six-item checklist
- A printable per-incident report page exists and is reachable

### Mobile app (28)


**ARCH**

- FCM really has two separate channels, matched on both sides
- Presentation layer complete on both halves, and both site profiles exist

**RO1.2**

- Mobile app correctly carries no detection code

**RO1.3**

- The app renders the arbitration outcome honestly and never overstates the evidence

**RO1.3 / Alg.2**

- 'verification unavailable' is stored and shown honestly all the way to the phone

**RO1.4**

- Flutter app carries no ablation code, which is correct

**RO2.2**

- Cross-repo mirror contract is tested over both sites equally
- Industrial's unmonitored room is handled honestly on both sides
- Cross-repo mirror contract is machine-checked, both sites present
- Static fallback route matches the thesis assumption consequence

**RO2.2 / RO2.3**

- App renders the server route, including the refuge case, and refuses to guess the building
- Phone consumes the backend polyline; no second routing implementation

**RO2.3**

- Foreground push picks its channel from the payload, fire alone takes over the screen
- The check-out action is wired from button to backend with the device token
- The route is actually drawn: path, hazard, blocked exits, muster point, refuge halo
- The gas warning screen is calm and carries no route, matching Table 3.6 tier 1a
- The post-incident report screen shows both counts and the difference, which is what s3.4.8 asks for
- Both site drawings, all twelve glyphs and every dependency earn their place
- Channel is chosen from the payload, and the two tiers really differ
- FCM receive covers foreground, background, terminated and cold-launch tap
- The check-out action exists, posts the device token, and the app shows both counts unreconciled
- Route is drawn only on its own site's plan, and the refuge case hides the check-out button

**RO2.3 / Alg.4**

- Phone picks the floor plan from the route data, never from a phone setting

**RO3.1**

- Phone renders each claim with its standing and admits what was withheld
- Phone renders graded claims, marks unsupported ones, admits withheld ones

**RO3.2**

- Phone renders the backend guidance sentence verbatim, never rebuilt locally

**RO3.4**

- All five Presentation B components render on one screen in the Flutter app
- Fake lock-screen mock-up was removed so participants see the real notification

### ESP32 sensor node (13)


**ALG1**

- Node sends no clock; the server stamps wall-clock time on arrival
- Grading thresholds exist in exactly one place; no second implementation

**ARCH**

- Communication layer matches Ch.3: HTTP POST JSON every 3 s, server timestamps

**RO1.1**

- No dead functions, no unused dependencies, no build scaffolding
- Fixed 3 s interval agrees with Chapter 3's stated cadence
- Pin map with the two real ESP32 hardware hazards documented

**RO1.4**

- Sensor node firmware carries no ablation code, which is correct

**RO2.1**

- Sensor-node repo contains nothing for RO2.1, which is correct

**RO2.2**

- Neither ESP32 repo contains routing code, which is right
- ESP32 repos correctly contribute nothing to RO2.2

**RO3.1**

- Sensor node firmware correctly contributes nothing to the report generator

**RO3.2**

- ESP32 repos correctly contain nothing for RO3.2
- Firmware repos correctly contribute nothing to RO3.2

### ESP32-CAM (9)


**ARCH**

- Camera stream is genuinely proxied through the backend end to end

**NONE**

- No out-of-scope behaviour: nothing here can violate the s3.2.1 exclusions

**RO1.2**

- ESP32-CAM firmware correctly streams only, with no on-device detection
- Both machine-facing routes are genuinely consumed; nothing is speculative plumbing

**RO1.3**

- ESP32 firmware correctly contributes nothing to RO1.3

**RO1.4**

- ESP32-CAM firmware carries no ablation code, which is correct

**RO2.1**

- Camera firmware is only a frame source, VGA by default, no on-board person logic
- ESP32 firmware correctly contains no occupant logic at all

**RO3.1**

- Firmware repos contain no RO3.1 code, correctly

### Across repos (19)


**RO1.1**

- All four required channels exist end to end as one synchronised message
- Fixed 3 s interval and 15 s stale limit match Chapter 3 exactly
- The mock flag is declared honestly all the way to the dashboard
- Neither the camera firmware nor the mobile app carries any sensor-node code
- All four required modules are present as one synchronised sweep
- Sequence number is carried end to end, board to dashboard
- Mock data is labelled as mock all the way to the screen
- The other two repos correctly carry no RO1.1 code

**RO1.1 (home/industry)**

- Both home and industrial zone sets are documented in the node config path and match the site files

**RO2.3**

- Two FCM notification channels exist end to end with matching ids
- The evacuation route travels with the alert, including a working offline path
- Delivery time is instrumented on one clock, including the terminated-app case
- Both sides have tests that pin the two-counts rule
- Neither ESP32 repo carries any RO2.3 code, which is right
- Two FCM channels exist with matching ids on both sides
- The evacuation route travels with the alert by two independent paths
- A gas warning carries no route and no check-out, matching Table 3.6 tier 1a
- Neither ESP32 repo touches RO2.3, which is correct

**RO3.4**

- Firmware repos contain nothing for RO3.4, which is correct
## Home and industry

Both site profiles stay. Both are real weighted graphs and neither is degenerate. The
problem is that they are not equally evidenced.

| | Home | Industrial |
|---|---|---|
| Zones | 8 | 7 |
| Exits | 2 | 4 |
| Graph edges | 16 | 20 |
| Route ground truth | 8 of 8 zones | 3 of 7 zones |
| Hazard radius | 2.0 m, justified in the file | 6.0 m, no written justification |

Four further points need a decision before the viva.

- The default site is home while the thesis scope is industrial.
- Switching to the industrial site still labels the interface "Home".
- The dashboard holds a fixed industrial zone name while the default site is home.
- The home graph is a tree, so the route search never has an alternative to choose. This
  makes the optimality measure always empty and the refusal measure always zero.

## Verification

Every blocking finding was opened and confirmed by hand before it was reported. The wider
set was produced by independent reviewers per objective and deduplicated. An adversarial
pass over the removal candidates was running when this document was written, so treat the
extra-code list as advice to check rather than a list to act on without looking.
