"""把人工调整(manual override)应用到对齐列。

工作表示普通 dict：{id(临时), position, tokens, suggested_*, researcher_*}，
应用结束后统一落库（删旧列、写新列）。

纪律：
* 原 witness.raw_transcription 永不触碰；删除的只是自动候选的列快照，
  且已有人工判断(researcher_*)会随列内容继承；
* 未知字(□)不允许与任何实字合并——不把未知补成猜测字；
* 缺叶/空白结构标记不与实字并列为"异体"；
* 每次动作都写 ManualOverride 审计行。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AlignmentColumn, ManualOverride

VALID_ACTIONS = {"anchor_insert", "split", "merge", "relink", "mark_lacuna"}

GUARDED_PAIRS = {
    ("unknown", "char"), ("char", "unknown"),
    ("lacuna", "char"), ("char", "lacuna"),
    ("blank", "char"), ("char", "blank"),
}


class OverrideError(ValueError):
    pass


def _snapshot(columns: list[AlignmentColumn]) -> list[dict]:
    import copy
    return [
        {
            "id": c.id, "position": c.position,
            "tokens": copy.deepcopy(c.tokens),
            "suggested_type": c.suggested_type, "suggested_reason": c.suggested_reason,
            "researcher_type": c.researcher_type, "researcher_note": c.researcher_note,
            "confirmed": c.confirmed,
        }
        for c in columns
    ]


def _load(db: Session, run_id: int) -> list[dict]:
    rows = (db.query(AlignmentColumn)
              .filter(AlignmentColumn.run_id == run_id)
              .order_by(AlignmentColumn.position).all())
    return _snapshot(rows)


def apply_override(db: Session, run_id: int, action: str, payload: dict, author: str) -> ManualOverride:
    if action not in VALID_ACTIONS:
        raise OverrideError(f"未知操作 {action}")
    cols = _load(db, run_id)
    if not cols:
        raise OverrideError("该运行尚无对齐列")

    if action == "split":
        cols = _split(cols, payload)
    elif action == "merge":
        cols = _merge(cols, payload)
    elif action == "relink":
        cols = _relink(cols, payload)
    elif action == "mark_lacuna":
        cols = _mark_lacuna(cols, payload)
    elif action == "anchor_insert":
        _validate_anchor(cols, payload)

    _persist(db, run_id, cols)
    ov = ManualOverride(run_id=run_id, action=action, payload=payload, author=author)
    db.add(ov)
    db.flush()
    return ov


def _find(cols: list[dict], cid: int) -> dict:
    col = next((c for c in cols if c["id"] == cid), None)
    if col is None:
        raise OverrideError("列不存在")
    return col


def _kinds(col: dict) -> set[str]:
    return {t["kind"] for t in col["tokens"].values() if t}


def _guard_against_guess(col: dict, new_kind: str) -> None:
    for k in _kinds(col):
        if (k, new_kind) in GUARDED_PAIRS or (new_kind, k) in GUARDED_PAIRS:
            raise OverrideError("禁止把未知字/缺文/空白与实字并入同一列（不得把未知补成猜测字）")


def _split(cols: list[dict], payload: dict) -> list[dict]:
    """纠正错误并列为两列：把指定见本的 token 单独拆到新列。"""
    col = _find(cols, payload["column_id"])
    wid = str(payload["witness_id"])
    if not col["tokens"].get(wid):
        raise OverrideError("split: 该见本在此列为空")
    new_col = {
        "id": None, "position": col["position"] + 1,
        "tokens": {w: (col["tokens"][wid] if w == wid else None) for w in col["tokens"]},
        "suggested_type": None, "suggested_reason": "人工拆分列，待重新判定",
        "researcher_type": None, "researcher_note": "", "confirmed": False,
    }
    col["tokens"][wid] = None
    col["suggested_reason"] = (col["suggested_reason"] or "") + "；人工已拆出一见本"
    idx = cols.index(col)
    return cols[:idx + 1] + [new_col] + cols[idx + 1:]


def _merge(cols: list[dict], payload: dict) -> list[dict]:
    a, b = _find(cols, payload["column_a"]), _find(cols, payload["column_b"])
    ia, ib = cols.index(a), cols.index(b)
    if abs(ia - ib) != 1:
        raise OverrideError("只能合并相邻两列")
    merged = {
        "id": a["id"], "position": a["position"], "tokens": dict(a["tokens"]),
        "suggested_type": None, "suggested_reason": "人工合并列，待重新判定",
        "researcher_type": None, "researcher_note": "", "confirmed": False,
    }
    for wid, tok in b["tokens"].items():
        if tok is None:
            continue
        if merged["tokens"].get(wid) is not None:
            raise OverrideError("同一见本两列都有字，不能并为单字列")
        _guard_against_guess(merged, tok["kind"])
        merged["tokens"][wid] = tok
    lo, hi = sorted((ia, ib))
    return cols[:lo] + [merged] + cols[hi + 1:]


def _relink(cols: list[dict], payload: dict) -> list[dict]:
    """把某见本 token 从一列移到另一列（纠正自动锚定/插入位置）。"""
    src = _find(cols, payload["column_from"])
    dst = _find(cols, payload["column_to"])
    wid = str(payload["witness_id"])
    tok = src["tokens"].get(wid)
    if not tok:
        raise OverrideError("源列该见本无字")
    if dst["tokens"].get(wid) is not None:
        raise OverrideError("目标列该见本已有字，请先拆分")
    _guard_against_guess(dst, tok["kind"])
    src["tokens"][wid] = None
    dst["tokens"][wid] = tok
    return cols


def _mark_lacuna(cols: list[dict], payload: dict) -> list[dict]:
    """在结构标记之间更正（缺叶↔空白↔未知），或在空位列补结构标记；绝不补实字。"""
    col = _find(cols, payload["column_id"])
    wid = str(payload["witness_id"])
    kind = payload.get("kind")
    if kind not in {"lacuna", "blank", "unknown"}:
        raise OverrideError("只能标注结构性缺失；补实字必须修订转录，不可猜补")
    existing = col["tokens"].get(wid)
    if existing and existing["kind"] == "char":
        raise OverrideError("该列是据转录解析的实字，不能抹改为缺失标记")
    col["tokens"][wid] = {
        "witness_id": int(wid), "kind": kind,
        "display": payload.get("display",
                              {"lacuna": "〔缺〕", "blank": "〔空白〕", "unknown": "□"}[kind]),
        "norm": "", "ordinal": -1,
        "note": payload.get("note", "人工标注的结构缺失（未改原转录）"),
        "raw_start": -1, "raw_end": -1,
        "anchor_after": None, "anchor_before": None,
        "gap_amount": payload.get("gap_amount"), "gap_unit": payload.get("gap_unit", ""),
    }
    return cols


def _validate_anchor(cols: list[dict], payload: dict) -> None:
    positions = {c["position"] for c in cols}
    after, before = payload.get("after_position"), payload.get("before_position")
    if after is None and before is None:
        raise OverrideError("至少提供一个相邻锚点(after_position/before_position)")
    if after is not None and after not in positions:
        raise OverrideError("锚点前列不存在")
    if before is not None and before not in positions:
        raise OverrideError("锚点后列不存在")


def _signature(col: dict) -> frozenset:
    return frozenset((w, t["display"] if t else None) for w, t in col["tokens"].items())


def _persist(db: Session, run_id: int, cols: list[dict]) -> None:
    old = (db.query(AlignmentColumn)
             .filter(AlignmentColumn.run_id == run_id)
             .order_by(AlignmentColumn.position).all())
    inherited = [
        (_signature({"tokens": c.tokens}), c.researcher_type, c.researcher_note, c.confirmed)
        for c in old if c.researcher_type or c.confirmed
    ]
    for c in old:
        db.delete(c)
    db.flush()
    for pos, col in enumerate(cols):
        new = AlignmentColumn(
            run_id=run_id, position=pos, tokens=col["tokens"],
            suggested_type=col["suggested_type"],
            suggested_reason=col["suggested_reason"],
        )
        sig = _signature(col)
        for old_sig, rtype, rnote, conf in inherited:
            if old_sig == sig:
                new.researcher_type, new.researcher_note, new.confirmed = rtype, rnote, conf
                break
        db.add(new)
    db.flush()
