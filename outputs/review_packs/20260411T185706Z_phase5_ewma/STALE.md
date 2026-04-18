## Stale Artifact

This Phase 5 review pack was generated before the day-aware timestamp
repair for combined multi-day review artifacts.

Do not use this pack's timestamp drilldowns as the authoritative Phase 5
record. The corrected regenerated challenger pack is:

- `outputs/review_packs/20260411T222629Z_phase5_ewma/`

The corrected paired incumbent pack is:

- `outputs/review_packs/20260411T222602Z_phase5_weighted/`

In particular, the old `timestamp_TOMATOES_141800` drilldown can mix
`day_-2` and `day_-1` context because both tutorial days reuse the same
raw timestamp axis.
