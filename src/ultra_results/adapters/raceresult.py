"""Adapter for my.raceresult.com. Handles both the Overall Results list and
per-runner Lap Details (splits).

Usage:
    python -m ultra_results.adapters.raceresult <event_id> <key>
"""
from __future__ import annotations

import re
import sys
from datetime import date

import httpx

from ultra_results.models import ParsedEvent, ParsedRace, ParsedResult, ParsedSourceAthlete, ParsedSplit

RESULTS_URL = "https://my-us-1.raceresult.com/{event_id}/results/list"
DETAILS_URL = "https://my-us-1.raceresult.com/{event_id}/details1/list"

HEADERS = {
    "accept": "*/*",
    "origin": "https://my.raceresult.com",
    "referer": "https://my.raceresult.com/",
    "user-agent": "Mozilla/5.0 (compatible; ultra-results-db/0.1; +https://github.com/dannymiller688/ultra-results-db)",
}


def fetch_overall_results(event_id: str, key: str, contest: str = "0") -> dict:
    params = {
        "key": key,
        "listname": "Result Lists|Overall Results",
        "page": "results",
        "contest": contest,
        "r": "all",
        "l": "0",
        "fav": "",
        "openedGroups": "{}",
        "term": "",
    }
    resp = httpx.get(RESULTS_URL.format(event_id=event_id), params=params, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def fetch_lap_details(event_id: str, key: str, pid: str) -> dict:
    params = {
        "key": key,
        "fav": "",
        "listname": "Online|Lap Details",
        "page": "details1",
        "r": "pid",
        "pid": pid,
    }
    resp = httpx.get(DETAILS_URL.format(event_id=event_id), params=params, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _parse_time_to_seconds(time_str: str) -> int | None:
    """'24:00:00' or '18:25:58' or '1:00:29.2' -> whole seconds. None for '-'/blank."""
    if not time_str or time_str.strip() in ("-", ""):
        return None
    time_str = time_str.strip()
    if "." in time_str:
        main, frac = time_str.rsplit(".", 1)
    else:
        main, frac = time_str, "0"
    parts = [int(p) for p in main.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts[-3:]
    total = h * 3600 + m * 60 + s
    return total


def _normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def parse_event_metadata(
    event_date: date,
    duration_s: int,
    loop_distance_m: float,
    event_name: str = "24 Hour",
) -> ParsedEvent:
    """Event metadata is not reliably derivable from the results/lap payloads
    alone (no course-length or event-duration field in either). For now this
    is supplied by the caller, sourced by a human checking the race's own
    website/results page. A future improvement would hit raceresult's
    Settings API to pull this programmatically -- see ADR 0005."""
    return ParsedEvent(
        event_date=event_date,
        event_type="fixed_time",
        duration_s=duration_s,
        loop_distance_m=loop_distance_m,
        distance_raw=event_name,
        name=event_name,
    )


def parse_results(payload: dict, contest_key: str) -> list[ParsedResult]:
    fields = payload["DataFields"]
    rows = payload["data"][contest_key]
    idx = {name: i for i, name in enumerate(fields)}

    results = []
    for row in rows:
        bib = row[idx["BIB"]]
        rr_id = row[idx["ID"]]
        display_name = row[idx["DisplayName"]]
        age_raw = row[idx["AGE"]]
        gender = row[idx["GenderMF"]]
        km = row[idx["KM"]]
        time_str = row[idx["TIME"]]
        done_flag = row[idx['if([Done]=1;"Done";" ")']]
        place_raw = row[idx['WithStatus([OverallRank.p])']]

        year_of_birth = None
        if age_raw and age_raw.strip().isdigit():
            year_of_birth = date.today().year - int(age_raw)

        status = "finished" if done_flag.strip() == "Done" else "in_progress"

        place = None
        if place_raw:
            digits = place_raw.strip().rstrip(".")
            if digits.isdigit():
                place = int(digits)

        athlete = ParsedSourceAthlete(
            source_athlete_key=rr_id,
            name_raw=display_name,
            name_norm=_normalize_name(display_name),
            year_of_birth=year_of_birth,
            sex=gender.strip() if gender else None,
        )

        results.append(
            ParsedResult(
                source_record_id=bib,
                athlete=athlete,
                status=status,
                time_s=_parse_time_to_seconds(time_str),
                distance_m=float(km) * 1000.0 if km else None,
                time_kind="official",
                overall_place=place,
            )
        )
    return results


def parse_splits(payload: dict, bib: str, loop_distance_m: float) -> list[ParsedSplit]:
    """payload['data'] is a flat list of [BIB, ID, lapNum, cumTimeStr, lapTimeStr]."""
    rows = payload["data"]
    splits = []
    for row in rows:
        _bib, _id, lap_num, cum_time_str, _lap_time_str = row
        seq = int(lap_num)
        elapsed_s = _parse_time_to_seconds(cum_time_str)
        splits.append(
            ParsedSplit(
                result_source_record_id=bib,
                seq=seq,
                checkpoint_name=f"Lap {seq}",
                cum_distance_m=seq * loop_distance_m,
                elapsed_s=elapsed_s,
                is_partial=False,
            )
        )
    return splits


if __name__ == "__main__":
    event_id, key = sys.argv[1], sys.argv[2]
    payload = fetch_overall_results(event_id, key)
    contest_key = next(iter(payload["data"].keys()))
    event = parse_event_metadata(
        event_date=date(2022, 12, 10),
        duration_s=24 * 3600,
        loop_distance_m=400.4,
    )
    results = parse_results(payload, contest_key)
    print(f"Parsed event: {event}")
    print(f"Parsed {len(results)} results")

    winner = results[0]
    loop_distance_m = 400.4  # derived from Marisa Lizak: 252281m / 630 laps
    splits_payload = fetch_lap_details(event_id, key, winner.athlete.source_athlete_key)
    splits = parse_splits(splits_payload, winner.source_record_id, loop_distance_m)
    print(f"Parsed {len(splits)} splits for {winner.athlete.name_raw}")
    print(splits[0])
    print(splits[-1])