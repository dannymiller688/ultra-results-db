# ADR 0007: result status is derived from Place, not a done-flag field

## Status
Accepted

## Context
Desert Solstice's results list had a done-flag column expression of
`if([Done]=1;"Done";" ")`. Perpetual Motion Ultras' equivalent column was
`iif([Chip]=1;"DONE";" ")` -- different expression string, different value
casing. Since raceresult lets each event organizer configure their own list
layout, hardcoding a lookup on the literal expression string is fragile and
broke immediately on the second differently-configured event we tried.

Perpetual Motion also gave us our first real DNS entrants (no laps, no KM,
no time, Place="DNS") -- a case Desert Solstice never exercised.

## Decision
Derive `status` from the Place field instead: "DNS" -> dns, "DNF" -> dnf,
"DQ" -> dq, anything else (a numeric rank) -> finished. Place's possible
values are a small, stable, well-known set across raceresult events, unlike
arbitrary per-event column expressions.

## Consequences
- The adapter no longer depends on knowing an event's exact done-flag
  column expression ahead of time.
- Splits are only fetched for entrants with an actual result (skipped for
  DNS), avoiding a wasted/likely-empty API call per non-starter.
- If a future source expresses "DNF"/"DQ" differently (a different word,
  a numeric code), this same brittleness could recur -- worth watching for
  on the next new source, not just the next raceresult event.
