"""
esp32-sensor-service readings -> the ten sensor channels the models expect.

THE MODEL WANTS DELTAS, AND EXCLUDES THE BASELINES THEY ARE MEASURED FROM. The
manifest lists `mq2_baseline` and `mq7_baseline` as leaky -- a per-experiment
constant that tells the model which experiment it is looking at. But
`mq2_delta = mq2_raw - mq2_base` needs that constant anyway, so it has to be
estimated at runtime, from the session itself, causally. That estimate is the
single largest source of error in this whole path, which is why it is a
documented choice with three modes rather than a hidden default.

EVERYTHING IS RESAMPLED ONTO A 1 Hz GRID. The models were trained at exactly
1 Hz and every temporal constant counts samples, not seconds. Nodes post every
3 s, so the grid is held (zero-order hold), never interpolated: interpolation
is non-causal, and it would produce fractional temperature_rate values that the
integer-quantised training channel never contained.

BUT RATES ARE COMPUTED ON ARRIVALS, NOT ON THE HELD GRID. This is the subtle
one. A naive hold makes mq2_rate zero for two windows out of three and then
dumps the whole 3-second jump into the third as a 3x spike -- a shape the model
has never seen. Computing the difference between arrivals and dividing by the
seconds between them gives the per-second rate, which is exactly what a 1 Hz
.diff() meant during training. It costs nothing and it is the difference
between a plausible channel and a spiky one.

TEMPERATURE IS ROUNDED ON PURPOSE. The generator does np.round(), so
temperature_c and humidity_pct are integers and temperature_rate is integer
quantised (its median is 0). A DHT22 reporting 0.1 degree resolution would
produce a continuous rate the model never saw, so the rounding is reproduced
here rather than treated as lost precision.
"""

from __future__ import annotations

import statistics

import constants as K

SENSOR_CHANNELS = (
    "mq2_delta", "mq2_rate", "mq7_delta", "mq7_rate", "mq_co_ratio",
    "flame_value", "flame_present", "temperature_c", "humidity_pct",
    "temperature_rate",
)


class SensorGapError(RuntimeError):
    """The node stopped reporting for long enough that holding would be a lie."""


def raw_from_reading(reading: dict, key: str) -> float | None:
    """Prefer the ADC value; reconstruct it from ppm only if that is all there is.

    The board computes ppm as a linear rescale of the ADC
    (mq2_ppm = mq2_raw/4095 * 2000), so the two are interchangeable -- but the
    training channel is ADC-shaped, with a baseline around 300 counts, so the
    raw form is the one that lands in the right range.
    """
    raw = reading.get(f"{key}_raw")
    if raw is not None:
        return float(raw)
    ppm = reading.get(f"{key}_ppm")
    if ppm is None:
        return None
    full = K.MQ2_PPM_FULL_SCALE if key == "mq2" else K.MQ7_PPM_FULL_SCALE
    return float(ppm) / full * K.ADC_FULL_SCALE


