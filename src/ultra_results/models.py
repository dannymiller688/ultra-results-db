"""Pydantic models produced by adapters. Adapters never touch the database --
they only produce these, and the loader consumes them."""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel


class ParsedRace(BaseModel):
    name: str
    country: Optional[str] = None
    region: Optional[str] = None
    surface: Optional[str] = None


class ParsedEvent(BaseModel):
    event_date: date
    event_type: str  # 'fixed_distance' | 'fixed_time' | 'backyard' | 'stage'
    distance_m: Optional[float] = None
    duration_s: Optional[int] = None
    loop_distance_m: Optional[float] = None
    distance_raw: Optional[str] = None
    name: Optional[str] = None


class ParsedSourceAthlete(BaseModel):
    source_athlete_key: Optional[str] = None  # source's own ID (raceresult's "ID" field, here)
    name_raw: str
    name_norm: str
    year_of_birth: Optional[int] = None
    sex: Optional[str] = None
    nationality: Optional[str] = None


class ParsedResult(BaseModel):
    source_record_id: Optional[str] = None  # BIB, in this source
    athlete: ParsedSourceAthlete
    status: str  # 'finished' | 'dnf' | 'dns' | 'dq' | 'in_progress'
    time_s: Optional[int] = None
    distance_m: Optional[float] = None
    time_kind: Optional[str] = None
    overall_place: Optional[int] = None


class ParsedSplit(BaseModel):
    result_source_record_id: str  # ties back to ParsedResult.source_record_id
    seq: int
    checkpoint_name: Optional[str] = None
    cum_distance_m: Optional[float] = None
    elapsed_s: int
    is_partial: bool = False
