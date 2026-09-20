"""
Scoring the six combinations, at the two levels a reviewer will ask for.

WINDOW LEVEL IS OPERATIONAL, EVENT LEVEL IS THE HEADLINE. "At any given second,
is the alarm right?" and "did this fire get caught at all?" are different
questions with very different numbers, and quoting only one invites the obvious
objection. trained_model_v3/metrics.csv reports both, which is also what keeps
our numbers externally checkable.

PRE-IGNITION WINDOWS OF A FIRE EXPERIMENT ARE NEGATIVES. This is the single
decision that makes false-alarm rate and latency mean anything. An experiment
labelled `liquid_fuel` is not on fire at t=0 -- it ignites part way through. If
every window of it counts as positive, then a detector that alarms immediately
and never stops scores perfectly, and its latency is zero. (That is exactly why
metrics.csv shows median_detection_s = 0.0; we report both definitions and say
which is which.)

RATES GET CONFIDENCE INTERVALS BECAUSE THE SAMPLE IS SMALL. 96 events, 24 of
them negative, does not support three decimal places. Every rate here carries a
95% Wilson interval, and every comparison against combination 6 carries an
exact McNemar test -- because the headline gap between the fusion model and
sensors alone is ONE event out of 96, and a paper that claims that as a win
gets rejected while a paper that measures it and says "not significant" gets
cited.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

import constants as K

GROUP = "experiment_id"
NO_FIRE = "no_fire"


def json_safe(value):
    """Make a result tree serialisable, turning undefined numbers into null.

    Two distinct problems, both of which fail only at the HTTP boundary and so
    are easy to miss locally: NaN and infinity are not valid JSON (Python's own
    json.dumps emits them anyway, but a strict encoder refuses), and numpy
    scalars are not JSON types at all.

    NaN becomes null rather than 0.0 deliberately. A precision of NaN means
    "this arm never fired, so precision is undefined" -- writing 0.0 would
    claim it fired and was always wrong, which is a different and much worse
    statement about a detector.
    """
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    return value


# ── ground truth ─────────────────────────────────────────────────────────────

def build_truth(frame: pd.DataFrame, windows: pd.DataFrame) -> pd.DataFrame:
    """Per-window and per-event binary truth, anchored on ignition.

    `frame` is the raw input (sorted the way build_features sorts it) and must
    carry `fire_type`. Ignition comes from `cfast_hrr_kw` for replayed CFAST
    experiments, or `ignition_offset_s` for real recordings. Both are
    evaluation-only: they are read here and never reach a model.
    """
    truth = frame.sort_values([GROUP, "timestamp"]).reset_index(drop=True)
    out = pd.DataFrame({
        GROUP: truth[GROUP],
        "window_idx": windows["window_idx"].to_numpy(),
        "fire_type": truth["fire_type"],
    })
    out["is_fire_event"] = out["fire_type"] != NO_FIRE

    if "cfast_hrr_kw" in truth.columns:
        burning = truth["cfast_hrr_kw"].astype(float) > 0.0
    elif "ignition_offset_s" in truth.columns:
        burning = out["window_idx"] >= truth["ignition_offset_s"].astype(float).round()
    else:
        # No ignition ground truth: fall back to "the whole fire experiment is
        # positive" and flag it, rather than silently changing the definition.
        burning = out["is_fire_event"]
        out.attrs["ignition_known"] = False

    # First burning window per experiment, then "at or after" it -- so a brief
    # dip in heat-release rate mid-fire does not turn windows back into
    # negatives.
    first = (out.assign(_b=burning.to_numpy())
                .groupby(GROUP, sort=False)["_b"]
                .transform(lambda s: s.idxmax() if s.any() else -1))
    idx = pd.Series(out.index, index=out.index)
    ignited = (first >= 0) & (idx >= first)

    out["ignition_window"] = np.where(
        first >= 0, out["window_idx"].to_numpy() - (idx - first).to_numpy(), -1)
    out["y_window"] = out["is_fire_event"] & ignited
    return out


# ── interval estimates ───────────────────────────────────────────────────────

def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Wilson rather than the normal approximation because several of these rates
    sit near 0 or 1 on small denominators, where the normal interval runs past
    the ends of [0, 1] and stops being a probability.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def mcnemar(a_correct: np.ndarray, b_correct: np.ndarray) -> dict:
    """Exact McNemar test for two detectors judged on the SAME events.

    Paired, because both arms saw identical inputs -- an unpaired test would
    throw away that pairing and lose most of the power we have on 96 events.
    Exact binomial rather than the chi-square approximation, which is not
    trustworthy when the discordant count is small, and here it usually is.
    """
    b = int(np.sum(a_correct & ~b_correct))   # a right, b wrong
    c = int(np.sum(~a_correct & b_correct))   # a wrong, b right
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "n_discordant": 0, "p_value": 1.0,
                "note": "the two arms agreed on every event"}

    # Two-sided exact: P(X <= min(b,c)) + P(X >= max(b,c)) under Binomial(n, .5)
    lo = min(b, c)
    tail = sum(math.comb(n, i) for i in range(lo + 1)) / (2 ** n)
    p = min(1.0, 2 * tail)
    return {"b": b, "c": c, "n_discordant": n, "p_value": p}


# ── binary scoring ───────────────────────────────────────────────────────────

def binary_scores(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    y_true = np.asarray(y_true, dtype=bool)
    y_pred = np.asarray(y_pred, dtype=bool)
    tp = int(np.sum(y_true & y_pred))
    fp = int(np.sum(~y_true & y_pred))
    tn = int(np.sum(~y_true & ~y_pred))
    fn = int(np.sum(y_true & ~y_pred))

    def ratio(num, den):
        return num / den if den else float("nan")

    precision = ratio(tp, tp + fp)
    recall = ratio(tp, tp + fn)
    f1 = ratio(2 * precision * recall, precision + recall) if tp else 0.0
    n_neg = fp + tn

    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "n": tp + fp + tn + fn, "n_positive": tp + fn, "n_negative": n_neg,
        "accuracy": ratio(tp + tn, tp + fp + tn + fn),
        "accuracy_ci": wilson(tp + tn, tp + fp + tn + fn),
        "precision": precision,
        "precision_ci": wilson(tp, tp + fp),
        "recall": recall,
        "recall_ci": wilson(tp, tp + fn),
        "f1": f1,
        "false_alarm_rate": ratio(fp, n_neg),
        "false_alarm_ci": wilson(fp, n_neg),
        # The same number a fire officer would actually feel. 0.166 per window
        # sounds small; 600 nuisance alarms per hour is the honest phrasing.
        "false_alarms_per_hour": ratio(fp, n_neg) * 3600 * K.WINDOW_HZ,
        "confusion": {"actual_fire": {"predicted_fire": tp, "predicted_none": fn},
                      "actual_none": {"predicted_fire": fp, "predicted_none": tn}},
    }


def detection_latency(alarm: pd.Series, truth: pd.DataFrame) -> dict:
    """Seconds from ignition to the first debounced alarm, over fire events.

    Median and p90, never a mean: an event that was never detected has no
    latency at all, so a mean over the survivors is biased downward exactly
    when a detector is at its worst. `events_never_detected` carries that
    information instead of hiding it.
    """
    delays, never = [], 0
    joined = truth.assign(alarm=np.asarray(alarm, dtype=bool))
    for _, grp in joined[joined["is_fire_event"]].groupby(GROUP, sort=False):
        ignition = grp["ignition_window"].iloc[0]
        fired = grp[grp["alarm"] & (grp["window_idx"] >= ignition)]
        if fired.empty:
            never += 1
        else:
            delays.append(float(fired["window_idx"].iloc[0] - ignition) / K.WINDOW_HZ)

    return {
        "median_detection_s": float(np.median(delays)) if delays else None,
        "p90_detection_s": float(np.percentile(delays, 90)) if delays else None,
        "events_detected": len(delays),
        "events_never_detected": never,
    }


# ── the fuel-type table (combination 6, and combination 1) ───────────────────

def fuel_scores(y_true: np.ndarray, y_pred: np.ndarray, classes: list[str],
                gate_mask: np.ndarray | None = None) -> dict:
    """4-class confusion plus per-class P/R/F1 and macro-F1.

    `no_fire` stays as a row and a column rather than being dropped, so a
    misfire on a quiet room is visible in the same table as a fuel mix-up.
    """
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)
    matrix = {a: {b: int(np.sum((y_true == a) & (y_pred == b))) for b in classes}
              for a in classes}

    per_class, f1s = {}, []
    for name in classes:
        tp = matrix[name][name]
        fp = int(np.sum((y_true != name) & (y_pred == name)))
        fn = int(np.sum((y_true == name) & (y_pred != name)))
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        per_class[name] = {"precision": p, "recall": r, "f1": f1,
                           "support": int(np.sum(y_true == name))}
        f1s.append(f1)

    detected = (y_true != NO_FIRE) & (y_pred != NO_FIRE)
    wrong_fuel = int(np.sum(detected & (y_true != y_pred)))

    out = {
        "confusion": matrix,
        "per_class": per_class,
        "macro_f1": float(np.mean(f1s)),
        "accuracy": float(np.mean(y_true == y_pred)),
        # Mirrors the column name in trained_model_v3/metrics/metrics.csv so
        # the two tables can be compared line by line.
        "wrong_fuel_given_detected": wrong_fuel / int(np.sum(detected))
        if np.sum(detected) else float("nan"),
    }
    if gate_mask is not None:
        out["abstain_rate"] = float(np.mean(gate_mask))
    return out


# ── orchestration ────────────────────────────────────────────────────────────

def evaluate(scored: dict, truth: pd.DataFrame, clf, manifest: dict,
             synthetic: bool) -> dict:
    """Everything the results page and the export need, for every combination."""
    combos = sorted(scored["alarm"])
    y_window = truth["y_window"].to_numpy()

    event_truth = truth.groupby(GROUP, sort=False)["is_fire_event"].first()
    event_ids = event_truth.index.to_numpy()
    y_event = event_truth.to_numpy()

    per_combo, event_correct = {}, {}
    for c in combos:
        alarm = scored["alarm"][c]
        # One definition of "the alarm raised" at both levels: the debounced
        # series now, and whether it ever raised for the event.
        ev_pred = (truth.assign(a=np.asarray(alarm, dtype=bool))
                        .groupby(GROUP, sort=False)["a"].any()
                        .reindex(event_ids).to_numpy())
        per_combo[c] = {
            "name": K.COMBOS[c],
            "modalities": K.COMBO_MODALITIES[c],
            "window": binary_scores(y_window, np.asarray(alarm, dtype=bool)),
            "event": binary_scores(y_event, ev_pred),
            "latency": detection_latency(alarm, truth),
            "score_summary": {
                "min": float(np.nanmin(scored["score"][c])),
                "median": float(np.nanmedian(scored["score"][c])),
                "max": float(np.nanmax(scored["score"][c])),
            },
        }
        event_correct[c] = ev_pred == y_event

    # Paired comparison against the full system. This is the number the paper
    # lives or dies on, so it is reported with the absolute event count beside
    # it, not only as a percentage.
    if 6 in event_correct:
        for c in combos:
            if c == 6:
                continue
            test = mcnemar(event_correct[6], event_correct[c])
            delta = int(event_correct[6].sum() - event_correct[c].sum())
            per_combo[c]["vs_combo6"] = {
                **test,
                "event_delta": delta,
                "event_delta_of": int(len(y_event)),
                "interpretation":
                    f"combination 6 gets {abs(delta)} "
                    f"{'more' if delta >= 0 else 'fewer'} of "
                    f"{len(y_event)} events right"
                    + ("" if test["p_value"] < 0.05
                       else " — not statistically significant"),
            }

    result = {
        "combos": per_combo,
        "n_windows": int(len(truth)),
        "n_events": int(len(y_event)),
        "n_fire_events": int(y_event.sum()),
        "ignition_known": truth.attrs.get("ignition_known", True),
        "synthetic": synthetic,
    }

    if scored.get("fuel") is not None:
        fuel = scored["fuel"]
        proba_cols = [f"p_{c}" for c in clf.classes]
        ev = (fuel.assign(**{GROUP: truth[GROUP].to_numpy()})
                  .groupby(GROUP, sort=False)[proba_cols].mean()
                  .reindex(event_ids))
        ev_pred = np.array([clf.classes[i] for i in ev.to_numpy().argmax(axis=1)])
        ev_true = (truth.groupby(GROUP, sort=False)["fire_type"].first()
                        .reindex(event_ids).to_numpy())
        gate = ev.to_numpy().max(axis=1) < manifest["config"]["gate_threshold"]
        result["fuel"] = {
            "classes": clf.classes,
            "event": fuel_scores(ev_true, ev_pred, clf.classes, gate),
            "window": fuel_scores(truth["fire_type"].to_numpy(),
                                  fuel["predicted_class"].to_numpy(), clf.classes),
            "gate_threshold": manifest["config"]["gate_threshold"],
        }
    # Sanitised once, here, rather than at each route: every caller of
    # evaluate() ends up on the wire.
    return json_safe(result)
