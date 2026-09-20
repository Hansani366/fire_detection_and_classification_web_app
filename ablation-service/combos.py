"""
The six sensing combinations, each as a pure function over a feature frame.

EVERY COMBINATION RETURNS THE SAME SHAPE: a per-window boolean alarm and a
per-window scalar score. The scalar is what makes the comparison honest --
reporting only the operating point invites "you tuned the rules to lose", so
every arm also yields an ROC/PR curve from its score, which is threshold-free.

COMBINATIONS 1 AND 6 SHARE ONE INFERENCE. `fire_classifier.build_features()`
already runs sensor_model.predict_proba and splices the four probabilities in
as `sensor_p_*`, because the fusion model consumes them. Combination 1 reads
those same columns rather than calling the model again: one call, two arms, and
no chance of the two disagreeing.

THE DEBOUNCE IS SHARED, AND IT IS THE ONLY DEFINITION OF "ALARM". A raw rule
firing for one window is not an alarm; HOLD_WINDOWS consecutive windows is.
That single definition then answers all three questions -- is the alarm on now
(window level), did it ever raise (event level), and when did it first raise
(latency) -- so the three cannot drift apart.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import constants as K

GROUP = "experiment_id"


# ── shared helpers ───────────────────────────────────────────────────────────

def _debounce(raw: pd.Series, groups: pd.Series) -> pd.Series:
    """Raise only after HOLD_WINDOWS consecutive windows of raw evidence.

    Causal by construction -- window t sees t-2..t and nothing after -- so the
    first True is a real detection time, not a value a later window supplied.
    """
    n = K.HOLD_WINDOWS
    return (
        raw.astype(float)
        .groupby(groups, sort=False)
        .rolling(n, min_periods=n)
        .min()
        .reset_index(level=0, drop=True)
        .fillna(0.0)
        .astype(bool)
    )


def _rolling_any(flag: pd.Series, groups: pd.Series, window: int) -> pd.Series:
    """Was this true at any point in the trailing `window` windows?"""
    return (
        flag.astype(float)
        .groupby(groups, sort=False)
        .rolling(window, min_periods=1)
        .max()
        .reset_index(level=0, drop=True)
        .fillna(0.0)
        .astype(bool)
    )


def _rolling_max(value: pd.Series, groups: pd.Series, window: int) -> pd.Series:
    return (
        value.groupby(groups, sort=False)
        .rolling(window, min_periods=1)
        .max()
        .reset_index(level=0, drop=True)
        .fillna(0.0)
    )


def _smooth(value: pd.Series, groups: pd.Series, window: int) -> pd.Series:
    """The manifest's causal probability smoothing, applied to one scalar.

    fire_classifier._smooth() does this across the whole probability vector and
    renormalises. For a single already-normalised scalar such as 1 - p[no_fire]
    the rolling mean alone is the same operation.
    """
    return (
        value.groupby(groups, sort=False)
        .rolling(window, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )


# ── the six arms ─────────────────────────────────────────────────────────────

def combo1_sensors(features: pd.DataFrame, manifest: dict) -> tuple[pd.Series, pd.Series]:
    """Sensors only — sensor_model.joblib, read from the spliced columns."""
    groups = features[GROUP]
    p_fire = 1.0 - features["sensor_p_no_fire"]
    score = _smooth(p_fire, groups, manifest["config"]["smooth_window"])
    return score > K.BINARY_THRESHOLD, score


def combo2_yolo(features: pd.DataFrame, manifest: dict) -> tuple[pd.Series, pd.Series]:
    """YOLO only — confidence, box area, and persistence of its OWN evidence.

    A RULE'S PERSISTENCE MUST BE MEASURED ON THE RULE'S OWN EVIDENCE. The
    obvious shortcut is to reuse the model's `fire_persistence` feature, but
    that is the rolling mean of `yolo_fire_conf > 0.5` -- a different channel
    at a different threshold from the gate this rule actually applies. In this
    data the fire channel's median on burning windows is 0.044 while smoke
    carries the signal, so borrowing that feature would reject two thirds of
    the windows the rule itself had already accepted, and combination 2 would
    lose for a reason that has nothing to do with what YOLO can see.

    So persistence here is the rolling mean of THIS rule's own detection, over
    the manifest's persistence_window. The required fraction is unchanged --
    roll_windows[0] of persistence_window, 5 of 25 -- so nothing is tuned; only
    the base channel is corrected.
    """
    groups = features[GROUP]
    window = manifest["config"]["persistence_window"]

    # max over the two classes: the generator's own `yolo_detected` column is
    # exactly this gate, which is the cross-check that 0.35 is the right one.
    evidence = features[["yolo_fire_conf", "yolo_smoke_conf"]].max(axis=1)
    area_ok = (
        (features["fire_area_ratio"] >= K.MIN_AREA_RATIO)
        | (features["smoke_area_ratio"] >= K.MIN_AREA_RATIO)
    )
    detected = (evidence >= K.YOLO_DETECT_THRESHOLD) & area_ok
    persist = _smooth(detected.astype(float), groups, window)

    raw = detected & (persist >= K.FIRE_PERSISTENCE_MIN)
    # The score is the rolling mean of the continuous evidence rather than the
    # persistence fraction, which only takes 26 distinct values -- too coarse
    # to draw an ROC curve from.
    return raw, _smooth(evidence, groups, window)


def combo3_vlm(features: pd.DataFrame, manifest: dict) -> tuple[pd.Series, pd.Series]:
    """VLM only — the held verdict, with a "could not see" floor."""
    score = features[["vlm_flame_conf", "vlm_smoke_conf"]].max(axis=1)
    raw = (score > K.VLM_CONFIRM_THRESHOLD) & (
        features["vlm_visual_conf"] >= K.VLM_VIEW_FLOOR
    )
    return raw, score


def combo4_sensors_yolo(
    features: pd.DataFrame, manifest: dict,
    raw1: pd.Series, score1: pd.Series, raw2: pd.Series, score2: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Sensors + YOLO — vision now, sensors within the chemistry's lag."""
    groups = features[GROUP]
    agreed = _rolling_any(raw1, groups, K.SENSOR_AGREE_WINDOWS)
    recent1 = _rolling_max(score1, groups, K.SENSOR_AGREE_WINDOWS)
    # min() because this is an AND: the combination is only as confident as its
    # weaker arm. Using a product or a mean would let one loud arm carry a
    # silent one, which is not what the rule says.
    return raw2 & agreed, pd.concat([score2, recent1], axis=1).min(axis=1)


