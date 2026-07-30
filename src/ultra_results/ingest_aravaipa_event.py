"""Ingest an Aravaipa live-timing event end to end: results + splits for
every non-DNS participant.

Usage:
    python -m ultra_results.ingest_aravaipa_event <race_event_id> <race_name>
"""
import sys
from datetime import datetime

from ultra_results.adapters.aravaipa import (
    fetch_participant_crossings,
    fetch_race_event,
    parse_event,
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


def main(race_event_id: str, race_name: str):
    conn = get_conn()

    source_id = get_or_create_source(conn, "aravaipa_live", "scrape", "https://live.aravaiparunning.com")
    race_id = get_or_create_race(conn, race_name, country="USA")

    payload = fetch_race_event(race_event_id)
    event, split_defs = parse_event(payload)
    race_start = datetime.fromisoformat(payload["races"][0]["startTime"].replace("Z", "+00:00"))

    ingest_run_id = start_ingest_run(conn, source_id, adapter_version="0.1.0")
    conn.commit()

    event_id_db = get_or_create_event(conn, race_id, event)
    conn.commit()

    results = parse_results(payload, event.loop_distance_m)
    total_splits = 0
    for result in results:
        source_athlete_id = upsert_source_athlete(conn, source_id, result)
        result_id = upsert_result(conn, event_id_db, source_athlete_id, ingest_run_id, result)
        conn.commit()

        if result.status == "dns":
            print(f"  {result.athlete.name_raw}: dns, no splits")
            continue

        crossings_payload = fetch_participant_crossings(race_event_id, int(result.athlete.source_athlete_key))
        splits = parse_splits(crossings_payload, split_defs, race_start, event.loop_distance_m)
        for s in splits:
            s.result_source_record_id = result.source_record_id
        upsert_splits(conn, result_id, splits)
        conn.commit()
        total_splits += len(splits)
        print(f"  {result.athlete.name_raw}: {len(splits)} splits loaded")

    finish_ingest_run(conn, ingest_run_id, records_ingested=len(results))
    conn.commit()
    conn.close()

    print(f"\nDone. {len(results)} results, {total_splits} total splits.")


if __name__ == "__main__":
    race_event_id, race_name = sys.argv[1], sys.argv[2]
    main(race_event_id, race_name)