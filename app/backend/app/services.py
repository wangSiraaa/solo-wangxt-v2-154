"""校勘编排服务：解析 → 规范化 → 调 CollateX → 分类 → 持久化候选。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import classify as classify_mod
from .collatex_client import collate
from .config import get_settings
from .models import AlignmentColumn, CollationRun, NormalizationRule, Witness
from .normalization import Normalizer
from .transcription import parse_transcription

# 受控词表（供前端下拉与导出）
VARIANT_TYPES = [
    "identical", "glyph_variant", "substitution", "omission", "addition",
    "punctuation", "lacuna", "blank", "unknown_char", "mixed_struct", "divergent",
]
VARIANT_TYPE_LABELS = {
    "identical": "一致",
    "glyph_variant": "异体字",
    "substitution": "异文",
    "omission": "脱文",
    "addition": "添入",
    "punctuation": "断句/标点",
    "lacuna": "缺叶/缺文",
    "blank": "空白正文",
    "unknown_char": "未知字",
    "mixed_struct": "结构混合(待判)",
    "divergent": "分歧(待判)",
}


def load_rules(db: Session, passage_id: int) -> list[NormalizationRule]:
    stmt = (
        select(NormalizationRule)
        .where(NormalizationRule.active.is_(True))
        .where(
            (NormalizationRule.passage_id == passage_id)
            | (NormalizationRule.passage_id.is_(None))
        )
        .order_by(NormalizationRule.priority.desc(), NormalizationRule.id)
    )
    return list(db.scalars(stmt))


def parse_witness(w: Witness, rules: list[NormalizationRule]) -> list:
    tokens = parse_transcription(w.raw_transcription, witness_id=w.id)
    scoped = [(r.pattern, r.replacement) for r in rules if r.witness_id is None or r.witness_id == w.id]
    Normalizer(scoped).apply(tokens)
    return tokens


def run_collation(
    db: Session, passage_id: int, include_punctuation: bool,
    witness_ids: list[int] | None = None,
) -> CollationRun:
    settings = get_settings()
    witnesses = list(db.scalars(select(Witness).where(Witness.passage_id == passage_id)))
    witnesses.sort(key=lambda w: w.sort_order)
    if witness_ids is not None:
        wanted = set(witness_ids)
        witnesses = [w for w in witnesses if w.id in wanted]
    if len(witnesses) < 2:
        raise ValueError("至少需要两个见本才能校勘")

    rules = load_rules(db, passage_id)
    parsed = {w.id: parse_witness(w, rules) for w in witnesses}

    # 正文序列；标点是否参与由参数决定（批注从不参与）
    def body(wid):
        return [
            t.to_dict()
            for t in parsed[wid]
            if t.kind != "annotation"
            and (bool(include_punctuation) or t.kind != "punct")
        ]

    sequences = {w.id: body(w.id) for w in witnesses}
    result = collate(sequences, mode=settings.collatex_mode,
                     url=settings.collatex_url, cli=settings.collatex_cli)

    run = CollationRun(
        passage_id=passage_id,
        engine=result.engine,
        include_punctuation=include_punctuation,
        status="empty" if not result.columns else "ok",
        note=result.note,
        rules_snapshot=[{"pattern": r.pattern, "replacement": r.replacement,
                         "witness_id": r.witness_id, "priority": r.priority} for r in rules],
    )
    db.add(run)
    db.flush()

    # 批注（插入片段）随 run 一并返回给前端做锚定展示；不进入对齐列
    annotations = {
        w.id: [t.to_dict() for t in parsed[w.id] if t.kind == "annotation"]
        for w in witnesses
    }
    # 挂到内存对象上，序列化时使用
    run.annotations_map = annotations  # type: ignore[attr-defined]

    for pos, col in enumerate(result.columns):
        # col: {wid: token_dict|None} —— JSON 要求键为字符串
        token_map = {str(wid): (tok if tok is not None else None) for wid, tok in col.items()}
        suggestion = classify_mod.classify_column(col)
        db.add(AlignmentColumn(
            run_id=run.id, position=pos, tokens=token_map,
            suggested_type=suggestion[0], suggested_reason=suggestion[1],
        ))

    db.flush()
    return run
