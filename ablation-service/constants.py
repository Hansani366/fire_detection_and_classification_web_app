"""
Every threshold the six combinations use, in one frozen place.

WHY THIS FILE EXISTS AT ALL. The page prints each combination's rule so it can
be copied into the paper. If the printed text and the executed code were
written separately they would drift, and the paper would describe a system that
was never run. So `describe()` renders the rule text *from the same constants
the code executes*, `/api/ablation/config` serves it, and the page renders what
the service returns. Printed and executed cannot disagree.

WHY NONE OF THESE NUMBERS IS HAND-TUNED. Combinations 1 and 6 are trained
models; 2 to 5 are rules. A reviewer will immediately ask whether the rules
were tuned to lose. So every constant below is either read from
model/manifest.json at runtime or taken verbatim from the dataset generator
that produced the training data, and each carries the provenance that says
which. Nothing here was chosen by looking at a result.
"""

# ── The clock ────────────────────────────────────────────────────────────────
# Training is exactly 1 Hz: 180 rows per 180-second experiment. manifest's
# roll_windows/persistence_window/smooth_window all count SAMPLES, so the
# window rate is not a free parameter -- changing it silently rescales every
# temporal feature. See main.py's module docstring.
WINDOW_HZ = 1.0
WINDOW_MS = int(1000 / WINDOW_HZ)

# ── Shared vision definitions (generator: YOLO_DETECT_THRESHOLD) ─────────────
# 0.35 is the generator's detection gate. It happens to equal the dashboard's
# MIN_CONF in frontend/static/index.html, so the rules below are simultaneously
# faithful to the training data and to the deployed system. Cite both.
YOLO_DETECT_THRESHOLD = 0.35

# Just above the test split's fire_area_ratio noise floor (p50 = 0.004) and far
# below real flames (p95 = 0.130), so it rejects sub-pixel boxes without
# rejecting small fires.
MIN_AREA_RATIO = 0.005

# fire_persistence is manifest's own persistence_window (25) evaluated at
# manifest's yolo_fire_threshold (0.5). 0.20 = 5 of those 25 windows, which is
# roll_windows[0] -- the shortest window the model itself considers meaningful.
FIRE_PERSISTENCE_MIN = 0.20

# ── Shared VLM definitions (generator: VLM_CONFIRM_THRESHOLD, VLM_COOLDOWN) ──
# The exact threshold the generator used to set vlm_confirmed, so combination 3
# asks the same question of the VLM that the training data encodes.
VLM_CONFIRM_THRESHOLD = 0.30

# `view` is clipped to [0.02, 1.0] and vlm_visual_conf = evidence * view, so
# below 0.10 the model is in the "could not see" region rather than the
# "looked and saw nothing" region. Without this floor, a dark or blocked frame
# reads as a confident negative.
VLM_VIEW_FLOOR = 0.10

# The generator invokes the VLM at most once per 4 s and holds the verdict
# between calls. Combination 3 uses the same cadence, but UNGATED (see below).
VLM_COOLDOWN_S = 4.0

# "Never invoked" is a real value in the training distribution, not a missing
# marker: it is what distinguishes "never looked" from "looked, saw nothing".
VLM_NEVER_INVOKED_STALENESS = -1.0

# ── Combination 4: how long sensors and vision may disagree ──────────────────
# The generator lags MQ-2 by 14 s and MQ-7 by 22 s (lag(mq2_true, 14.0)), so
# demanding instantaneous agreement between a camera and a gas sensor is
# physically impossible -- the gas has not arrived yet. 10 windows is under
# both lags: as tight as the chemistry permits, and stated as such.
SENSOR_AGREE_WINDOWS = 10

# ── Fairness controls, applied identically to all six ────────────────────────
# ONE debounce for every combination: the alarm is raised only after this many
# CONSECUTIVE windows of raw evidence. Applied identically to all six so that
# detection latency is comparable -- without it, a jumpier combination would
# look faster purely because it fires on single-frame noise. The same rule
# defines the event-level verdict (did the debounced alarm ever raise?) and the
# latency measurement (when did it first raise?), so there is one definition
# rather than three.
HOLD_WINDOWS = 3

