# Fonts

The dashboard, the ablation page and the reports page load these two files
instead of fetching the same families from `fonts.googleapis.com`. The CDN made
the pages depend on the network to look right, which a submitted artefact
cannot: a trial laptop may have no internet, and a screenshot taken with the
fallback font does not match one taken with the real font.

| File | Family | Used for | Licence |
|---|---|---|---|
| `Inter.ttf` | Inter | body copy, `--body` | SIL Open Font License 1.1 |
| `PlusJakartaSans.ttf` | Plus Jakarta Sans | headings, labels, numerals, `--display` | SIL Open Font License 1.1 |

Both are variable fonts, so one file covers every weight the pages ask for. The
`@font-face` rules that declare the weight ranges are at the top of
`../css/tokens.css`.

These are the same two files the mobile app bundles in
`fire_notification_and_evacuation_mobile_app/assets/fonts/`. Replace both
copies together, or the phone and the dashboard stop matching.
