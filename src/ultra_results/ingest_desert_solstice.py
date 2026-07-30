"""Ingest a raceresult fixed-time event end to end: results + splits for
every runner. One-off script; will get folded into a proper typer CLI once
we've proven it generalizes across a couple more events.

Usage:
    python -m ultra_results.ingest_desert_solstice <event_id> <key> \\
        <race_name> <event_date YYYY-MM-DD> <duration_hours> <loop_distance_m>
"""
import sys
from datetime import date, datetime

from ultra_results.adapters.raceresult import (
    fetch_lap_details,
    fetch_overall_results,
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


def main(
    event_id: str,
    key: str,
    race_name: str,
    event_date: date,
    duration_s: int,
    loop_distance_m: float,
):
    conn = get_conn()

    source_id = get_or_create_source(conn, "raceresult", "scrape", "https://my.raceresult.com")
    ingest_run_id = start_ingest_run(conn, source_id, adapter_version="0.2.0")
    conn.commit()

    payload = fetch_overall_results(event_id, key)
    contest_key = next(iter(payload["data"].keys()))
    event = parse_event_metadata(
        event_date=event_date,
        duration_s=duration_s,
        loop_distance_m=loop_distance_m,
    )
    results = parse_results(payload, contest_key)

    race_id = get_or_create_race(conn, race_name, country="USA")
    event_id_db = get_or_create_event(conn, race_id, event)
    conn.commit()

    total_splits = 0
    for result in results:
        source_athlete_id = upsert_source_athlete(conn, source_id, result)
        result_id = upsert_result(conn, event_id_db, source_athlete_id, ingest_run_id, result)
        conn.commit()

        splits_payload = fetch_lap_details(event_id, key, result.athlete.source_athlete_key)
        splits = parse_splits(splits_payload, result.source_record_id, loop_distance_m)
        upsert_splits(conn, result_id, splits)
        conn.commit()
        total_splits += len(splits)
        print(f"  {result.athlete.name_raw}: {len(splits)} splits loaded")

    finish_ingest_run(conn, ingest_run_id, records_ingested=len(results))
    conn.commit()
    conn.close()

    print(f"\nDone. {len(results)} results, {total_splits} total splits.")


if __name__ == "__main__":
    event_id, key, race_name, event_date_str, duration_hours_str, loop_distance_str = sys.argv[1:7]
    main(
        event_id=event_id,
        key=key,
        race_name=race_name,
        event_date=datetime.strptime(event_date_str, "%Y-%m-%d").date(),
        duration_s=int(float(duration_hours_str) * 3600),
        loop_distance_m=float(loop_distance_str),
    )