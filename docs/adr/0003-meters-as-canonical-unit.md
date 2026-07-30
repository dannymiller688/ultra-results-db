# ADR 0003: everything is stored in meters (and seconds), no exceptions

## Status
Accepted

## Context
Sources say "50 miles," "52.4mi," "84.5 km," "26.2," whatever they feel like.
If we store distance as whatever string/unit the source used, every query
that compares distances across sources turns into a unit-conversion
nightmare, forever, in every query, by everyone who touches this later.

## Decision
Every distance column is numeric meters. Every time column is numeric
seconds. Full stop. We ALSO keep the source's original raw text
(`distance_raw`) so nothing is lost, but it's just there for reference/
debugging, never used in comparisons or math.

## Consequences
- Adapters have to do the unit conversion once, at parse time, not us doing
  it 50 times later in random queries.
- "Fastest 50 mile" query is just a WHERE on a number, no CASE WHEN unit = 'mi'
  silliness.
- If a source's unit is ambiguous or we guess wrong, that bug lives in one
  place (the adapter's parser), not smeared across the whole codebase.
