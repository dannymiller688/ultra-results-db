"""Source-agnostic loader. Takes parsed models (from any adapter) and
upserts them into core.* tables. Adapters never touch the DB directly --
this is the only place that does.
"""
from __future__ import annotations

import os
import uuid
from datetime import date

import psycopg
from dotenv import load_dotenv

from ultra_results.models import ParsedEvent, ParsedResult, ParsedSplit

load_dotenv()


def get_conn():
    return psycopg.connect(os.environ["DATABASE_URL"])


def get_or_create_source(conn, name: str, access_method: str, base_url: str | None = None) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM core.sources WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO core.sources (name, base_url, access_method) VALUES (%s, %s, %s) RETURNING id",
            (name, base_url, access_method),
        )
        return cur.fetchone()[0]


def start_ingest_run(conn, source_id: int, adapter_version: str) -> uuid.UUID:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO core.ingest_runs (source_id, adapter_version) VALUES (%s, %s) RETURNING id",
            (source_id, adapter_version),
        )
        return cur.fetchone()[0]


def finish_ingest_run(conn, ingest_run_id: uuid.UUID, records_ingested: int, status: str = "success"):
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE core.ingest_runs
               SET finished_at = now(), records_ingested = %s, status = %s
               WHERE id = %s""",
            (records_ingested, status, ingest_run_id),
        )


def get_or_create_race(conn, name: str, country: str | None = None) -> uuid.UUID:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM core.races WHERE name = %s", (name,))
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            "INSERT INTO core.races (name, country) VALUES (%s, %s) RETURNING id",
            (name, country),
        )
        return cur.fetchone()[0]


def get_or_create_event(conn, race_id: uuid.UUID, event: ParsedEvent) -> uuid.UUID:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id FROM core.events
               WHERE race_id = %s AND event_date = %s AND event_type = %s
               AND distance_m IS NOT DISTINCT FROM %s
               AND duration_s IS NOT DISTINCT FROM %s""",
            (race_id, event.event_date, event.event_type, event.distance_m, event.duration_s),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            """INSERT INTO core.events
               (race_id, event_date, event_type, distance_m, duration_s, loop_distance_m, distance_raw, name)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (
                race_id, event.event_date, event.event_type, event.distance_m,
                event.duration_s, event.loop_distance_m, event.distance_raw, event.name,
            ),
        )
        return cur.fetchone()[0]


def upsert_source_athlete(conn, source_id: int, result: ParsedResult) -> uuid.UUID:
    a = result.athlete
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM core.source_athletes WHERE source_id = %s AND source_athlete_key = %s",
            (source_id, a.source_athlete_key),
        )
        row = cur.fetchone()
        if row:
            return row[0]
        cur.execute(
            """INSERT INTO core.source_athletes
               (source_id, source_athlete_key, name_raw, name_norm, year_of_birth, sex, nationality)
               VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (source_id, a.source_athlete_key, a.name_raw, a.name_norm, a.year_of_birth, a.sex, a.nationality),
        )
        return cur.fetchone()[0]


def upsert_result(conn, event_id: uuid.UUID, source_athlete_id: uuid.UUID, ingest_run_id: uuid.UUID, result: ParsedResult) -> uuid.UUID:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO core.results
               (event_id, source_athlete_id, ingest_run_id, status, time_s, distance_m, time_kind, overall_place, source_record_id)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (event_id, source_athlete_id) DO UPDATE SET
                   status = EXCLUDED.status,
                   time_s = EXCLUDED.time_s,
                   distance_m = EXCLUDED.distance_m,
                   time_kind = EXCLUDED.time_kind,
                   overall_place = EXCLUDED.overall_place,
                   ingest_run_id = EXCLUDED.ingest_run_id
               RETURNING id""",
            (
                event_id, source_athlete_id, ingest_run_id, result.status, result.time_s,
                result.distance_m, result.time_kind, result.overall_place, result.source_record_id,
            ),
        )
        return cur.fetchone()[0]


def upsert_splits(conn, result_id: uuid.UUID, splits: list[ParsedSplit]):
    with conn.cursor() as cur:
        for s in splits:
            cur.execute(
                """INSERT INTO core.splits (result_id, seq, checkpoint_name, cum_distance_m, elapsed_s, is_partial)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (result_id, seq) DO UPDATE SET
                       cum_distance_m = EXCLUDED.cum_distance_m,
                       elapsed_s = EXCLUDED.elapsed_s,
                       is_partial = EXCLUDED.is_partial""",
                (result_id, s.seq, s.checkpoint_name, s.cum_distance_m, s.elapsed_s, s.is_partial),
            )