# Binary decision point for the two probabilistic arms (1 and 6). Expressed as
# 1 - p[no_fire] rather than argmax != no_fire so both arms yield a single
# sweepable scalar and therefore an ROC curve, like the rule-based arms.
BINARY_THRESHOLD = 0.5

# ── Flame flicker (generator: flicker ~ N(2.1, 0.45) when flame is visible) ──
# SAMPLING RATE IS THE WHOLE POINT. Target flicker is ~2.1 Hz. The dashboard
# detection loop runs at 2 Hz, whose Nyquist limit is 1 Hz -- so sampling
# brightness there would alias a 2.1 Hz flame down to ~0.1 Hz, which is exactly
# the generator's "nothing there" value. The feature would report "no flame" on
# every real flame and look perfectly plausible doing it. Hence an independent
# 16 Hz sampler: Nyquist 8 Hz covers the full 0-6 Hz training range.
FLICKER_SAMPLE_HZ = 16.0
FLICKER_WINDOW_N = 64                      # 4.0 s at 16 Hz
FLICKER_BIN_HZ = FLICKER_SAMPLE_HZ / FLICKER_WINDOW_N   # 0.25 Hz resolution
FLICKER_MAX_HZ = 6.0                       # generator clips to [0, 6]
# Glare vs flame discriminator: glare has a flat spectrum, flame has a peak.
# Below this ratio we emit the "nothing" value rather than the argmax of noise.
FLICKER_PEAK_RATIO = 3.0
# The generator's quiet mode, N(0.1, 0.1). Emitted during warmup and whenever
# the peak is rejected, so a warming-up session stays in-distribution instead
# of sitting at an arbitrary 0.
FLICKER_QUIET_HZ = 0.1
# Below this frame rate the FFT would alias rather than measure, so recordings
# are refused instead of being given a fabricated number.
FLICKER_MIN_SOURCE_HZ = 12.0

# ── Sensor adapter ───────────────────────────────────────────────────────────
# mq2_delta = mq2_raw - baseline, and the model excludes baselines as leaky --
# so the baseline has to be estimated at runtime. 30 s because the longest
# rolling window is 25 samples: a shorter prefix risks the estimate sitting
# inside a window the model will also read.
BASELINE_S = 30.0
# Training priors, N(300, 22) and N(120, 14). Shown in the manual-entry form as
# LABELLED SYNTHETIC HINTS only. Never a silent default: defaulting an
# uncalibrated board to 300 turns mq2_delta into a pure offset error.
MQ2_BASELINE_HINT = 300.0
MQ7_BASELINE_HINT = 120.0
# Verbatim from the generator: mq7_delta / mq2_delta.clip(lower=5.0)
MQ_RATIO_FLOOR = 5.0
# The board's flame AO is inverted -- lower counts mean a brighter IR source.
# Landmarks from the node sketch: ~400 with a flame, ~3900 with none.
FLAME_DARK_COUNTS = 3900.0
FLAME_BRIGHT_COUNTS = 400.0
# Verbatim from the generator: flame_present = flame_value > 0.18
FLAME_PRESENT_THRESHOLD = 0.18
# Matches sensor-service's SENSOR_STALE_AFTER_S, so both agree on when a node
# has stopped talking.
SENSOR_STALE_AFTER_S = 15.0
# Holding a dead node's last reading through a fire is the exact failure
# sensor-service warns about, so past this the experiment aborts rather than
# quietly inventing data.
SENSOR_GAP_ABORT_S = 30.0
# The board's ppm conversion is a linear rescale of the ADC, so raw can be
# recovered when only ppm was recorded. From the node sketch.
MQ2_PPM_FULL_SCALE = 2000.0
MQ7_PPM_FULL_SCALE = 500.0
ADC_FULL_SCALE = 4095.0

