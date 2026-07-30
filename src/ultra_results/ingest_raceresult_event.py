"""Ingest ALL divisions/contests of a raceresult fixed-time event -- e.g. a
race with simultaneous 6hr/12hr/24hr divisions, each modeled as its own
core.events row under the same race.

Usage:
    python -m ultra_results.ingest_raceresult_event <event_id> <key> \\
        <race_name> <event_date YYYY-MM-DD> <loop_distance_m>
"""
import sys
from datetime import date, datetime

from ultra_results.adapters.raceresult import (
    fetch_lap_details,
    fetch_overall_results,
    parse_contest_duration_hours,
    parse_event_metadata,
    parse_results,
    parse_splits,
)
from ultra_results.loader import (
    finish_ingest_run,
    get_conn,
    get_or_create_event,
    get_or_create_race,
    get_or_create_source,
    start_ingest_run,
    upsert_result,
    upsert_source_athlete,
    upsert_splits,
)


def main(event_id: str, key: str, race_name: str, event_date: date, loop_distance_m: float):
    conn = get_conn()

    source_id = get_or_create_source(conn, "raceresult", "scrape", "https://my.raceresult.com")
    race_id = get_or_create_race(conn, race_name, country="USA")

    payload = fetch_overall_results(event_id, key)
    contest_keys = list(payload["data"].keys())
    print(f"Found {len(contest_keys)} division(s): {contest_keys}")

    grand_total_results = 0
    grand_total_splits = 0

    for contest_key in contest_keys:
        duration_hours = parse_contest_duration_hours(contest_key)
        duration_s = duration_hours * 3600
        print(f"\n--- {contest_key} ({duration_hours}hr) ---")

        ingest_run_id = start_ingest_run(conn, source_id, adapter_version="0.3.0")
        conn.commit()

        event = parse_event_metadata(
            event_date=event_date,
            duration_s=duration_s,
            loop_distance_m=loop_distance_m,
            event_name=f"{duration_hours} Hour",
        )
        event_id_db = get_or_create_event(conn, race_id, event)
        conn.commit()

        results = parse_results(payload, contest_key)
        total_splits = 0
        for result in results:
            source_athlete_id = upsert_source_athlete(conn, source_id, result)
            result_id = upsert_result(conn, event_id_db, source_athlete_id, ingest_run_id, result)
            conn.commit()

            if result.status != "finished" and result.overall_place is None:
                # DNS entrants have no laps to fetch
                print(f"  {result.athlete.name_raw}: {result.status}, no splits")
                continue

            splits_payload = fetch_lap_details(event_id, key, result.athlete.source_athlete_key)
            splits = parse_splits(splits_payload, result.source_record_id, loop_distance_m)
            upsert_splits(conn, result_id, splits)
            conn.commit()
            total_splits += len(splits)
            print(f"  {result.athlete.name_raw}: {len(splits)} splits loaded")

        finish_ingest_run(conn, ingest_run_id, records_ingested=len(results))
        conn.commit()

        grand_total_results += len(results)
        grand_total_splits += total_splits

    conn.close()
    print(f"\nDone. {grand_total_results} results, {grand_total_splits} total splits across {len(contest_keys)} divisions.")


if __name__ == "__main__":
    event_id, key, race_name, event_date_str, loop_distance_str = sys.argv[1:6]
    main(
        event_id=event_id,
        key=key,
        race_name=race_name,
        event_date=datetime.strptime(event_date_str, "%Y-%m-%d").date(),
        loop_distance_m=float(loop_distance_str),
    )