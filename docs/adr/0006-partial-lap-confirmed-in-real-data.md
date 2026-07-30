# ADR 0006: the partial-final-lap case (ADR 0001) showed up immediately, as predicted

## Status
Accepted (confirms ADR 0001)

## Context
ADR 0001 predicted that for fixed-time events, a runner's official credited
distance would exceed the max cumulative distance recorded in splits, because
of a measured partial final lap after the last full crossing. This was
designed before we had any real data to check it against.

First real ingest (Desert Solstice 2022, Marisa Lizak): her last full lap
(#630) crossed at elapsed_s=86331 with cum_distance_m=252252.0. Her official
result: time_s=86400, distance_m=252281.0. That's 69 more seconds and ~29
more meters than her last recorded split -- exactly the partial-lap gap the
schema was built to expect.

## Decision
No schema change needed. This is confirmation the ADR 0001 design was
correct, not a bug to fix. Recording it here as evidence for future readers
(including future us) that the "results != max(splits)" behavior is
observed, not theoretical.

## Consequences
- Any dbt test or validation logic must NOT assert
  results.distance_m == MAX(splits.cum_distance_m) for fixed_time events --
  this is now backed by a concrete real-world example, not just a hypothesis.
- We do not currently model the partial lap itself as its own split row
  (e.g. seq=631, is_partial=true) for Desert Solstice -- raceresult's Lap
  Details list doesn't expose it, only full lap crossings. This is a
  limitation of the source, not our schema. Worth revisiting if a future
  source does expose partial-lap measurements directly.
