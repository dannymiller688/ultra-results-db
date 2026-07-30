# ADR 0005: loop_distance_m is currently derived by hand, not parsed

## Status
Accepted (temporary, flagged for follow-up)

## Context
raceresult's per-event "Lap Details" list gives us lap number + cumulative
time, but NOT lap distance directly. For Desert Solstice we figured out
loop_distance_m = 400.4 by taking the winner's official credited distance
(252281m) and dividing by her lap count (630). That number is now
hardcoded as a constant in ingest_desert_solstice.py.

This only works because:
- the event is on a track (fixed, known loop length)
- we happened to have one runner's official distance to reverse-engineer from
- we manually ran the division ourselves and typed the result in

## Decision
Ship it hardcoded for event #1. Explicitly do NOT pretend this is a general
solution. Flag it here so it doesn't quietly become "how the adapter works."

## Consequences
- Adding event #2 will almost certainly break this assumption unless it's
  also a track race with the exact same loop length (unlikely).
- Before ingesting a second raceresult event, we need to either:
  (a) find loop distance in the event's Settings API instead of guessing, or
  (b) derive it per-event the same reverse-engineering way, but make it a
      parameter instead of a hardcoded constant.
- Non-track fixed-time races (out-and-back trails, etc.) won't have a
  single fixed loop_distance_m at all -- that's a bigger parsing problem,
  not just a hardcode-to-parameter fix.

## Update (after 2nd event ingested)
Validated against Desert Solstice 2021 (event 188236): derived loop_distance_m
by dividing the winner's official KM by his lap count (278.44km / 696 laps =
400.06m), same technique as event #1. Winner's split count matched exactly
(696), confirming the derived value was correct. This is now a repeatable
manual step per event, not a one-off guess -- still not automated, but no
longer "hopefully this generalizes," it's proven to generalize across two
independently-run track events.

Also: do NOT trust incidental metadata fields (e.g. a list config's
"LastChange" timestamp) as the event date. Confirmed a real bug this way --
188236's LastChange said 2020-12-11, but the actual race (per the page's own
"Race start time... Saturday, December 11, 2021" text) was 2021. Event date
must come from an explicit, human-confirmed source -- the race's own stated
date -- never inferred from adjacent metadata.