def combo5_vlm_yolo(
    features: pd.DataFrame, manifest: dict,
    raw2: pd.Series, score2: pd.Series, score3: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """VLM + YOLO — verbatim the rule the dashboard deploys today."""
    confirmed = features["vlm_confirmed"] > 0.5
    return raw2 & confirmed, pd.concat([score2, score3], axis=1).min(axis=1)


def combo6_fusion(
    features: pd.DataFrame, manifest: dict, clf,
) -> tuple[pd.Series, pd.Series, pd.DataFrame]:
    """All three — the trained fusion model, plus its 4-class fuel verdict."""
    groups = features[GROUP]
    proba = clf.fusion.predict_proba(features[clf.fusion_features])
    # The manifest's causal smoothing over the whole vector, renormalised --
    # the same call the model's own predict() makes, so combination 6 is scored
    # exactly as trained_model_v3/metrics.csv scored it.
    proba = clf._smooth(proba, groups.to_numpy())

    frame = pd.DataFrame(proba, columns=[f"p_{c}" for c in clf.classes],
                         index=features.index)
    frame["predicted_class"] = [clf.classes[i] for i in proba.argmax(axis=1)]
    frame["confidence"] = proba.max(axis=1)
    frame["low_confidence"] = frame["confidence"] < manifest["config"]["gate_threshold"]

    score = 1.0 - frame["p_no_fire"]
    return score > K.BINARY_THRESHOLD, score, frame


# ── orchestration ────────────────────────────────────────────────────────────

def score_all(
    features: pd.DataFrame, manifest: dict, clf, combos: list[int] | None = None,
) -> dict:
    """Run every requested combination over one prepared feature frame.

    Returns per-window raw rules, debounced alarms and scores, keyed by combo
    number, plus combination 6's fuel-class frame.
    """
    wanted = set(combos or K.COMBOS)
    groups = features[GROUP]
    raw: dict[int, pd.Series] = {}
    score: dict[int, pd.Series] = {}
    fuel = None

    # 1 and 2 first: 4 and 5 are built from them, so they are computed once.
    raw[1], score[1] = combo1_sensors(features, manifest)
    raw[2], score[2] = combo2_yolo(features, manifest)
    raw[3], score[3] = combo3_vlm(features, manifest)
    raw[4], score[4] = combo4_sensors_yolo(
        features, manifest, raw[1], score[1], raw[2], score[2])
    raw[5], score[5] = combo5_vlm_yolo(features, manifest, raw[2], score[2], score[3])
    raw[6], score[6], fuel = combo6_fusion(features, manifest, clf)

    return {
        "raw": {c: raw[c] for c in wanted},
        "alarm": {c: _debounce(raw[c], groups) for c in wanted},
        "score": {c: score[c].astype(float) for c in wanted},
        "fuel": fuel if 6 in wanted else None,
    }


def zero_vlm_channels(frame: pd.DataFrame) -> pd.DataFrame:
    """Set the eleven VLM channels to their never-invoked values.

    Ten zeros and vlm_staleness_s = -1.0. This is not an invented "modality
    off" encoding: it is exactly what the generator emits for a session where
    YOLO never fired, so a combination that excludes the VLM stays inside the
    training distribution instead of being handed a row the model never saw.
    """
    out = frame.copy()
    for col in ("vlm_invoked", "vlm_confirmed", "vlm_flame_conf", "vlm_smoke_conf",
                "vlm_smoke_darkness", "vlm_flame_colour_index",
                "vlm_gas_source_conf", "vlm_liquid_source_conf",
                "vlm_solid_source_conf", "vlm_visual_conf"):
        if col in out:
            out[col] = 0.0
    if "vlm_staleness_s" in out:
        out["vlm_staleness_s"] = K.VLM_NEVER_INVOKED_STALENESS
    return out
