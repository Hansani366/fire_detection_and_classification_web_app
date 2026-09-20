# Your own recordings go here

This folder is bind-mounted read-only into `ablation-service` at `/data`. Everything inside it except
this file is git-ignored, because a single recording is usually thousands of image files.

**Why a bind mount and not an upload.** nginx caps request bodies at 10 MB, and posting a recording
frame by frame would be thousands of requests. Putting the files on disk also means a run can be
repeated later against exactly the same input, which is what makes a published number reproducible.

## Layout

One folder per experiment. The folder name is the experiment id.

```
ablation-data/
  EXP_LAB_0001/
    meta.json
    sensors.csv
    frames/
      000001.jpg
      000002.jpg
      ...
  EXP_LAB_0002/
    ...
```

Frame filenames must be zero-padded so that sorting them alphabetically gives the right time order.

## `meta.json`

```json
{
  "experiment_id": "EXP_LAB_0001",
  "label": "liquid_fuel",
  "started_at": "2026-05-04T14:02:11Z",
  "frame_rate_hz": 16.0,
  "ignition_offset_s": 42.0,
  "sensor_node_id": "node-a",
  "mq2_baseline": null,
  "mq7_baseline": null,
  "flame_dark_counts": 3900,
  "flame_bright_counts": 400,
  "baseline_seconds": 30,
  "notes": ""
}
```

| field | meaning |
|---|---|
| `label` | one of `no_fire`, `gas_fire`, `liquid_fuel`, `solid_combustible` — the ground truth |
| `frame_rate_hz` | the real capture rate. **Below 12 Hz the flicker feature is refused** rather than measured, because sampling a ~2 Hz flame that slowly aliases it down to something that looks like "no flame at all" |
| `ignition_offset_s` | seconds from `started_at` to ignition; `null` for a `no_fire` run. Windows *before* this count as negatives, which is what makes false-alarm rate and detection latency mean anything |
| `mq2_baseline` / `mq7_baseline` | leave `null` to estimate from the first `baseline_seconds` of clean air (recommended). Give a number only if you calibrated the board yourself |
| `flame_dark_counts` / `flame_bright_counts` | the flame sensor's analog reading with no flame and with a flame. The module is inverted — **lower counts mean brighter** |

**Record at least `baseline_seconds` of quiet before ignition.** The models need a delta above a clean-air
baseline, and the baseline can only be measured from air that is actually clean.

## `sensors.csv`

One row per sensor sample, in time order. The column names match what `esp32-sensor-service` already
reports, so `GET /api/sensors/history?deviceId=...` output converts with almost no work.

```
t_iso,mq2_ppm,mq2_raw,mq7_ppm,mq7_raw,flame,flame_raw,temperature_c,humidity_pct
2026-05-04T14:02:11Z,120.5,247,18.2,149,0,3880,22.0,54.0
```

`mq2_raw` and `mq7_raw` are preferred over the ppm columns, because the models were trained on
ADC-shaped values. If you only have ppm, leave the raw columns empty and they will be reconstructed.

The sensor cadence does not need to match the frame rate — both are resampled onto a 1 Hz grid,
which is the rate the models were trained at.
