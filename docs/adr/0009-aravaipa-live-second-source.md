# ADR 0009: aravaipa_live as source #2, and its data-shape quirks

## Status
Accepted

## Context
Aravaipa Running runs its own live-timing platform (live.aravaiparunning.com),
structurally unrelated to raceresult -- different vendor, different auth
pattern, and critically, raw timing-mat crossing data instead of a
pre-aggregated lap list. This became our second source, and it happened to
land on Desert Solstice 2025, a third year of a race we already had two
years of via raceresult -- good setup for future cross-source entity
resolution, though we're not building that yet.

Several things this source does differently from raceresult:

1. `participants` is a top-level key on the race_events payload, NOT nested
   under `races[0]`. First adapter draft got this wrong (KeyError), fixed
   by reading `payload["participants"]` directly.

2. Checkpoints are explicit structured data (id, name, distance), not
   guessed. The race object gives `loop_distance_m` directly
   (`"distance": 400`) -- no reverse-engineering needed, unlike raceresult's
   winner-KM-divided-by-laps hack (ADR 0005).

3. Multiple checkpoints per lap: this race defines Start (0m), Half (200m),
   and Finish (400m), so splits here are finer-grained than raceresult's
   one-crossing-per-lap.

4. Raw crossings have REDUNDANT READS: the same physical mat crossing is
   often recorded multiple times by different `eventSourceId` antennas
   within under a second of each other, all at the same (splitId, loopId).
   Only `validCrossing: true` rows should count, and even among those,
   duplicates by (splitId, loopId) must be deduped -- we keep the first
   chronologically.

5. `loopId` is 0-indexed. Confirmed against the live site's own display:
   loopId=0 is "Lap 1". cum_distance_m = loopId * loop_distance_m +
   within_lap_distance.

6. Status semantics are undocumented. Only two values observed (0, 1);
   inferred 1 = DNS (matches a participant with lapCount=0), 0 = finished/
   active. This is a guess based on pattern, not a documented enum -- flag
   if a third status value ever appears.

7. The top-level payload includes `"renderedLive": true`, meaning this may
   be a mid-race snapshot rather than final results. Observed evidence: one
   participant's roster `lapCount` (368) was one lap behind their own
   crossings-derived max lap (369) -- consistent with the two payloads
   being fetched moments apart during a live race, not a data bug.

## Decision
Built as its own adapter module (aravaipa.py), not shoehorned into the
raceresult adapter, given the structural differences above. Splits are
derived entirely from the crossings endpoint; the roster's own lapCount is
used only for the results row's distance_m and is treated as slightly less
authoritative than the crossings-derived lap count when they disagree.

## Consequences
- We now have proof the core schema holds an event that spans two
  independently-built vendor APIs, which was the actual point of adding a
  second source (M3 goal).
- Cross-source entity resolution (M4) has real material now: Desert
  Solstice runners appear across raceresult (2021/2022) and aravaipa_live
  (2025) under different source_athlete records, same real people.
- If aravaipa exposes non-live (final/archived) results for past events,
  those may not have the "renderedLive" ambiguity -- worth checking before
  assuming all aravaipa ingests need the lapCount-vs-crossings caution.
