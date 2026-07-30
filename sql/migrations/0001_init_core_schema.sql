-- 0001_init_core_schema.sql
-- Establishes the raw landing layer and the core normalized schema.
-- See docs/adr/ for the reasoning behind medallion layering, meters-as-canonical-unit,
-- nullable runner_id, and result-as-terminal-split.

BEGIN;

-- ============================================================
-- SCHEMAS
-- ============================================================
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;

-- ============================================================
-- ENUMS (core)
-- ============================================================
CREATE TYPE core.event_type AS ENUM ('fixed_distance', 'fixed_time', 'backyard', 'stage');
CREATE TYPE core.result_status AS ENUM ('finished', 'dnf', 'dns', 'dq', 'in_progress');
CREATE TYPE core.time_kind AS ENUM ('official', 'chip', 'gun', 'unofficial');
CREATE TYPE core.access_method AS ENUM ('api', 'scrape', 'manual');

-- ============================================================
-- RAW LAYER
-- One landing table per source. Payload is stored verbatim (JSONB)
-- so parsing bugs can be replayed without re-hitting the source.
-- ============================================================
CREATE TABLE raw.raceresult_payloads (
    id              BIGSERIAL PRIMARY KEY,
    ingest_run_id   UUID NOT NULL,
    source_event_id TEXT NOT NULL,       -- raceresult's numeric event ID, as text
    list_name       TEXT NOT NULL,       -- e.g. 'results', 'splits'
    payload         JSONB NOT NULL,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_raceresult_payloads_event ON raw.raceresult_payloads (source_event_id);
CREATE INDEX idx_raceresult_payloads_ingest_run ON raw.raceresult_payloads (ingest_run_id);

-- ============================================================
-- CORE LAYER
-- ============================================================

-- Registry of data sources.
CREATE TABLE core.sources (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,        -- 'raceresult', 'duv', 'runsignup'
    base_url        TEXT,
    access_method   core.access_method NOT NULL,
    notes           TEXT
);

-- One row per adapter execution. Everything downstream carries ingest_run_id
-- for lineage: which scraper/API pull produced this row, and when.
CREATE TABLE core.ingest_runs (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         INTEGER NOT NULL REFERENCES core.sources (id),
    adapter_version   TEXT NOT NULL,     -- git SHA or version tag of the adapter code
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at        TIMESTAMPTZ,
    records_ingested   INTEGER,
    status              TEXT NOT NULL DEFAULT 'running'  -- 'running' | 'success' | 'failed'
);

-- The recurring race (e.g. "Desert Solstice Invitational").
CREATE TABLE core.races (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    country     TEXT,
    region      TEXT,          -- state/province, informal
    surface     TEXT,          -- 'track', 'road', 'trail', etc.
    notes       TEXT
);

-- A dated instance of a race at a specific distance/format.
-- Both distance_m and duration_s are nullable and both can be populated --
-- a fixed-time event has duration_s set and distance_m null (the event's
-- *target*, not any single runner's result); a fixed-distance event is the
-- reverse. loop_distance_m is set whenever the event runs on a repeating loop,
-- which is common for both backyard ultras and many fixed-time track races.
CREATE TABLE core.events (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    race_id           UUID NOT NULL REFERENCES core.races (id),
    event_date        DATE NOT NULL,
    event_type        core.event_type NOT NULL,
    distance_m        NUMERIC,          -- target distance, if fixed_distance
    duration_s        INTEGER,          -- target duration, if fixed_time
    loop_distance_m   NUMERIC,          -- set if the course is a repeating loop
    distance_raw      TEXT,             -- source's original distance string, preserved verbatim
    name              TEXT,             -- e.g. "50 Mile", "24 Hour" -- source's own event label
    UNIQUE (race_id, event_date, event_type, distance_m, duration_s)
);

-- The per-source representation of a person. Never merged/deleted --
-- runner_id (nullable) is populated later by entity resolution (M4),
-- and is a plain UPDATE, fully reversible.
CREATE TABLE core.source_athletes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id       INTEGER NOT NULL REFERENCES core.sources (id),
    runner_id       UUID,                       -- FK added once core.runners exists, see below
    source_athlete_key TEXT,                    -- source's own athlete/rider ID, if any
    name_raw        TEXT NOT NULL,
    name_norm       TEXT NOT NULL,               -- lowercased, whitespace-collapsed, for matching
    year_of_birth   INTEGER,
    date_of_birth   DATE,
    sex             TEXT,
    nationality     TEXT,
    UNIQUE (source_id, source_athlete_key)
);

-- Canonical person identity, populated by entity resolution across source_athletes.
CREATE TABLE core.runners (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name    TEXT NOT NULL,
    year_of_birth   INTEGER,
    nationality     TEXT
);

ALTER TABLE core.source_athletes
    ADD CONSTRAINT fk_source_athletes_runner
    FOREIGN KEY (runner_id) REFERENCES core.runners (id);

-- A result is the terminal, denormalized "finish line" observation for one
-- entrant in one event, plus status facts that have no natural home on a
-- split (DNF, DQ, official vs unofficial). For fixed_time events, distance_m
-- here is the *credited* distance (which may include a measured partial final
-- lap) and will NOT generally equal the max cumulative distance recorded in
-- core.splits -- that is expected, not a data-quality bug. See ADR on
-- result-as-terminal-split.
CREATE TABLE core.results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id            UUID NOT NULL REFERENCES core.events (id),
    source_athlete_id   UUID NOT NULL REFERENCES core.source_athletes (id),
    ingest_run_id       UUID NOT NULL REFERENCES core.ingest_runs (id),
    status              core.result_status NOT NULL,
    time_s              INTEGER,           -- finish time in seconds, if applicable
    distance_m          NUMERIC,           -- credited distance, if applicable (fixed_time results)
    time_kind           core.time_kind,
    overall_place       INTEGER,
    source_record_id    TEXT,              -- source's own row/result ID, for idempotent upsert
    confidence          NUMERIC DEFAULT 1.0,
    UNIQUE (event_id, source_athlete_id)
);

CREATE INDEX idx_results_event ON core.results (event_id);
CREATE INDEX idx_results_source_athlete ON core.results (source_athlete_id);

-- A single checkpoint/lap crossing. is_partial marks the case (common in
-- fixed_time / looped events) where the final "crossing" is a measured
-- partial lap rather than a mat trigger -- e.g. the last, incomplete loop
-- when the clock runs out.
CREATE TABLE core.splits (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    result_id           UUID NOT NULL REFERENCES core.results (id),
    seq                 INTEGER NOT NULL,        -- ordering, 1-indexed
    checkpoint_name     TEXT,                    -- source's label, e.g. "Lap 12", "Mile 26"
    cum_distance_m      NUMERIC,                 -- cumulative distance at this checkpoint
    elapsed_s           INTEGER NOT NULL,        -- cumulative time at this checkpoint
    is_partial          BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (result_id, seq)
);

CREATE INDEX idx_splits_result ON core.splits (result_id);

COMMIT;
