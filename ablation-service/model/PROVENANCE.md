# Vendored model artifacts — do not edit

These four files are **copies**. They are vendored rather than bind-mounted so that
`docker compose build` works from this repository alone, and so that a published result can be
traced to exact bytes.

## Source

Sibling repository, at the same level as this one:

```
../fire_classification_model/trained_model_v3/
    model/fusion_model.joblib
    model/sensor_model.joblib
    model/manifest.json
    fire_classifier.py          -> vendored one level up, at ablation-service/
```

| field | value |
|---|---|
| training `run_id` | `20260920T122953Z` |
| selected model | `mlp/fusion_stacked` |
| dataset | `fire_multimodal_v3.csv`, 86,400 rows, 480 experiments |
| data source | `cfast_v3` — **synthetic simulation, not recorded fire** |

## Checksums

```
b43cfd2fe701db791c0da81b4379b08115a17bcf5e231ddd93e4dfc1991211aa  fusion_model.joblib
ab58434114d3aa1deb649cfa2e3a2131a4915aa5929e249699b2721abfdaea06  sensor_model.joblib
1b0ca5f33ae0b3e650068df23fc06f4ef721532a07fe6093f551fd8b8ab0b1e0  manifest.json
```

Verify with `shasum -a 256 model/*.joblib model/manifest.json`. `/api/ablation/health` reports the
live checksums so a running container can be matched against a results export.

## What the two models are, and why both are needed

`fusion_model.joblib` reads **no raw sensor values at all**. Features 92–95 of its 96 are
`sensor_p_no_fire`, `sensor_p_gas_fire`, `sensor_p_liquid_fuel`, `sensor_p_solid_combustible` — the
`predict_proba` output of `sensor_model.joblib`. The chain is:

```
raw sensor channels -> sensor_model (XGBClassifier, 53 features) -> 4 probabilities
                                                                         |
      raw vision channels + temporal features ------------------------- + -> fusion_model
                                                    (Pipeline: StandardScaler -> MLP(128,64), 96 features)
```

So `sensor_model.joblib` is a required sub-model, not an alternative. `fire_classifier.py` splices
the probabilities in automatically (`needs_sensor_proba`).

## Re-vendoring

Copy all four files together and update the checksums above. They are a matched set: `manifest.json`
supplies every temporal constant the feature builder uses (`roll_windows`, `persistence_window`,
`smooth_window`, `gate_threshold`), so a mismatched manifest silently changes the features.

`fire_classifier.py` resolves `MODEL_DIR` relative to its own file, which is why it sits one level up
from this directory — beside `main.py`, with `model/` underneath it.
