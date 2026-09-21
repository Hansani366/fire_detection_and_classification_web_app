"""
Thin client for fire-classification-service, which owns the trained models.

WHY THIS SERVICE NO LONGER LOADS THE MODELS. It used to hold its own copy of
`fusion_model.joblib` and `sensor_model.joblib`. Two copies means two sets of
pinned library versions, two chances to re-vendor only one of them, and a real
possibility of the research page and the live dashboard disagreeing about the
same fire. The weights now live in exactly one service and everything that
needs a verdict asks it.

WHAT STAYED HERE. The six combination rules, the metrics, the ground-truth
definitions and the temporal features the RULES need. Those are the research
question. The model is not: combinations 1 and 6 are the trained arms, and
their probabilities arrive from over there.

WHY THE RAW FRAME IS ENOUGH. Only combinations 1 and 6 need the model's 96
engineered features, and those are built inside the classification service. The
rule-based arms read raw channels and compute their own rolling statistics, so
nothing here has to reimplement `build_features` -- which is exactly the
duplication that would drift.
"""

from __future__ import annotations

import logging

import httpx
import numpy as np
import pandas as pd

log = logging.getLogger("ablation.classifier")

GROUP = "experiment_id"


class ClassifierUnavailable(RuntimeError):
    """The classification service could not be reached or refused the frame."""


class ClassifierClient:
    """Holds the remote model's identity plus the config it advertises."""

    def __init__(self, base_url: str, health: dict):
        self.base_url = base_url.rstrip("/")
        self.health = health
        self.classes: list[str] = health["classes"]
        # The 27 raw channels the model needs, as the model's owner reports
        # them. Read rather than copied, so adding a channel to the model does
        # not silently leave this service sending the old set.
        self.channels: list[str] = health["required_channels"]
        # Served by the model's owner rather than copied, so the smoothing
        # window and persistence window here are always the ones the model was
        # trained with.
        self.config: dict = health["config"]
        self.manifest = {"config": self.config, "class_names": self.classes,
                         "run_id": health["manifest_run_id"],
                         "library_versions": health["lib_versions"]}

    @classmethod
    async def connect(cls, base_url: str, timeout: float = 30.0) -> "ClassifierClient":
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/classify/health")
            resp.raise_for_status()
            return cls(base_url, resp.json())

    async def score(self, frame: pd.DataFrame, timeout: float = 600.0) -> dict:
        """Raw observation rows -> fusion and sensor probabilities, aligned.

        The response carries `experiment_id` and `window_idx` because the
        service sorts by (experiment_id, timestamp) before scoring. Rows are
        realigned against that here rather than assuming the input order
        survived -- an off-by-one in the alignment would silently scramble
        every metric on the page.
        """
        # ONLY the channels the model reads, plus the two keys. Two reasons,
        # and the second one bites immediately: the evaluation-only columns
        # (fire_type, cfast_hrr_kw, ood_fuel) are none of the model's business,
        # and ood_fuel is empty on the test split, which pandas reads as NaN --
        # and NaN is not valid JSON, so the whole request fails to serialise.
        wanted = [c for c in self.channels if c in frame.columns]
        missing = [c for c in self.channels if c not in frame.columns]
        if missing:
            raise ClassifierUnavailable(
                f"frame is missing {len(missing)} model channel(s): {missing[:5]}")

        rows = frame[[GROUP, "timestamp", *wanted]].copy()
        rows["timestamp"] = pd.to_datetime(rows["timestamp"]).astype(str)

        # A NaN that survives into a real channel would be a silent wrong
        # answer rather than a serialisation error, so it is caught here.
        holes = [c for c in wanted if rows[c].isna().any()]
        if holes:
            raise ClassifierUnavailable(
                f"model channels contain missing values: {holes[:5]}. The "
                f"classifier cannot be given gaps — fix the source data.")

        payload = {"rows": rows.to_dict("records"), "smooth": False}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/api/classify/batch", json=payload)
        except httpx.HTTPError as exc:
            raise ClassifierUnavailable(
                f"fire-classification-service unreachable: {exc}") from exc
        if resp.status_code != 200:
            raise ClassifierUnavailable(
                f"fire-classification-service refused the frame "
                f"(HTTP {resp.status_code}): {resp.text[:300]}")

        out = resp.json()
        return {
            "classes": out["classes"],
            "fusion": np.asarray(out["fusion_proba"], dtype=float),
            "sensor": np.asarray(out["sensor_proba"], dtype=float),
            "order": pd.DataFrame({GROUP: out["experiment_id"],
                                   "window_idx": out["window_idx"]}),
        }


def sorted_like_service(frame: pd.DataFrame) -> pd.DataFrame:
    """Reproduce the ordering the classification service scores in.

    `build_features` sorts by (experiment_id, timestamp) and resets the index,
    then numbers windows with a per-experiment cumcount. Everything on this
    side -- the rules, the truth table, the exports -- must line up with that,
    so the sort happens once, here.
    """
    out = frame.sort_values([GROUP, "timestamp"]).reset_index(drop=True)
    out["window_idx"] = out.groupby(GROUP, sort=False).cumcount()
    return out