class SensorAdapter:
    """Turns a stream of node readings into 1 Hz model channels.

    Feed it arrivals with `observe()`, then ask for `channels()` once per
    window. It returns None while it is still measuring the baseline, because a
    delta computed against an unknown baseline is meaningless -- and worse,
    `cummax` and the rolling maxima never forget a poisoned early value.
    """

    def __init__(self, baseline_mode: str = "quiet_prefix",
                 mq2_baseline: float | None = None,
                 mq7_baseline: float | None = None,
                 flame_dark: float = K.FLAME_DARK_COUNTS,
                 flame_bright: float = K.FLAME_BRIGHT_COUNTS,
                 baseline_s: float = K.BASELINE_S):
        if baseline_mode not in ("quiet_prefix", "running_min", "manual"):
            raise ValueError(f"unknown baseline_mode: {baseline_mode}")
        self.baseline_mode = baseline_mode
        self.baseline_s = 0.0 if baseline_mode == "manual" else baseline_s
        self.flame_dark = float(flame_dark)
        self.flame_bright = float(flame_bright)

        self.mq2_base = mq2_baseline
        self.mq7_base = mq7_baseline
        if baseline_mode == "manual" and (mq2_baseline is None or mq7_baseline is None):
            raise ValueError("manual baseline mode needs both mq2 and mq7 baselines")

        self._prefix: list[tuple[float, float]] = []   # (mq2_raw, mq7_raw)
        self._last: dict | None = None                 # last arrival's values
        self._last_t: float | None = None
        self._rates = {"mq2_rate": 0.0, "mq7_rate": 0.0, "temperature_rate": 0.0}
        self.flame_disagreements = 0
        self.samples = 0

    # -- baseline ---------------------------------------------------------

    @property
    def baselining(self) -> bool:
        return self.mq2_base is None or self.mq7_base is None

    def _freeze_baseline(self) -> None:
        """Fix the baseline and never move it again.

        Freezing matters more than the estimator does. A baseline that dropped
        later would retroactively change every delta already emitted, and
        therefore every running maximum built from them -- so the feature
        history would stop being causal and the prediction would drift away
        from what a batch score gives.
        """
        if not self._prefix:
            return
        mq2s = [a for a, _ in self._prefix]
        mq7s = [b for _, b in self._prefix]
        if self.baseline_mode == "running_min":
            # For a session that was already burning when recording started:
            # the MQ response is monotone in combustible gas, so the minimum
            # seen is the cleanest air on offer. Worse than a quiet prefix,
            # which is why it is tagged in the output rather than silently used.
            self.mq2_base, self.mq7_base = min(mq2s), min(mq7s)
        else:
            # Median, not mean: MQ heaters and Wi-Fi transients spike, and the
            # training baseline was a single noiseless constant.
            self.mq2_base, self.mq7_base = statistics.median(mq2s), statistics.median(mq7s)

    # -- ingestion --------------------------------------------------------

    def observe(self, t: float, reading: dict) -> None:
        """Record one arrival. `t` is seconds since the session started."""
        mq2 = raw_from_reading(reading, "mq2")
        mq7 = raw_from_reading(reading, "mq7")
        temp = reading.get("temperature_c")
        hum = reading.get("humidity_pct")

        # Rounded here, before anything differences them, so the rate inherits
        # the same quantisation the training channel had.
        temp = None if temp is None else float(round(float(temp)))
        hum = None if hum is None else float(round(float(hum)))

        if self._last_t is not None and t > self._last_t:
            dt = t - self._last_t
            for name, now, was in (("mq2_rate", mq2, self._last.get("mq2_raw")),
                                   ("mq7_rate", mq7, self._last.get("mq7_raw")),
                                   ("temperature_rate", temp,
                                    self._last.get("temperature_c"))):
                if now is not None and was is not None:
                    self._rates[name] = (now - was) / dt

        self._last = {"mq2_raw": mq2, "mq7_raw": mq7, "temperature_c": temp,
                      "humidity_pct": hum,
                      "flame": reading.get("flame"),
                      "flame_raw": reading.get("flame_raw")}
        self._last_t = t
        self.samples += 1

        if self.baselining and self.baseline_mode != "manual":
            if mq2 is not None and mq7 is not None and t < self.baseline_s:
                self._prefix.append((mq2, mq7))
            elif t >= self.baseline_s:
                self._freeze_baseline()

    # -- flame ------------------------------------------------------------

    def _flame_value(self, reading: dict) -> float:
        """Analog IR counts -> the model's 0..1 flame channel.

        The module's AO is inverted: lower counts mean a brighter source. A
        linear inversion is the right shape because the training channel is
        linear in radiative flux before its own clip -- but note the training
        channel's median is 1.000, so this is effectively a three-state signal,
        not a calibrated radiometer. Do not read it as one.
        """
        raw = reading.get("flame_raw")
        digital = reading.get("flame")

        if raw is None:
            # DO-only node. Defensible precisely because the training channel
            # is saturated: 1.0 is its median value on burning windows.
            return 1.0 if digital else 0.0

        span = self.flame_dark - self.flame_bright
        value = 0.0 if span <= 0 else (self.flame_dark - float(raw)) / span
        value = max(0.0, min(1.0, value))

        # The digital pin is the module's own pot-calibrated presence call. If
        # it says flame and the analog map says none, the map is miscalibrated
        # -- so trust the module and count the disagreement, rather than
        # reporting "no flame" during a fire.
        if digital and value <= K.FLAME_PRESENT_THRESHOLD:
            self.flame_disagreements += 1
            value = K.FLAME_PRESENT_THRESHOLD + 0.01
        return value

    # -- emission ---------------------------------------------------------

    def channels(self, window_t: float) -> dict[str, float] | None:
        """The ten channels for the 1 Hz window ending at `window_t`.

        None while the baseline is still being measured. Raises SensorGapError
        once the node has been silent long enough that holding its last reading
        through a developing fire would be an invention -- the same failure
        esp32-sensor-service guards against by going stale rather than looking green.
        """
        if self.baselining and self.baseline_mode != "manual":
            if window_t >= self.baseline_s:
                self._freeze_baseline()
            if self.baselining:
                return None
        if self._last is None:
            return None

        age = window_t - (self._last_t or 0.0)
        if age > K.SENSOR_GAP_ABORT_S:
            raise SensorGapError(
                f"no sensor sample for {age:.0f}s (limit {K.SENSOR_GAP_ABORT_S:.0f}s)")

        last = self._last
        mq2 = last.get("mq2_raw")
        mq7 = last.get("mq7_raw")
        mq2_delta = 0.0 if mq2 is None else mq2 - self.mq2_base
        mq7_delta = 0.0 if mq7 is None else mq7 - self.mq7_base
        flame_value = self._flame_value(last)

        return {
            "mq2_delta": mq2_delta,
            "mq2_rate": self._rates["mq2_rate"],
            "mq7_delta": mq7_delta,
            "mq7_rate": self._rates["mq7_rate"],
            # Verbatim generator: mq7_delta / mq2_delta.clip(lower=5.0). The
            # floor stops a near-zero denominator turning sensor noise into a
            # huge ratio during clean air.
            "mq_co_ratio": mq7_delta / max(mq2_delta, K.MQ_RATIO_FLOOR),
            "flame_value": flame_value,
            "flame_present": 1.0 if flame_value > K.FLAME_PRESENT_THRESHOLD else 0.0,
            "temperature_c": last.get("temperature_c") or 0.0,
            "humidity_pct": last.get("humidity_pct") or 0.0,
            "temperature_rate": self._rates["temperature_rate"],
        }

    def status(self, window_t: float) -> dict:
        age = window_t - (self._last_t or 0.0)
        return {
            "baselining": self.baselining,
            "baseline_mode": self.baseline_mode,
            "baseline_source": ("manual" if self.baseline_mode == "manual"
                                else self.baseline_mode),
            "mq2_baseline": self.mq2_base,
            "mq7_baseline": self.mq7_base,
            "sensor_age_s": round(age, 1),
            "sensor_stale": age > K.SENSOR_STALE_AFTER_S,
            "flame_disagreements": self.flame_disagreements,
            "samples": self.samples,
        }
