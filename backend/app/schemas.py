# -*- coding: utf-8 -*-
"""API 請求／回應模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- 見本/段落

class WitnessIn(BaseModel):
    siglum: str = Field(min_length=1, max_length=80)
    source: str = ""
    era: str = ""
    notes: str = ""
    raw_transcription: str = ""
    sort_order: int = 0


class WitnessOut(WitnessIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    passage_id: str


class PassageIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    reference: str = ""
    base_text: str = ""


class PassageOut(PassageIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime
    witnesses: list[WitnessOut] = []


# ---------------------------------------------------------------- 規範規則

class RuleIn(BaseModel):
    pattern: str = Field(min_length=1, max_length=200)
    replacement: str = Field(max_length=200)
    scope: str = "all"
    enabled: bool = True
    note: str = ""


class RuleOut(RuleIn):
    model_config = ConfigDict(from_attributes=True)
    id: str
    passage_id: str


# ---------------------------------------------------------------- 預覽/對齊

class TokenPreview(BaseModel):
    position: int
    orig: str
    norm: str
    type: str
    note: str = ""
    anchor_after_position: int | None = None


class PreviewIn(BaseModel):
    passage_id: str | None = None
    raw_transcription: str
    include_punctuation: bool = False


class CollateIn(BaseModel):
    passage_id: str
    include_punctuation: bool = False
    use_collatex: bool = True
    revision_note: str = ""
    # 以既有 run 為底稿做人工調整時傳入
    base_run_id: str | None = None


class CellOut(BaseModel):
    token_id: str | None = None
    orig: str = ""
    norm: str = ""
    type: str
    gap_token_id: str | None = None


class ColumnOut(BaseModel):
    index: int
    cells: dict[str, CellOut | None]
    suggested_kind: str
    suggested_note: str = ""


class MarkerOut(BaseModel):
    token_id: str
    witness_id: str
    type: str
    orig: str
    note: str = ""
    anchor_column_index: int | None = None
    span_columns: list[int] | None = None


class JudgmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    run_id: str
    column_index: int
    kind: str
    rationale: str = ""
    decided_by: str = "researcher"


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    passage_id: str
    engine: str
    include_punctuation: bool
    score: float | None
    columns: list[ColumnOut]
    markers: list[MarkerOut]
    revision_note: str
    created_at: datetime
    judgments: list[JudgmentOut] = []


# ---------------------------------------------------------------- 人工操作

class JudgmentIn(BaseModel):
    column_index: int = Field(ge=0)
    kind: Literal[
        "variant_form", "omission", "added", "same", "punctuation",
        "annotation", "insertion", "lacuna", "blank", "unknown",
        "doubtful", "moved", "undecided"]
    rationale: str = ""
    decided_by: str = "researcher"


class AdjustIn(BaseModel):
    """人工調整對齊：不改原轉錄，只產生一版新 run。

    action:
      move_cell   把某欄某見本的字移到目標欄（目標欄不存在則新建）
      split_col   把一欄中不同見本的字拆成兩欄
      merge_col   把兩欄合併（僅在不衝突時允許）
    """
    action: Literal["move_cell", "split_col", "merge_col"]
    run_id: str
    column_index: int
    witness_id: str | None = None
    target_column_index: int | None = None
    second_column_index: int | None = None
    revision_note: str = ""
