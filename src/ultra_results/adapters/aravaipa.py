"""Adapter for live.aravaiparunning.com -- Aravaipa Running's live-timing
platform. Structurally different from raceresult: this is raw timing-mat
crossing data (with redundant-reader duplicates to filter/dedupe), not a
pre-aggregated lap list. Checkpoints are explicit, named, and distanced,
unlike raceresult where we had to reverse-engineer loop distance.

Usage:
    python -m ultra_results.adapters.aravaipa <race_event_id>
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime, timezone

import httpx

from ultra_results.models import ParsedEvent, ParsedResult, ParsedSourceAthlete, ParsedSplit

BASE_URL = "https://live.aravaiparunning.com/api/v1/race_events/{event_id}"

HEADERS = {
    "accept": "application/json",
    "authorization": "bearer undefined",
    "referer": "https://live.aravaiparunning.com/",
    "x-live-ver": "200",
    "user-agent": "Mozilla/5.0 (compatible; ultra-results-db/0.1; +https://github.com/dannymiller688/ultra-results-db)",
}


def fetch_race_event(event_id: str) -> dict:
    resp = httpx.get(BASE_URL.format(event_id=event_id), params={"live": ""}, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def fetch_participant_crossings(event_id: str, participant_id: int) -> dict:
    url = f"{BASE_URL.format(event_id=event_id)}/participants/{participant_id}"
    resp = httpx.get(url, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def parse_event(payload: dict) -> tuple[ParsedEvent, dict]:
    """Returns (ParsedEvent, split_defs) where split_defs maps splitId ->
    (name, distance_m), used later to interpret crossings."""
    race = payload["races"][0]
    start = datetime.fromisoformat(race["startTime"].replace("Z", "+00:00"))
    cutoff = datetime.fromisoformat(race["cutoff"].replace("Z", "+00:00"))
    duration_s = int((cutoff - start).total_seconds())

    split_defs = {
        s["id"]: (s["name"], s["distance"])
        for s in race["splits"]
        if "id" in s  # skips the non-public "Roaming" entry, which has no id
    }

    event = ParsedEvent(
        event_date=start.date(),
        event_type="fixed_time",
        duration_s=duration_s,
        loop_distance_m=race["distance"],
        distance_raw=race["name"],
        name=race["name"],
    )
    return event, split_defs


def parse_results(payload: dict, loop_distance_m: float) -> list[ParsedResult]:
    results = []
    for p in payload["participants"]:
        full_name = f"{p['firstName']} {p['lastName']}"
        status = "dns" if p["status"] == 1 else "finished"  # inferred mapping, see adapter docstring

        athlete = ParsedSourceAthlete(
            source_athlete_key=str(p["id"]),
            name_raw=full_name,
            name_norm=_normalize_name(full_name),
            year_of_birth=date.today().year - p["age"] if p.get("age") else None,
            sex=p.get("gender"),
            nationality=p.get("country"),
        )

        results.append(
            ParsedResult(
                source_record_id=p["bib"],
                athlete=athlete,
                status=status,
                distance_m=p["lapCount"] * loop_distance_m if p["lapCount"] else None,
                time_kind="official",
                overall_place=p.get("overallPlace"),
            )
        )
    return results


def parse_splits(crossings_payload: dict, split_defs: dict, race_start: datetime, loop_distance_m: float) -> list[ParsedSplit]:
    """Dedupes redundant-reader crossings (same splitId+loopId fired by
    multiple antennas within ~1s of each other) by keeping only the first
    valid crossing per (splitId, loopId). loopId is 0-indexed (loopId=0 is
    lap 1), confirmed against the live site's own display."""
    seen = set()
    splits = []
    seq = 0
    for c in sorted(crossings_payload["crossings"], key=lambda x: x["timestamp"]):
        if not c["validCrossing"] or c["splitId"] is None:
            continue
        key = (c["splitId"], c["loopId"])
        if key in seen:
            continue
        seen.add(key)

        if c["splitId"] not in split_defs:
            continue  # unknown checkpoint, skip rather than guess

        name, within_lap_distance_m = split_defs[c["splitId"]]
        ts = datetime.fromisoformat(c["timestamp"].replace("Z", "+00:00"))
        elapsed_s = int((ts - race_start).total_seconds())
        if elapsed_s < 0:
            continue  # pre-race noise (e.g. mat test crossings before gun)

        cum_distance_m = c["loopId"] * loop_distance_m + within_lap_distance_m

        seq += 1
        splits.append(
            ParsedSplit(
                result_source_record_id="",  # filled in by caller, which knows the bib
                seq=seq,
                checkpoint_name=f"Lap {c['loopId'] + 1} - {name}",
                cum_distance_m=cum_distance_m,
                elapsed_s=elapsed_s,
                is_partial=False,
            )
        )
    return splits


if __name__ == "__main__":
    event_id = sys.argv[1]
    payload = fetch_race_event(event_id)
    event, split_defs = parse_event(payload)
    results = parse_results(payload, event.loop_distance_m)
    print(f"Parsed event: {event}")
    print(f"Split checkpoints: {split_defs}")
    print(f"Parsed {len(results)} results")

    # Smoke test splits parsing against the first result with a real lap count
    race_start = datetime.fromisoformat(payload["races"][0]["startTime"].replace("Z", "+00:00"))
    sample = next(r for r in results if r.status == "finished")
    crossings_payload = fetch_participant_crossings(event_id, int(sample.athlete.source_athlete_key))
    splits = parse_splits(crossings_payload, split_defs, race_start, event.loop_distance_m)
    print(f"\nParsed {len(splits)} splits for {sample.athlete.name_raw}")
    for s in splits[:4]:
        print(s)
    print("...")
    for s in splits[-2:]:
        print(s)