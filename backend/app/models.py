# -*- coding: utf-8 -*-
"""SQLAlchemy 2.0 模型。

設計要點
========
* ``Token.orig`` 保存原字形（含缺字符號、夾注、墨釘等），任何對齊調整都不會改動它；
* ``Token.norm`` 是參與比對的規範形式，與原字形分欄保存；
* :class:`Witness` 保存原始轉錄原文 ``raw_transcription``，與分詞結果同留；
* 人工判斷與自動建議分層：``CollationRun`` 是建議快照，
  :class:`Judgment` 才是研究者結論，匯出時以判斷為準；
* 缺葉（lacuna）、空白正文（blank，即漫漶空白）、
  批注（annotation）、插入（insertion）各自是不同的 token 類型，
  絕不混成普通文字差異。
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


def _uuid() -> str:
    return uuid.uuid4().hex


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- token 類型

class TokenType(str, enum.Enum):
    TEXT = "text"                # 普通正文字符
    PUNCT = "punct"              # 標點（可選是否參與對齊）
    LACUNA = "lacuna"            # 缺葉／整葉脫失，佔位記號
    BLANK = "blank"              # 漫漶空白／空白正文，非缺葉
    ANNOTATION = "annotation"    # 批注：旁注、眉批等
    INSERTION = "insertion"      # 後人鈔補／他本插入片段
    UNKNOWN = "unknown"          # 存疑字（缺字方框等），保留原形，不得猜補


# 不參加普通正文行列、只錨定於相鄰位置的類型
MARKER_TYPES = {TokenType.ANNOTATION, TokenType.INSERTION}
# 佔位類型：與一般文字性質完全不同
GAP_TYPES = {TokenType.LACUNA, TokenType.BLANK}


class RelationKind(str, enum.Enum):
    """研究者對一個對齊行列可下的校勘判斷。"""
    VARIANT_FORM = "variant_form"      # 異體字／異文
    OMISSION = "omission"              # 脫文
    ADDED = "added"                    # 衍／增（他本所無）
    SAME = "same"                      # 一致，無異
    PUNCTUATION = "punctuation"        # 僅標點、斷句之差
    ANNOTATION = "annotation"          # 批注
    INSERTION = "insertion"            # 插入片段
    LACUNA = "lacuna"                  # 缺葉
    BLANK = "blank"                    # 空白正文
    UNKNOWN = "unknown"                # 存疑，無法判定
    DOUBTFUL = "doubtful"              # 疑似，待考
    MOVED = "moved"                    # 錯簡／移位
    UNDECIDED = "undecided"            # 暫不判定


class Passage(Base):
    """同一段文字（一個校勘單元）。"""
    __tablename__ = "passages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(200))
    reference: Mapped[str] = mapped_column(String(200), default="")
    base_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))

    witnesses: Mapped[list["Witness"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan",
        order_by="Witness.sort_order")
    rules: Mapped[list["NormalizationRule"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan")
    runs: Mapped[list["CollationRun"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan")


class Witness(Base):
    """一個見本（鈔本、刻本、輯校本……）。"""
    __tablename__ = "witnesses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    passage_id: Mapped[str] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), index=True)
    siglum: Mapped[str] = mapped_column(String(80))       # 例如 甲本、乙本
    source: Mapped[str] = mapped_column(String(300), default="")
    era: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    raw_transcription: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))

    passage: Mapped[Passage] = relationship(back_populates="witnesses")
    tokens: Mapped[list["Token"]] = relationship(
        back_populates="witness", cascade="all, delete-orphan",
        order_by="Token.position")

    __table_args__ = (UniqueConstraint("passage_id", "siglum",
                                       name="uq_witness_siglum"),)


class Token(Base):
    """一個對齊原子（字符／標點／記號）。

    ``orig`` 與 ``norm`` 分欄：
      orig = 原字形，如「徳」「□」「〔缺葉〕」；
      norm = 比對用規範形，如「德」，缺葉記號的 norm 為空。
    ``anchor_after`` 記錄插入片段、批注所錨定的相鄰正文 token，
    保證它「貼著」原位，而不會被當成脫文行。
    """
    __tablename__ = "tokens"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    witness_id: Mapped[str] = mapped_column(
        ForeignKey("witnesses.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    orig: Mapped[str] = mapped_column(Text)
    norm: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[TokenType] = mapped_column(Enum(TokenType),
                                            default=TokenType.TEXT)
    anchor_after: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")

    witness: Mapped[Witness] = relationship(back_populates="tokens")


class NormalizationRule(Base):
    """規範化規則：把原字形映射為比對形式。

    規則只產生 ``norm``，不改寫 ``orig``，因此可逆、可審計。
    """
    __tablename__ = "normalization_rules"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    passage_id: Mapped[str] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), index=True)
    pattern: Mapped[str] = mapped_column(String(200))   # 原形，如 徳/爲/峯
    replacement: Mapped[str] = mapped_column(String(200))  # 規範形
    scope: Mapped[str] = mapped_column(String(80), default="all")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str] = mapped_column(Text, default="")

    passage: Mapped[Passage] = relationship(back_populates="rules")


class CollationRun(Base):
    """一次 CollateX（或退回比對器）產生的對齊候選快照。

    快照是「建議」，不是結論：
      * ``include_punctuation`` 記錄本次標點是否參與對齊；
      * ``engine`` 記錄來源（collatex / builtin）；
      * columns/markers 以 JSON 保存；
      * 調整對齊時新增一筆 run（版本化），原轉錄與舊 run 都保留。
    """
    __tablename__ = "collation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    passage_id: Mapped[str] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), index=True)
    engine: Mapped[str] = mapped_column(String(40))
    include_punctuation: Mapped[bool] = mapped_column(Boolean, default=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    columns: Mapped[list] = mapped_column(JSON, default=list)
    markers: Mapped[list] = mapped_column(JSON, default=list)
    revision_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))

    passage: Mapped[Passage] = relationship(back_populates="runs")
    judgments: Mapped[list["Judgment"]] = relationship(
        back_populates="run", cascade="all, delete-orphan")


class Judgment(Base):
    """研究者對某一欄（或某記號）的人工判斷。

    同一 run + column_index 只保留一筆，更新即覆核；
    自動建議寫在 column.suggested_kind，人工判斷寫在本表，涇渭分明。
    """
    __tablename__ = "judgments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("collation_runs.id", ondelete="CASCADE"), index=True)
    column_index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[RelationKind] = mapped_column(Enum(RelationKind))
    rationale: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(120), default="researcher")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))

    run: Mapped[CollationRun] = relationship(back_populates="judgments")

    __table_args__ = (UniqueConstraint("run_id", "column_index",
                                       name="uq_run_column"),)


class TranscriptRevision(Base):
    """見本原轉錄的修訂歷史。

    改寫轉錄不會覆蓋舊文本：每次修改留一筆，可隨時回看。
    對齊調整（調欄、判斷）完全不觸及本表，也不觸及 Token.orig。
    """
    __tablename__ = "transcript_revisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    witness_id: Mapped[str] = mapped_column(
        ForeignKey("witnesses.id", ondelete="CASCADE"), index=True)
    old_transcription: Mapped[str] = mapped_column(Text, default="")
    new_transcription: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[str] = mapped_column(String(120), default="researcher")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))