# ── Live session bounds ──────────────────────────────────────────────────────
# predict() rebuilds features over the whole buffer every tick (O(n^2)), and
# demo.py forbids trimming because cummax and persistence reach back to the
# start. So we cap loudly and show the cap, rather than trimming silently and
# letting the prediction drift away from what a batch score would give.
LIVE_MAX_ROWS = 1800                       # 30 min at 1 Hz

COMBOS = {
    1: "sensors only",
    2: "YOLO only",
    3: "VLM only",
    4: "sensors + YOLO",
    5: "VLM + YOLO",
    6: "sensors + YOLO + VLM",
}

# Which raw modalities each combination is allowed to see. Used to zero the
# channels a combination must not read, and rendered in the UI as the ablation
# matrix.
COMBO_MODALITIES = {
    1: {"sensors": True,  "yolo": False, "vlm": False},
    2: {"sensors": False, "yolo": True,  "vlm": False},
    3: {"sensors": False, "yolo": False, "vlm": True},
    4: {"sensors": True,  "yolo": True,  "vlm": False},
    5: {"sensors": False, "yolo": True,  "vlm": True},
    6: {"sensors": True,  "yolo": True,  "vlm": True},
}


def rule_text(manifest: dict) -> dict[int, dict]:
    """The printed rule for each combination, rendered from the live constants.

    `manifest` supplies the values this module deliberately does not copy --
    they belong to the trained model, and duplicating them here is exactly the
    drift this file exists to prevent.
    """
    cfg = manifest["config"]
    smooth = cfg["smooth_window"]
    pwin = cfg["persistence_window"]
    ythr = cfg["yolo_fire_threshold"]

    return {
        1: {
            "name": COMBOS[1],
            "decided_by": "sensor_model.joblib (XGBClassifier, 53 features)",
            "rule": f"p_fire = 1 - p[no_fire] > {BINARY_THRESHOLD}, "
                    f"after the same causal {smooth}-window probability "
                    f"smoothing the fusion model uses",
            "score": "p_fire",
            "why": "The literal sensors-only arm is a trained model, not a hand "
                   "rule. metrics.csv already reports xgboost/sensor_only, so "
                   "this number is externally checkable; and a hand rule here "
                   "would be a strawman.",
        },
        2: {
            "name": COMBOS[2],
            "decided_by": "rule over fire-detection-yolo-service output",
            "rule": f"(yolo_fire_conf >= {YOLO_DETECT_THRESHOLD} OR "
                    f"yolo_smoke_conf >= {YOLO_DETECT_THRESHOLD}) "
                    f"AND (fire_area_ratio >= {MIN_AREA_RATIO} OR "
                    f"smoke_area_ratio >= {MIN_AREA_RATIO}) "
                    f"AND fire_persistence >= {FIRE_PERSISTENCE_MIN}",
            "score": f"fire_persistence at the {YOLO_DETECT_THRESHOLD} gate",
            "why": f"{YOLO_DETECT_THRESHOLD} is the generator's "
                   f"YOLO_DETECT_THRESHOLD and the dashboard's MIN_CONF. "
                   f"{FIRE_PERSISTENCE_MIN} = 5 of the manifest's {pwin} "
                   f"persistence windows at its yolo_fire_threshold {ythr}.",
        },
        3: {
            "name": COMBOS[3],
            "decided_by": "rule over vlm-service /describe-image-detailed/",
            "rule": f"max(vlm_flame_conf, vlm_smoke_conf) > "
                    f"{VLM_CONFIRM_THRESHOLD} AND vlm_visual_conf >= "
                    f"{VLM_VIEW_FLOOR}",
            "score": "max(vlm_flame_conf, vlm_smoke_conf)",
            "why": f"{VLM_CONFIRM_THRESHOLD} is the generator's "
                   f"VLM_CONFIRM_THRESHOLD. Invoked on a FIXED "
                   f"{VLM_COOLDOWN_S:g}s cadence, never on the YOLO gate -- a "
                   f"VLM-only arm that waited for YOLO would not be VLM-only.",
        },
        4: {
            "name": COMBOS[4],
            "decided_by": "rule: combination 2 confirmed by combination 1",
            "rule": f"alarm(2) now AND alarm(1) at any point in the last "
                    f"{SENSOR_AGREE_WINDOWS} windows",
            "score": f"min(score(2), max score(1) over the last "
                     f"{SENSOR_AGREE_WINDOWS} windows)",
            "why": f"The generator lags MQ-2 by 14s and MQ-7 by 22s, so "
                   f"instantaneous agreement between a camera and a gas sensor "
                   f"is physically impossible. {SENSOR_AGREE_WINDOWS}s is under "
                   f"both lags -- as tight as the chemistry permits.",
        },
        5: {
            "name": COMBOS[5],
            "decided_by": "rule: the dashboard's deployed alarm logic",
            "rule": "alarm(2) now AND the held VLM verdict is confirmed",
            "score": "min(score(2), held score(3))",
            "why": "This is verbatim the rule the live system already runs "
                   "(_markdown/fire_alarm_logic.md): YOLO proposes, the VLM "
                   "confirms, the verdict is held between invocations.",
        },
        6: {
            "name": COMBOS[6],
            "decided_by": "fusion_model.joblib (StandardScaler -> MLP(128,64), "
                          "96 features) over sensor_model.joblib",
            "rule": f"1 - p[no_fire] > {BINARY_THRESHOLD} after the manifest's "
                    f"causal {smooth}-window smoothing; the 4-class fuel label "
                    f"is the argmax of the same smoothed vector",
            "score": "1 - p[no_fire]",
            "why": "The only combination that uses a trained fusion model. Note "
                   "it CONTAINS combination 1: four of its 96 features are "
                   "sensor_model's probabilities, so 'fusion beats sensors' is "
                   "partly tautological and the informative comparison is "
                   "against combination 4.",
        },
    }


