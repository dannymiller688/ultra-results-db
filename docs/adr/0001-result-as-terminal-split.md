# ADR 0001: Results are a denormalized terminal split, not an independent fact

## Status
Accepted

## Context
A finish is conceptually just the last checkpoint crossing in a race — the same
kind of observation (cumulative distance, cumulative time) as every split before
it. Modeling `results` as a fully separate table from `splits` risks the two
silently disagreeing, or duplicating logic for "what was the final time/distance."

But for fixed-time events (e.g. 24-hour races), the credited final distance
often includes a *measured partial final lap* — the distance covered between
the last full loop crossing and the moment the clock expires. This is not a
mat/timing-mat crossing at all; it's a manual or GPS-based measurement. DNF,
DNS, DQ, and official-vs-unofficial status are also facts about the *entrant*,
not about any single split.

## Decision
`core.results` is a denormalized cache of the terminal split, plus status
metadata that has no natural home on a split row. `core.splits` still holds
every individual checkpoint crossing, including a flagged partial final lap
(`is_partial`) where applicable.

`results.distance_m` is intentionally allowed to exceed
`MAX(splits.cum_distance_m)` for a given result in fixed-time events. This is
expected behavior, not a data quality bug, and must not be "fixed" by a
validation rule that assumes the two should be equal.

## Consequences
- Fast queries ("fastest 50-mile this year") hit `results` directly without
  aggregating over `splits`.
- Any code or dbt test asserting `results.distance_m == MAX(splits.cum_distance_m)`
  is wrong for fixed-time events and must scope that assertion to
  `event_type = 'fixed_distance'` only.
- Adapters must be able to represent a partial final lap distinctly from a
  full completed lap (`splits.is_partial`), which adds a small amount of
  parsing complexity per source but avoids silent distance corruption.
