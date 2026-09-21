"""
Constants the feature adapters need, in one place.

THE 1 Hz CLOCK IS THE ONE THAT MATTERS. Both models were trained at exactly
1 Hz -- 180 rows per 180-second experiment -- and every temporal parameter in
manifest.json counts SAMPLES, not seconds: `roll_windows [5,15]`,
`persistence_window 25`, `smooth_window 5`. `vlm_staleness_s` is likewise a
sample count that only reads as seconds because the rate is 1 Hz. Feed this
service at any other rate and the 25-window persistence mean quietly covers a
different span of real time.

Everything else here is taken verbatim from the dataset generator that produced
the training data, so the values this service computes have the same meaning as
the ones the models learned from.
"""

# ── The clock ────────────────────────────────────────────────────────────────
WINDOW_HZ = 1.0

# ── Vision ───────────────────────────────────────────────────────────────────
# The generator's YOLO_DETECT_THRESHOLD, which also happens to equal the
# dashboard's MIN_CONF.
YOLO_DETECT_THRESHOLD = 0.35
FLICKER_MAX_HZ = 6.0
# The generator's quiet mode, N(0.1, 0.1). Used when flicker is not measured,
# so a row stays inside the training distribution rather than sitting at an
# arbitrary 0.
FLICKER_QUIET_HZ = 0.1

# ── VLM ──────────────────────────────────────────────────────────────────────
# The exact threshold the generator used to set vlm_confirmed.
VLM_CONFIRM_THRESHOLD = 0.30
# At most one call per this many seconds; the verdict is held in between.
VLM_COOLDOWN_S = 4.0
# "Never invoked" is a real value in the training distribution, not a missing
# marker -- it is the only thing separating "never looked" from "looked and saw
# nothing".
VLM_NEVER_INVOKED_STALENESS = -1.0

# ── Sensors ──────────────────────────────────────────────────────────────────
# The models read deltas above a clean-air baseline, and exclude the baseline
# itself as leaky -- so it has to be measured at runtime. 30 s because the
# longest rolling window is 25 samples.
BASELINE_S = 30.0
# Training priors, N(300, 22) and N(120, 14). Only ever a labelled hint.
MQ2_BASELINE_HINT = 300.0
MQ7_BASELINE_HINT = 120.0
# Verbatim generator: mq7_delta / mq2_delta.clip(lower=5.0)
MQ_RATIO_FLOOR = 5.0
# The flame module's analog pin is inverted: lower counts mean brighter.
FLAME_DARK_COUNTS = 3900.0
FLAME_BRIGHT_COUNTS = 400.0
# Verbatim generator: flame_present = flame_value > 0.18
FLAME_PRESENT_THRESHOLD = 0.18
# Matches esp32-sensor-service's SENSOR_STALE_AFTER_S.
SENSOR_STALE_AFTER_S = 15.0
# Past this, holding a dead node's last reading through a developing fire would
# be inventing data.
SENSOR_GAP_ABORT_S = 30.0
# The board's ppm output is a linear rescale of the ADC, so raw counts can be
# recovered when only ppm was recorded.
MQ2_PPM_FULL_SCALE = 2000.0
MQ7_PPM_FULL_SCALE = 500.0
ADC_FULL_SCALE = 4095.0

# ── Session bounds ───────────────────────────────────────────────────────────
# predict() rebuilds features over the whole buffer each tick, and the model's
# running maxima and persistence reach back to the first window, so the buffer
# must not be trimmed. Cap it loudly instead.
LIVE_MAX_ROWS = 1800                       # 30 min at 1 Hz
