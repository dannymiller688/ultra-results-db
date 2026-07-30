# ADR 0008: one raceresult event ID can contain multiple divisions/durations

## Status
Accepted

## Context
Perpetual Motion Ultras (event 374335) runs 6hr, 12hr, and 24hr divisions
simultaneously, all under one raceresult event ID, exposed as three keys in
the results payload's `data` object (`#1_6 Hour`, `#2_12 Hour`, `#3_24 Hour`).
Earlier adapter code only ever read `next(iter(payload["data"].keys()))`,
silently ignoring every division past the first.

## Decision
Loop over every key in `data`, creating one core.races row (shared) and one
core.events row per division/contest. Duration is parsed directly out of
the contest key text (e.g. "24 Hour") via regex, failing loudly if the
pattern doesn't match rather than guessing.

## Consequences
- One raceresult event_id can and often will map to N core.events rows,
  not 1:1. Any future code assuming "one event ID = one event row" is wrong.
- ingest_raceresult_event.py replaces the earlier one-off
  ingest_desert_solstice.py as the general entrypoint; the older script's
  single-contest assumption is now known-incomplete (it happened to work
  for Desert Solstice only because that event has exactly one division).
- Duration-from-contest-key-text is itself a small parsing assumption
  ("24 Hour" pattern) -- would break on a differently-worded division name.
  Acceptable for now, flagged for whenever a source names things unusually.
