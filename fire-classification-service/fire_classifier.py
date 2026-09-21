"""Load the trained fire-classification model and run it on new observations.

VENDORED FILE -- DO NOT EDIT. This is a verbatim copy from the sibling repo
`../fire_classification_model/trained_model_v3/fire_classifier.py`. It is
copied rather than imported so `docker compose build` works from this
repository alone. To update it, re-copy it together with model/*.joblib and
model/manifest.json -- they are a matched set, and a mismatched manifest
silently changes the features. See model/PROVENANCE.md.

The model does not score rows in isolation. It expects a *sequence* of
observations per experiment, because most of its features are temporal --
rolling statistics, differences and running maxima over the preceding windows.
Handing it a single detached row will produce a prediction, but a poor one.

Everything about how features are rebuilt comes from `model/manifest.json`,
which the training notebook writes. Nothing here is hardcoded, so the serving
pipeline cannot drift away from the training pipeline without the manifest
changing too.

Typical use:

    from fire_classifier import FireClassifier

    clf = FireClassifier.load()
    result = clf.predict(df)        # df has one row per observation window
    print(result[["experiment_id", "predicted_class", "confidence"]])
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent / "model"

# Columns the model needs to see in the incoming frame, beyond the raw channels.
GROUP_COL = "experiment_id"
TIME_COL = "timestamp"

# Abstention is an outcome, not a class.
ABSTAIN_LABEL = "abstain"


class FireClassifier:
    """The trained fusion model plus the feature pipeline it was trained with."""

    def __init__(self, fusion_bundle: dict, sensor_bundle: dict, manifest: dict):
        self.fusion = fusion_bundle["model"]
        self.fusion_features = fusion_bundle["features"]
        self.sensor = sensor_bundle["model"]
        self.sensor_features = sensor_bundle["features"]
        self.manifest = manifest

        self.classes = manifest["class_names"]
        self.config = manifest["config"]
        self.groups = manifest["feature_groups"]

        # Only some trained variants consume the sensor model's probabilities;
        # `concat_all`, for instance, reads the raw sensor columns instead.
        self.needs_sensor_proba = any(
            col in self.fusion_features for col in self.groups["sensor_probability"]
        )

    # -- loading ----------------------------------------------------------

    @classmethod
    def load(cls, model_dir: Path | str = MODEL_DIR) -> "FireClassifier":
        model_dir = Path(model_dir)
        manifest = json.loads((model_dir / "manifest.json").read_text())
        return cls(
            fusion_bundle=joblib.load(model_dir / "fusion_model.joblib"),
            sensor_bundle=joblib.load(model_dir / "sensor_model.joblib"),
            manifest=manifest,
        )

    # -- feature pipeline -------------------------------------------------

    def _recompute_persistence(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Fraction of the recent past that carried a positive detection.

        Causal by construction: window `t` sees windows `t-N..t` and nothing
        after. The training notebook computes these the same way rather than
        using the dataset's shipped persistence columns, which were derived
        from ground truth and would not exist at inference time.
        """
        out = frame.copy()
        window = self.config["persistence_window"]
        threshold = self.config["yolo_fire_threshold"]

        out["_fire_hit"] = (out["yolo_fire_conf"] > threshold).astype(float)
        out["_sensor_hit"] = out["flame_present"].astype(float)
        grouped = out.groupby(GROUP_COL, sort=False)
        for src, dst in [("_fire_hit", self.groups["persistence_vision"][0]),
                         ("_sensor_hit", self.groups["persistence_sensor"][0])]:
            out[dst] = (grouped[src].rolling(window, min_periods=1).mean()
                                    .reset_index(level=0, drop=True))
        return out.drop(columns=["_fire_hit", "_sensor_hit"])

    def _add_temporal(self, frame: pd.DataFrame) -> pd.DataFrame:
        out = frame.copy()
        grouped = out.groupby(GROUP_COL, sort=False)

        # Position within the experiment. A caller that scores a trimmed buffer
        # must supply these itself -- derived from the buffer they would restart
        # at 0 on every call and the model would think each batch was a fresh
        # event. Supplying them is not enough to make a trimmed buffer correct
        # (see the note on cummax in predict), but it is necessary.
        if "window_idx" not in out.columns:
            out["window_idx"] = grouped.cumcount()
        if "elapsed_s" not in out.columns:
            out["elapsed_s"] = grouped[TIME_COL].transform(
                lambda s: (s - s.iloc[0]).dt.total_seconds())

        # Built as separate blocks and joined once -- assigning ~100 columns one
        # at a time fragments the frame badly.
        blocks = []
        for base_cols in self.groups["temporal_base"].values():
            for window in self.config["roll_windows"]:
                roller = grouped[base_cols].rolling(window, min_periods=1)
                for stat in ("mean", "std", "max"):
                    block = getattr(roller, stat)().reset_index(level=0, drop=True)
                    blocks.append(block.add_suffix(f"_roll{window}_{stat}").fillna(0.0))

            blocks.append(grouped[base_cols].diff().fillna(0.0).add_suffix("_diff1"))
            blocks.append(grouped[base_cols].cummax().add_suffix("_cummax"))

        return pd.concat([out] + blocks, axis=1)

    def build_features(self, frame: pd.DataFrame) -> pd.DataFrame:
        """Raw observations -> the exact feature matrix the model was trained on."""
        missing = [c for c in (GROUP_COL, TIME_COL) if c not in frame.columns]
        if missing:
            raise ValueError(
                f"input is missing {missing}. The model needs {GROUP_COL} to keep "
                f"experiments apart and {TIME_COL} to order them, because its "
                f"features are temporal.")

        out = frame.copy()
        out[TIME_COL] = pd.to_datetime(out[TIME_COL])

        # Frames assembled a row at a time, or parsed from JSON, arrive with
        # object-dtype columns. The rolling and cumulative operations below
        # cannot run on those, so coerce the raw channels up front rather than
        # failing deep inside the feature builder.
        channels = [c for c in self.required_columns() if c in out.columns]
        object_channels = [c for c in channels if out[c].dtype == object]
        if object_channels:
            out[object_channels] = out[object_channels].apply(
                pd.to_numeric, errors="coerce")
            unparsed = [c for c in object_channels if out[c].isna().all()]
            if unparsed:
                raise ValueError(
                    f"these columns hold no numeric values: {unparsed}. "
                    f"Check the input is raw sensor readings, not formatted text.")

        out = out.sort_values([GROUP_COL, TIME_COL]).reset_index(drop=True)

        if self.config["recompute_persistence"]:
            out = self._recompute_persistence(out)
        out = self._add_temporal(out)

        if self.needs_sensor_proba:
            proba = self.sensor.predict_proba(out[self.sensor_features])
            out[self.groups["sensor_probability"]] = proba

        absent = [c for c in self.fusion_features if c not in out.columns]
        if absent:
            raise ValueError(
                f"{len(absent)} feature(s) could not be built, first few: {absent[:5]}. "
                f"Check that the input carries every raw channel the model expects "
                f"(see FireClassifier.required_columns()).")
        return out

    def required_columns(self) -> list[str]:
        """Raw channels the caller must supply, beyond experiment_id/timestamp."""
        groups = self.groups
        return sorted(set(groups["yolo"] + groups["vlm"] + groups["sensor"]))

    # -- prediction -------------------------------------------------------

    def _smooth(self, proba: np.ndarray, group_ids: np.ndarray) -> np.ndarray:
        """Causal rolling mean of the probability vector, within an experiment.

        Stops one noisy frame from flipping the decision.
        """
        window = self.config["smooth_window"]
        frame = pd.DataFrame(proba).assign(**{GROUP_COL: group_ids})
        rolled = (frame.groupby(GROUP_COL, sort=False)[list(range(proba.shape[1]))]
                       .rolling(window, min_periods=1).mean()
                       .reset_index(level=0, drop=True)
                       .to_numpy())
        return rolled / rolled.sum(axis=1, keepdims=True)

    def predict(self, frame: pd.DataFrame, smooth: bool = True,
                gate: bool = False) -> pd.DataFrame:
        """Per-window predictions.

        smooth -- apply the causal probability smoothing used during evaluation.
        gate   -- return "abstain" when the top probability is below the
                  manifest's threshold. Abstention is its own outcome, never one
                  of the classes: routing it into a class would let the model
                  take credit for refusing to answer.

                  Worth knowing before you rely on it: confidence has been
                  measured as a novelty detector on held-out fuels the model
                  never saw, and it scores AUROC 0.485 -- chance. Gating trades
                  coverage for precision on FAMILIAR fuels; it will not catch an
                  unfamiliar one.
        """
        features = self.build_features(frame)
        proba = self.fusion.predict_proba(features[self.fusion_features])
        group_ids = features[GROUP_COL].to_numpy()

        if smooth:
            proba = self._smooth(proba, group_ids)

        predictions = proba.argmax(axis=1)
        confidence = proba.max(axis=1)
        abstained = confidence < self.config["gate_threshold"]

        labels = [self.classes[i] for i in predictions]
        if gate:
            labels = [ABSTAIN_LABEL if low else name
                      for name, low in zip(labels, abstained)]

        result = pd.DataFrame({
            GROUP_COL: group_ids,
            TIME_COL: features[TIME_COL].to_numpy(),
            "window_idx": features["window_idx"].to_numpy(),
            "predicted_class": labels,
            "confidence": confidence,
            "low_confidence": abstained,
        })
        for i, name in enumerate(self.classes):
            result[f"p_{name}"] = proba[:, i]
        return result

    def predict_events(self, frame: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """One decision per experiment, by averaging its windows' probabilities.

        This is the call that answers "what kind of fire was this?", as opposed
        to "what does this instant look like?".
        """
        windows = self.predict(frame, **kwargs)
        proba_cols = [f"p_{name}" for name in self.classes]
        per_event = windows.groupby(GROUP_COL, sort=False)[proba_cols].mean()

        best = per_event.to_numpy().argmax(axis=1)
        confidence = per_event.to_numpy().max(axis=1)
        labels = [self.classes[i] for i in best]
        if kwargs.get("gate"):
            labels = [ABSTAIN_LABEL if c < self.config["gate_threshold"] else name
                      for name, c in zip(labels, confidence)]
        return pd.DataFrame({
            GROUP_COL: per_event.index,
            "predicted_class": labels,
            "confidence": confidence,
            "n_windows": windows.groupby(GROUP_COL, sort=False).size().to_numpy(),
        }).reset_index(drop=True)
