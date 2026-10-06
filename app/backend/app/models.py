"""数据模型。

核心原则：
* raw_transcription 保存研究者录入的原始标记文本，永远不被自动流程改写；
* 规范化规则(normalization rule)独立成行，可以反复调整而不影响原转录；
* 自动对齐只是候选（collation_run + alignment_column），人工判断落在
  alignment_column.researcher_* 与 column_judgment 上；
* 人工调整对齐另存 manual_overrides，绝不回写原转录。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Passage(Base):
    """一段待校勘的文字（题目级容器）。"""

    __tablename__ = "passages"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    witnesses: Mapped[list["Witness"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan", order_by="Witness.sort_order"
    )
    runs: Mapped[list["CollationRun"]] = relationship(
        back_populates="passage", cascade="all, delete-orphan"
    )


class Witness(Base):
    """一个见本（抄本/刻本/稿本……）。"""

    __tablename__ = "witnesses"
    __table_args__ = (UniqueConstraint("passage_id", "siglum", name="uq_witness_siglum"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    passage_id: Mapped[int] = mapped_column(ForeignKey("passages.id", ondelete="CASCADE"))
    siglum: Mapped[str] = mapped_column(String(40))  # 如 甲本、P.3251
    label: Mapped[str] = mapped_column(String(200), default="")
    source_note: Mapped[str] = mapped_column(Text, default="")
    # 原转录，逐字符保留，含标记；任何自动流程不得改写
    raw_transcription: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    passage: Mapped["Passage"] = relationship(back_populates="witnesses")


class NormalizationRule(Base):
    """规范化规则：用于匹配的等价字形，不改动原转录。

    pattern 为原字形（可多字），replacement 为规范形。scope 可为全局(global)
    或限定某个见本。规则带优先级，可随时停用。
    """

    __tablename__ = "normalization_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    passage_id: Mapped[int | None] = mapped_column(
        ForeignKey("passages.id", ondelete="CASCADE"), nullable=True
    )
    witness_id: Mapped[int | None] = mapped_column(
        ForeignKey("witnesses.id", ondelete="CASCADE"), nullable=True
    )
    pattern: Mapped[str] = mapped_column(String(50))
    replacement: Mapped[str] = mapped_column(String(50))
    note: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)


class CollationRun(Base):
    """一次对齐运算。参数（标点是否参与等）与结果快照一并保存。"""

    __tablename__ = "collation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    passage_id: Mapped[int] = mapped_column(ForeignKey("passages.id", ondelete="CASCADE"))
    engine: Mapped[str] = mapped_column(String(40))  # collatex-http / collatex-cli / internal-fallback
    include_punctuation: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="ok")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    # 运算时实际使用的规则快照，保证可复现
    rules_snapshot: Mapped[list] = mapped_column(JSON, default=list)

    passage: Mapped["Passage"] = relationship(back_populates="runs")
    columns: Mapped[list["AlignmentColumn"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="AlignmentColumn.position"
    )
    overrides: Mapped[list["ManualOverride"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class AlignmentColumn(Base):
    """对齐表中的一列：各见本在该位置上的 token（或缺席）。

    token 数据结构：
      {witness_id, kind, display, norm, ordinal, raw_start, raw_end, note}
    kind: char | punct | lacuna | blank | unknown | annotation
    自动建议写在 suggested_*；研究者结论写在 researcher_*，二者永不互覆。
    """

    __tablename__ = "alignment_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("collation_runs.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    # witness_id -> token 或 null（该见本此列缺席，即脱/添判断的原始材料）
    tokens: Mapped[dict] = mapped_column(JSON, default=dict)
    suggested_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    suggested_reason: Mapped[str] = mapped_column(Text, default="")
    # —— 人工判断 ——
    researcher_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    researcher_note: Mapped[str] = mapped_column(Text, default="")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    run: Mapped["CollationRun"] = relationship(back_populates="columns")


class ManualOverride(Base):
    """人工对自动对齐的调整动作记录（仅追加，不删除原转录/原列）。

    action:
      anchor_insert  把插入片段（批注/添补）锚定到相邻列
      split          拆开自动合并的一列
      merge          合并相邻列
      relink         把某 token 移到另一列
      mark_lacuna    缺叶/缺字标记（区别于空白正文）
    """

    __tablename__ = "manual_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("collation_runs.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(30))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    author: Mapped[str] = mapped_column(String(80), default="researcher")

    run: Mapped["CollationRun"] = relationship(back_populates="overrides")
