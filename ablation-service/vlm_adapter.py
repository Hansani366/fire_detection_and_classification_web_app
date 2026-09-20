"""
vlm-service's detailed response -> the eleven VLM channels the model expects.

THE VLM IS A CASCADE CONFIRMER, NOT A PARALLEL BRANCH. In the training
generator it runs only when YOLO fires, on a cooldown, and its verdict is HELD
between calls. So a row's VLM channels are usually not a fresh observation --
they are the last observation, plus how old it is. `vlm_invoked` and
`vlm_staleness_s` exist precisely because a zero in a VLM column is otherwise
ambiguous between "looked, saw nothing" and "never looked".

MINUS ONE IS A VALUE, NOT A MISSING MARKER. Before the first invocation
`vlm_staleness_s` is -1.0. That is a real number in the training distribution
and the only thing distinguishing a session the VLM never looked at from one
where it looked and saw nothing. Writing 0.0 there would claim a confident
negative observation that never happened.

THE THREE SOURCE SCORES SUM TO `evidence`, NOT TO 1. The generator computes a
softmax over fuel templates and multiplies it by `evidence`. Measured on the
test split, the three sum to a median of 0.46. Passing three numbers that sum
to 1.0 would put every row out of distribution on the model's most-used VLM
feature family -- so the prompt asks for independent judgements and this module
does the scaling.

THERE ARE TWO DIFFERENT CONFIDENCES, AND CONFLATING THEM IS SILENT. In the
generator, `evidence = max(obs_flame, obs_smoke)` is what the camera could
actually observe, and it scales the source, darkness and visual channels. But
the confidences the VLM *reports* are that observation attenuated by how well
it could see:

    vlm_flame_conf = obs_flame * (0.55 + 0.45 * view)

So `vlm_flame_conf` is always <= `obs_flame`, and reconstructing `evidence` as
`max(vlm_flame_conf, vlm_smoke_conf)` under-reads it. A real VLM's answer is
the *reported* kind: asked about a hazy image it already hedges. This module
therefore inverts the attenuation to recover the observation before scaling
anything by it. The divisor lies in [0.55, 1.0], so it cannot blow up.

Measured on the 1,444 invoked rows of the test split, recovering `evidence`:

    estimator                  bias      mean|err|
    max(reported)            -0.1928       0.1961
    de-attenuated (this)     +0.0007       0.0567

The naive form carries a large systematic bias; de-attenuating removes it
almost exactly. The 0.057 that remains is the generator's own
`rng.normal(0, 0.05)` injected after the attenuation, which no inversion can
undo -- so a perfect round-trip is not achievable and not the target.

`vlm_confirmed` is the one exception: the generator compares the REPORTED
confidences against the threshold, not the recovered evidence, so this module
does too.

AN ERROR IS NOT AN OBSERVATION. A timeout or a 500 leaves the hold untouched
and keeps ageing it. Zeroing the channels mid-session would invent a confident
"saw nothing" from a request that never completed, which is a distribution the
model has never seen.
"""

from __future__ import annotations

import constants as K

# In the order the model's feature list expects them. Anything building a row
# by hand should iterate this rather than writing the names out again.
VLM_CHANNELS = (
    "vlm_invoked", "vlm_confirmed", "vlm_staleness_s", "vlm_flame_conf",
    "vlm_smoke_conf", "vlm_smoke_darkness", "vlm_flame_colour_index",
    "vlm_gas_source_conf", "vlm_liquid_source_conf", "vlm_solid_source_conf",
    "vlm_visual_conf",
)

NEVER_INVOKED = {
    "vlm_invoked": 0.0,
    "vlm_confirmed": 0.0,
    "vlm_staleness_s": K.VLM_NEVER_INVOKED_STALENESS,
    "vlm_flame_conf": 0.0,
    "vlm_smoke_conf": 0.0,
    "vlm_smoke_darkness": 0.0,
    "vlm_flame_colour_index": 0.0,
    "vlm_gas_source_conf": 0.0,
    "vlm_liquid_source_conf": 0.0,
    "vlm_solid_source_conf": 0.0,
    "vlm_visual_conf": 0.0,
}


# The generator's view attenuation: reported = observed * (VIEW_FLOOR_GAIN +
# VIEW_GAIN * view). Named rather than inlined because the inversion below has
# to use exactly the same two numbers.
VIEW_FLOOR_GAIN = 0.55
VIEW_GAIN = 0.45