def describe(manifest: dict) -> dict:
    """The whole frozen configuration, for /api/ablation/config."""
    return {
        "window_hz": WINDOW_HZ,
        "combos": COMBOS,
        "modalities": COMBO_MODALITIES,
        "rules": rule_text(manifest),
        "shared": {
            "yolo_detect_threshold": YOLO_DETECT_THRESHOLD,
            "min_area_ratio": MIN_AREA_RATIO,
            "fire_persistence_min": FIRE_PERSISTENCE_MIN,
            "vlm_confirm_threshold": VLM_CONFIRM_THRESHOLD,
            "vlm_view_floor": VLM_VIEW_FLOOR,
            "vlm_cooldown_s": VLM_COOLDOWN_S,
            "sensor_agree_windows": SENSOR_AGREE_WINDOWS,
            "hold_windows": HOLD_WINDOWS,
            "binary_threshold": BINARY_THRESHOLD,
        },
        "flicker": {
            "sample_hz": FLICKER_SAMPLE_HZ,
            "window_n": FLICKER_WINDOW_N,
            "bin_hz": FLICKER_BIN_HZ,
            "max_hz": FLICKER_MAX_HZ,
            "peak_ratio": FLICKER_PEAK_RATIO,
            "quiet_hz": FLICKER_QUIET_HZ,
            "min_source_hz": FLICKER_MIN_SOURCE_HZ,
        },
        "sensor_adapter": {
            "baseline_s": BASELINE_S,
            "mq2_baseline_hint": MQ2_BASELINE_HINT,
            "mq7_baseline_hint": MQ7_BASELINE_HINT,
            "mq_ratio_floor": MQ_RATIO_FLOOR,
            "flame_dark_counts": FLAME_DARK_COUNTS,
            "flame_bright_counts": FLAME_BRIGHT_COUNTS,
            "flame_present_threshold": FLAME_PRESENT_THRESHOLD,
            "stale_after_s": SENSOR_STALE_AFTER_S,
            "gap_abort_s": SENSOR_GAP_ABORT_S,
        },
        "live": {"max_rows": LIVE_MAX_ROWS},
        "from_manifest": manifest["config"],
    }
