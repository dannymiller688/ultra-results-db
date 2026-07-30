# ADR 0002: runner_id is nullable and we never merge/delete source_athletes

## Status
Accepted

## Context
Same human shows up under different names/spellings across sources (or even
within one source over years). We eventually want to say "these 3 rows across
2 sources are actually the same person." But matching people is messy and
we WILL get it wrong sometimes.

## Decision
Every source's version of a person lives forever in `source_athletes`,
untouched. There's a `runner_id` column that starts out NULL and gets filled
in later by whatever matching process we build (M4). `core.runners` is the
"real person" table that source_athletes point at.

## Consequences
- Bad match? Just UPDATE the runner_id back to NULL or to the right one. No
  data loss, no "oops we deleted the wrong row."
- We can literally re-run the whole matching process from scratch whenever
  we want, since nothing gets destroyed the first time around.
- Until M4 actually runs, runner_id is just NULL everywhere and that's fine.
