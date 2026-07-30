# ADR 0004: raw -> core -> marts, we never skip a layer

## Status
Accepted

## Context
Sources are messy and we WILL find parsing bugs after the fact. If we parse
straight from the API response into our nice clean tables, finding a bug
later means re-hitting the source again (maybe it's gone, rate-limited,
or changed) just to fix a typo in our parsing logic.

## Decision
Three layers, always in this order:
- `raw` = literally what the source gave us, untouched, as JSON blobs
- `core` = normalized, typed, our actual schema (events/results/splits/etc)
- `marts` = denormalized views built on core, for fast/easy querying (dbt)

Nothing writes into `marts` from `raw` directly. Nothing skips `core`.

## Consequences
- Found a parsing bug 3 months in? Fix the parser, replay from `raw`, done.
  Don't need the source to still be up or reachable.
- Slightly more upfront table-plumbing than "just parse it into the final
  shape," but it's the difference between "re-run a script" and "re-scrape
  the internet" when something goes wrong.
- `marts` layer doesn't exist yet (that's M5-ish, via dbt) but the folder's
  already there waiting.
