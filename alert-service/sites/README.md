# Site files

One JSON file per facility. `SITE_KEY` picks which one the service loads
(`home` by default); `sites.py` validates it at import and **raises** if it does
not hold together, so a broken file stops the container at start-up with the
reason in `docker compose logs alert-service` rather than during a fire.

| Key | What it is | Footprint | Hazard radius |
|---|---|---|---|
| `unit7` | The demonstration facility. A fictional garment unit, transcribed from the mobile app's original drawing. | 36.0 × 34.8 m | 6.0 m |
| `home` | The real trial facility (Section 3.3.7), traced from `home_layout.png`. | 13.28 × 9.68 m | 2.0 m |

## Coordinates are in metres

The methodology weights edges by *physical length* and blocks a hazard *radius*.
In abstract drawing units "radius = 60" cannot be checked against anything, and
the optimality gap against a hand-measured route has no denominator. So nodes
carry `x`/`y` in metres and `render.pxPerM` converts to the phone's drawing space
once, at load.

## The mirror contract

The backend owns the graph. **The phone owns the artwork** — rooms, doors, exit
bars and labels are const data in
`../../../fire_notification_and_evacuation_mobile_app/lib/shared/floor_plan/floor_plan_data.dart`,
because a generic renderer fed server geometry looks like a wireframe and that
screen is read under time pressure.

The two sides must agree on exactly two things:

1. **Exit ids.** A server-blocked exit finds its bar on the drawing by id. Rename
   one here and it will silently draw as open.
2. **The coordinate space.** `render.designW × designH` at `pxPerM` must describe
   the same building as the Dart `designSize`. A mismatch draws a perfectly
   correct route through the walls of a different building.

`revision` is the third thing to keep in step, and it is not cosmetic: stored
routes record it, and the route analysis refuses to score a route against a plan
revision it was not generated under.

The Flutter test `test/route_test.dart` checks all of this across both repos and
skips only if this repo is not checked out beside it.

## Editing a site

- Add or move a node/edge → bump `revision`.
- `wM` on an edge is optional; it defaults to the straight-line distance. State
  it explicitly when a segment is honestly longer to walk than it looks (a
  doorway you pass through single-file). A `wM` *shorter* than the straight line
  is rejected — that is a typo, and a typo there quietly shortens a route the
  system then calls optimal.
- `zoneAnchors` needs one entry per zone: the node an occupant of that zone is
  routed from, and the point within it where a fire is modelled.
- `groundTruth` is the hand-derived answer, **written before running the
  system**. It is checked by `test_routing.py` and used by
  `GET /api/analysis/routes`. When the code and the ground truth disagree, work
  out which is right by hand — do not simply adopt whatever the code produced.
- Geometry never goes in the database. The SQLite file lives in a volume that
  survives `compose down`, so config stored there silently ignores your edits.

## Switching sites

```bash
docker compose up -d --force-recreate alert-service   # env is read at start
```

A plain `restart` keeps the old value. Switching against an existing
`alert-data` volume is handled: `init_db` updates the zones that survive
(preserving their status) and deletes the ones that do not.
