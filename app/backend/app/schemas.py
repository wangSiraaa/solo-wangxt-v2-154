from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, Field


class WitnessIn(BaseModel):
    siglum: str
    label: str = ""
    source_note: str = ""
    raw_transcription: str
    sort_order: int = 0


class WitnessOut(WitnessIn):
    id: int
    passage_id: int

    model_config = {"from_attributes": True}


class PassageIn(BaseModel):
    title: str
    description: str = ""
    witnesses: list[WitnessIn] = Field(default_factory=list)


class PassageOut(BaseModel):
    id: int
    title: str
    description: str
    created_at: dt.datetime
    witnesses: list[WitnessOut]

    model_config = {"from_attributes": True}


class RuleIn(BaseModel):
    pattern: str
    replacement: str
    note: str = ""
    witness_id: int | None = None
    priority: int = 100
    active: bool = True


class RuleOut(RuleIn):
    id: int
    passage_id: int | None

    model_config = {"from_attributes": True}


class CollateRequest(BaseModel):
    passage_id: int
    include_punctuation: bool = False
    witness_ids: list[int] | None = None  # None = 全部


class TokenOut(BaseModel):
    witness_id: int | None
    kind: str
    display: str
    norm: str
    ordinal: int
    note: str = ""
    anchor_after: int | None = None
    anchor_before: int | None = None
    gap_amount: int | None = None
    gap_unit: str = ""


class ColumnOut(BaseModel):
    id: int
    position: int
    tokens: dict[str, Any]  # key 为 witness_id 字符串（JSON 限制）
    suggested_type: str | None
    suggested_reason: str
    researcher_type: str | None
    researcher_note: str
    confirmed: bool


class RunOut(BaseModel):
    id: int
    passage_id: int
    engine: str
    include_punctuation: bool
    status: str
    note: str
    created_at: dt.datetime
    columns: list[ColumnOut]
    annotations: list[TokenOut] = []
    overrides: list[dict[str, Any]] = []


class JudgmentIn(BaseModel):
    researcher_type: str | None = None
    researcher_note: str = ""
    confirmed: bool = False


class OverrideIn(BaseModel):
    action: str  # anchor_insert | split | merge | relink | mark_lacuna
    payload: dict[str, Any] = Field(default_factory=dict)
    author: str = "researcher"


class WitnessRevisionIn(BaseModel):
    """研究者修订转录：另存新版本需要扩展表结构；此处仅允许追加式勘误说明，
    raw_transcription 通过专门的修订接口在保留审计字段的前提下更新。"""

    new_raw_transcription: str
    reason: str