def to_channels(detail: dict) -> dict[str, float]:
    """One detailed VLM response -> the nine observation channels.

    `vlm_invoked` and `vlm_staleness_s` are left to the caller, because they
    describe *when* the observation happened rather than what it saw.
    """
    flame = float(detail.get("flame_visible", 0.0))
    smoke = float(detail.get("smoke_visible", 0.0))
    view = float(detail.get("view_quality", 0.0))

    # Undo the view attenuation to recover what the camera could observe. The
    # VLM's own answer is already hedged for a poor view, so scaling the source
    # and darkness channels by it directly would apply the same penalty twice.
    attenuation = VIEW_FLOOR_GAIN + VIEW_GAIN * view
    obs_flame = min(1.0, flame / attenuation)
    obs_smoke = min(1.0, smoke / attenuation)
    evidence = max(obs_flame, obs_smoke)

    gas = float(detail.get("source_gas", 0.0))
    liquid = float(detail.get("source_liquid", 0.0))
    solid = float(detail.get("source_solid", 0.0))
    total = gas + liquid + solid
    # Normalise then rescale by evidence: reproduces softmax(...) * evidence in
    # the property that matters, which is that the three sum to evidence. When
    # the VLM saw no fuel at all there is nothing to apportion.
    if total > 0.0:
        gas, liquid, solid = (x / total * evidence for x in (gas, liquid, solid))
    else:
        gas = liquid = solid = 0.0

    return {
        # Compares the REPORTED confidences, matching the generator's
        # `max(held[0], held[1]) > VLM_CONFIRM_THRESHOLD`.
        "vlm_confirmed": 1.0 if max(flame, smoke) > K.VLM_CONFIRM_THRESHOLD else 0.0,
        "vlm_flame_conf": flame,
        "vlm_smoke_conf": smoke,
        "vlm_smoke_darkness": float(detail.get("smoke_darkness", 0.0)) * evidence,
        # min(1, 2*obs_flame) verbatim from the generator: the colour reading is
        # trusted at full weight once the observation passes 0.5, and faded out
        # below that rather than switched off at a threshold.
        "vlm_flame_colour_index": float(detail.get("flame_colour_index", 0.0))
        * min(1.0, 2.0 * obs_flame),
        "vlm_gas_source_conf": gas,
        "vlm_liquid_source_conf": liquid,
        "vlm_solid_source_conf": solid,
        "vlm_visual_conf": evidence * view,
    }


class VlmHold:
    """Sample-and-hold over the VLM, one per live session or experiment.

    Mirrors the generator's loop: invoke at most once per cooldown, hold the
    result in between, and age it. Time is counted in WINDOWS, because at the
    model's 1 Hz rate `vlm_staleness_s` is a window count -- which is also why
    feeding this at any other rate would quietly rescale the channel.
    """

    def __init__(self, cooldown_s: float = K.VLM_COOLDOWN_S):
        self.cooldown_windows = max(1, round(cooldown_s * K.WINDOW_HZ))
        self._held: dict[str, float] | None = None
        self._windows_since = 0
        self.invocations = 0
        self.errors = 0

    def due(self, gated: bool = True) -> bool:
        """Should the VLM be called on this window?

        `gated` is the caller's own trigger -- YOLO having fired, for
        combinations 5 and 6. Combination 3 passes True unconditionally, which
        is the whole reason it is a VLM-only arm rather than a YOLO-gated one.
        """
        if not gated:
            return False
        if self._held is None:
            return True
        return self._windows_since >= self.cooldown_windows

    def observe(self, detail: dict) -> None:
        """Record a successful call. Resets staleness to zero."""
        self._held = to_channels(detail)
        self._windows_since = 0
        self.invocations += 1

    def failed(self) -> None:
        """Record a call that did not complete. Deliberately keeps the hold."""
        self.errors += 1

    def tick(self) -> None:
        """Advance one window. Call once per window, after observe/failed."""
        if self._held is not None:
            self._windows_since += 1

    def channels(self, invoked_this_window: bool = False) -> dict[str, float]:
        if self._held is None:
            return dict(NEVER_INVOKED)
        return {
            **self._held,
            "vlm_invoked": 1.0 if invoked_this_window else 0.0,
            "vlm_staleness_s": float(self._windows_since) / K.WINDOW_HZ,
        }
