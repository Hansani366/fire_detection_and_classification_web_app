"""
Flame flicker from a sequence of frames — the batch twin of js/flicker.js.

THE TWO IMPLEMENTATIONS MUST AGREE. The live tab measures this channel in the
browser at 16 Hz; this measures it here from recorded frames. If they used
different windows, different detrending or a different peak test, a recording
and a live session would disagree about the same fire, and the ablation would
be comparing the measurement rather than the system. Every constant comes from
constants.py, which js/flicker.js mirrors by hand with a comment pointing here.

A LOW FRAME RATE IS REFUSED, NOT APPROXIMATED. Real flame flickers at about
2.1 Hz, so a source below ~12 Hz has a Nyquist limit under 6 Hz and folds that
peak down toward zero -- which is exactly the generator's value for "nothing
there". Estimating anyway would fabricate a confident "no flame" on every real
flame. Better to emit the quiet value and mark the channel unavailable.
"""

from __future__ import annotations

import numpy as np

import constants as K

_HANN = np.hanning(K.FLICKER_WINDOW_N)


def estimate(samples: np.ndarray) -> float:
    """Dominant flicker frequency of one window of mean-luminance samples."""
    n = K.FLICKER_WINDOW_N
    if len(samples) < n:
        return K.FLICKER_QUIET_HZ

    window = np.asarray(samples[-n:], dtype=float)

    # Detrend with a least-squares line: a growing fire gets steadily brighter,
    # and without removing that ramp its energy lands in the low bins and reads
    # as very slow flicker.
    x = np.arange(n)
    slope, intercept = np.polyfit(x, window, 1)
    detrended = (window - (slope * x + intercept)) * _HANN

    mags = np.abs(np.fft.rfft(detrended))

    # Bins 0 and 1 are DC and 0.25 Hz -- below any real flame, and where
    # whatever trend survived detrending ends up.
    top = int(K.FLICKER_MAX_HZ / K.FLICKER_BIN_HZ) + 1
    band = mags[2:min(top, len(mags))]
    if band.size == 0:
        return K.FLICKER_QUIET_HZ

    peak = int(band.argmax())
    # Glare has a flat spectrum; flame has a peak. Without this the estimator
    # returns the argmax of noise and calls it a flame.
    if band[peak] <= K.FLICKER_PEAK_RATIO * float(np.median(mags[2:])):
        return K.FLICKER_QUIET_HZ

    return float(min(K.FLICKER_MAX_HZ, (peak + 2) * K.FLICKER_BIN_HZ))


def luminance(image, boxes: list[list[float]]) -> float | None:
    """Mean Rec. 601 luma inside the union bounding box of `boxes`.

    Returns None when there is no box to measure, which the caller treats as
    "no flame visible" rather than as a zero reading.
    """
    if not boxes:
        return None
    x1 = max(0, int(min(b[0] for b in boxes)))
    y1 = max(0, int(min(b[1] for b in boxes)))
    x2 = int(max(b[2] for b in boxes))
    y2 = int(max(b[3] for b in boxes))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return None

    crop = np.asarray(image.convert("RGB").crop((x1, y1, x2, y2)), dtype=float)
    if crop.size == 0:
        return None
    return float(0.299 * crop[..., 0].mean()
                 + 0.587 * crop[..., 1].mean()
                 + 0.114 * crop[..., 2].mean())


def usable(frame_rate_hz: float) -> bool:
    return frame_rate_hz >= K.FLICKER_MIN_SOURCE_HZ
