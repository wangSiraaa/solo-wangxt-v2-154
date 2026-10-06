# -*- coding: utf-8 -*-
"""業務服務層。"""
from __future__ import annotations

import copy
import csv
import io
import json

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .collate.aligner import align_witnesses
from .collate.collatex_client import CollateXError, run_collatex
from .collate.normalization import load_char_map, norm_for_token
from .collate.tokenizer import tokenize
from .config import get_settings
from .models import (
    CollationRun,
    Judgment,
    Passage,
    RelationKind,
    Token,
    TokenType,
    TranscriptRevision,
    Witness,
)

TOKEN_ENUM = {
    "text": TokenType.TEXT,
    "punct": TokenType.PUNCT,
    "lacuna": TokenType.LACUNA,
    "blank": TokenType.BLANK,
    "annotation": TokenType.ANNOTATION,
    "insertion": TokenType.INSERTION,
    "unknown": TokenType.UNKNOWN,
}


# ---------------------------------------------------------------- 轉錄處理

def retokenize_witness(db: Session, witness: Witness,
                       charmap: dict[str, str] | None = None) -> None:
    """依 witness.raw_transcription 重建 token 列。

    * 原字形 orig 直接取自解析結果；
    * norm 套用規範規則；
    * 重建採「全刪全建」，但僅作用於 tokens 表——
      raw_transcription 與 TranscriptRevision 永不被此函式改動；
    * 已有 run（對齊快照）也完全不受影響，故歷史結論不會被悄悄改寫。
    """
    if charmap is None:
        charmap = load_char_map(db, witness.passage_id)

    parsed = tokenize(witness.raw_transcription)
    db.query(Token).filter(Token.witness_id == witness.id).delete()
    db.flush()

    for pt in parsed.tokens:
        ttype = TOKEN_ENUM[pt.type]
        norm = norm_for_token(pt.orig, ttype, charmap)
        # anchor_after 是同見本內的 position，先記 position，
        # 提交後若需 token id 可再解析；目前欄位存 position 即可定位
        db.add(Token(
            witness_id=witness.id,
            position=pt.position,
            orig=pt.orig,
            norm=norm,
            type=ttype,
            anchor_after=(str(pt.anchor_after_position)
                          if pt.anchor_after_position is not None else None),
            note=pt.note,
        ))
    db.flush()


def create_witness(db: Session, passage_id: str, data) -> Witness:
    w = Witness(passage_id=passage_id, siglum=data.siglum, source=data.source,
                era=data.era, notes=data.notes,
                raw_transcription=data.raw_transcription,
                sort_order=data.sort_order)
    db.add(w)
    db.flush()
    retokenize_witness(db, w)
    db.add(TranscriptRevision(
        witness_id=w.id, old_transcription="",
        new_transcription=data.raw_transcription))
    db.flush()
    return w


def update_transcription(db: Session, witness: Witness, new_text: str,
                         changed_by: str = "researcher") -> None:
    """更新轉錄：留修訂史、重建 token；舊 run 保持原樣。"""
    if new_text == witness.raw_transcription:
        return
    db.add(TranscriptRevision(
        witness_id=witness.id,
        old_transcription=witness.raw_transcription,
        new_transcription=new_text,
        changed_by=changed_by))
    witness.raw_transcription = new_text
    db.flush()
    retokenize_witness(db, witness)
    db.flush()


# ---------------------------------------------------------------- 對齊

def _load_passage_bundle(db: Session, passage_id: str):
    passage = db.get(Passage, passage_id)
    if passage is None:
        raise KeyError("passage not found")
    witnesses = (db.query(Witness)
                 .filter(Witness.passage_id == passage_id)
                 .order_by(Witness.sort_order, Witness.siglum)
                 .all())
    witness_tokens = {}
    for w in witnesses:
        toks = db.query(Token).filter(Token.witness_id == w.id)\
            .order_by(Token.position).all()
        witness_tokens[w.id] = toks
    return passage, witnesses, witness_tokens


def collate(db: Session, passage_id: str, include_punctuation: bool,
            use_collatex: bool = True, revision_note: str = "",
            base_columns=None, base_markers=None,
            base_judgments: dict[int, str] | None = None) -> CollationRun:
    passage, witnesses, witness_tokens = _load_passage_bundle(db, passage_id)
    if len(witnesses) < 1:
        raise ValueError("至少需要一個見本")
    order = [w.id for w in witnesses]

    engine = "builtin"
    result = None
    settings = get_settings()

    if use_collatex and settings.collatex_url and len(witnesses) > 1:
        try:
            with httpx.Client(timeout=settings.collatex_timeout) as client:
                result = run_collatex(
                    client, settings.collatex_url,
                    witness_tokens, order, include_punctuation)
            engine = "collatex"
        except CollateXError:
            result = None  # 安靜退回，下面由內建產生
    if result is None:
        if base_columns is not None:
            # 人工調整：沿用傳入欄位，不再重算
            result = {"columns": base_columns, "markers": base_markers or [],
                      "engine_detail": "manual", "score": None}
            engine = "manual"
        else:
            result = align_witnesses(witness_tokens, order,
                                     include_punctuation)
            engine = "builtin"

    run = CollationRun(
        passage_id=passage_id,
        engine=engine,
        include_punctuation=include_punctuation,
        score=result.get("score"),
        columns=result["columns"],
        markers=result["markers"],
        revision_note=revision_note,
    )
    db.add(run)
    db.flush()

    if base_judgments:
        for col_idx, kind in base_judgments.items():
            db.add(Judgment(run_id=run.id, column_index=col_idx,
                            kind=RelationKind(kind)))
        db.flush()
    return run


# ---------------------------------------------------------------- 人工判斷

def set_judgment(db: Session, run_id: str, data) -> Judgment:
    run = db.get(CollationRun, run_id)
    if run is None:
        raise KeyError("run not found")
    if data.column_index >= len(run.columns):
        raise IndexError("column_index 超出範圍")
    existing = (db.query(Judgment)
                .filter(Judgment.run_id == run_id,
                        Judgment.column_index == data.column_index)
                .one_or_none())
    if existing:
        existing.kind = RelationKind(data.kind)
        existing.rationale = data.rationale
        existing.decided_by = data.decided_by
        db.flush()
        return existing
    j = Judgment(run_id=run_id, column_index=data.column_index,
                 kind=RelationKind(data.kind), rationale=data.rationale,
                 decided_by=data.decided_by)
    db.add(j)
    db.flush()
    return j


# ---------------------------------------------------------------- 人工調整

def adjust(db: Session, data) -> CollationRun:
    """依調整動作產生*新一版* run。

    全程只深拷貝舊 run 的 JSON 欄位做修改：
      * 不寫 Token.orig、不動 raw_transcription；
      * 未知字「□」的 cell 不許被改成其他字（後端硬性拒絕）；
      * 調整後重新編欄號，舊判斷按欄位內容儘量保留。
    """
    run = db.get(CollationRun, data.run_id)
    if run is None:
        raise KeyError("run not found")
    cols = copy.deepcopy(run.columns)
    markers = copy.deepcopy(run.markers)

    if data.action == "move_cell":
        if data.witness_id is None or data.target_column_index is None:
            raise ValueError("move_cell 需要 witness_id 與 target_column_index")
        _guard_unknown(cols[data.column_index]["cells"].get(data.witness_id))
        cell = cols[data.column_index]["cells"].pop(data.witness_id)
        target = data.target_column_index
        if target < 0 or target > len(cols):
            raise IndexError("目標欄超出範圍")
        if target == len(cols):
            cols.append({"index": target,
                         "cells": {w: None for w in _wids(cols)},
                         "suggested_kind": "undecided",
                         "suggested_note": "人工移動產生的新欄"})
        existing = cols[target]["cells"].get(data.witness_id)
        if existing is not None:
            raise ValueError("目標欄該見本已有字，請先移走或使用 split_col")
        cols[target]["cells"][data.witness_id] = cell

    elif data.action == "split_col":
        src = cols[data.column_index]
        groups: dict[str, dict] = {}
        for wid, cell in src["cells"].items():
            key = "none" if cell is None else cell.get("norm", cell.get("orig"))
            groups.setdefault(key, {})[wid] = cell
        if len(groups) < 2:
            raise ValueError("此欄各見本內容相同，無需拆分")
        new_cols = []
        for key, grp in groups.items():
            new_cols.append({
                "index": 0,
                "cells": {w: grp.get(w) for w in _wids(cols)},
                "suggested_kind": ("undecided" if key != "none" else "omission"),
                "suggested_note": "人工拆分",
            })
        cols[data.column_index:data.column_index + 1] = new_cols

    elif data.action == "merge_col":
        j = data.second_column_index
        if j is None or j == data.column_index:
            raise ValueError("merge_col 需要兩個不同欄號")
        a, b = cols[data.column_index], cols[j]
        for wid in _wids(cols):
            if a["cells"].get(wid) is not None and b["cells"].get(wid) is not None:
                raise ValueError(f"見本 {wid} 在兩欄都有字，不能合併")
        for wid, cell in b["cells"].items():
            if cell is not None:
                a["cells"][wid] = cell
        del cols[j]

    # 重編 index；附著的記號錨點以夾擠方式粗略保留
    cols = _reindex(cols)
    note = data.revision_note or f"人工調整：{data.action}"
    # 舊判斷不機械遷移（欄位語義可能已變），但保留在舊 run；
    # 新 run 不複製判斷，由研究者重新確認——避免建議偷渡成結論。
    return collate(db, run.passage_id, run.include_punctuation,
                   use_collatex=False, revision_note=note,
                   base_columns=cols, base_markers=markers)


def _guard_unknown(cell):
    if cell and cell.get("type") == "unknown":
        raise ValueError("未知字「□」不可被移補為他字；只能保留原位或留空")


def _wids(cols):
    return sorted({w for c in cols for w in c["cells"]})


def _reindex(cols):
    for i, c in enumerate(cols):
        c["index"] = i
    return cols


# ---------------------------------------------------------------- 預覽

def preview_tokens(db: Session, raw: str, passage_id: str | None):
    charmap = load_char_map(db, passage_id) if passage_id else {}
    parsed = tokenize(raw)
    out = []
    for pt in parsed.tokens:
        ttype = TOKEN_ENUM[pt.type]
        out.append({
            "position": pt.position,
            "orig": pt.orig,
            "norm": norm_for_token(pt.orig, ttype, charmap),
            "type": pt.type,
            "note": pt.note,
            "anchor_after_position": pt.anchor_after_position,
        })
    return out


# ---------------------------------------------------------------- 匯出

KIND_LABEL = {
    "variant_form": "異體字/異文", "omission": "脫文", "added": "增衍",
    "same": "一致", "punctuation": "斷句", "annotation": "批注",
    "insertion": "插入", "lacuna": "缺葉", "blank": "空白",
    "unknown": "存疑", "doubtful": "待考", "moved": "移位",
    "undecided": "未判定",
}


def export_run(db: Session, run_id: str, fmt: str):
    run = db.get(CollationRun, run_id)
    if run is None:
        raise KeyError("run not found")
    witnesses = (db.query(Witness)
                 .filter(Witness.passage_id == run.passage_id)
                 .order_by(Witness.sort_order, Witness.siglum).all())
    wmap = {w.id: w for w in witnesses}
    judgments = {j.column_index: j for j in run.judgments}

    payload = {
        "passage_id": run.passage_id,
        "passage_title": db.get(Passage, run.passage_id).title,
        "run_id": run.id,
        "engine": run.engine,
        "include_punctuation": run.include_punctuation,
        "created_at": run.created_at.isoformat(),
        "witness_sources": [
            {"witness_id": w.id, "siglum": w.siglum, "source": w.source,
             "era": w.era}
            for w in witnesses
        ],
        "columns": [],
        "markers": run.markers,
    }
    for col in run.columns:
        j = judgments.get(col["index"])
        entry = {
            "column_index": col["index"],
            "auto_suggested_kind": col["suggested_kind"],
            "auto_suggested_note": col.get("suggested_note", ""),
            "human_judgment": (KIND_LABEL.get(j.kind.value, j.kind.value)
                               if j else None),
            "human_kind": j.kind.value if j else None,
            "rationale": j.rationale if j else "",
            "readings": [],
        }
        for w in witnesses:
            cell = col["cells"].get(w.id)
            entry["readings"].append({
                "siglum": w.siglum, "source": w.source,
                "orig": cell["orig"] if cell else "",
                "norm": cell["norm"] if cell else "",
                "type": cell["type"] if cell else "gap",
                "present": cell is not None,
            })
        payload["columns"].append(entry)

    if fmt == "json":
        return "application/json", json.dumps(payload, ensure_ascii=False,
                                              indent=2)
    if fmt == "csv":
        return "text/csv; charset=utf-8", _export_csv(payload, witnesses)
    if fmt in ("md", "markdown"):
        return "text/markdown; charset=utf-8", _export_md(payload, witnesses)
    raise ValueError("fmt 必須是 json / csv / md")


def _export_csv(payload, witnesses):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["# passage", payload["passage_title"],
                     "run", payload["run_id"], "engine", payload["engine"]])
    header = ["column", "auto_suggestion", "human_judgment", "rationale"]
    header += [f"{w.siglum}({w.source})[orig]" for w in witnesses]
    header += [f"{w.siglum}[norm]" for w in witnesses]
    writer.writerow(header)
    for col in payload["columns"]:
        row = [col["column_index"], col["auto_suggested_kind"],
               col["human_kind"] or "", col["rationale"]]
        row += [r["orig"] for r in col["readings"]]
        row += [r["norm"] for r in col["readings"]]
        writer.writerow(row)
    # 記號（缺葉/批注等）另段輸出，保留錨點
    writer.writerow([])
    writer.writerow(["--- markers: 缺葉/空白/批注/插入（含錨點）---"])
    writer.writerow(["type", "siglum", "orig", "note", "anchor_column"])
    sig = {m["witness_id"]: next(
        (w.siglum for w in witnesses if w.id == m["witness_id"]),
        m["witness_id"]) for m in payload["markers"]}
    for m in payload["markers"]:
        writer.writerow([m["type"], sig.get(m["witness_id"], "?"),
                         m["orig"], m.get("note", ""),
                         m.get("anchor_column_index")])
    return buf.getvalue()


def _export_md(payload, witnesses):
    lines = [f"# 校勘記：{payload['passage_title']}", ""]
    lines.append(f"- Run: `{payload['run_id']}`；引擎：{payload['engine']}；"
                 f"標點參與對齊：{'是' if payload['include_punctuation'] else '否'}")
    lines.append("- 見本來源：")
    for w in payload["witness_sources"]:
        lines.append(f"    - **{w['siglum']}** — {w['source']}（{w['era']}）")
    lines.append("")
    lines.append("| 欄 | 自動建議 | 人工判斷 | 理由 | "
                 + " | ".join(w.siglum for w in witnesses) + " |")
    lines.append("|---|---|---|---|" + "---|" * len(witnesses))
    for col in payload["columns"]:
        cells = " | ".join(
            (r["orig"] if r["present"] else "—").replace("|", "／")
            for r in col["readings"])
        lines.append(
            f"| {col['column_index']} "
            f"| {KIND_LABEL.get(col['auto_suggested_kind'], col['auto_suggested_kind'])} "
            f"| {col['human_judgment'] or '（待判斷）'} "
            f"| {col['rationale']} | {cells} |")
    lines.append("")
    lines.append("## 記號（不混入文字差異）")
    for m in payload["markers"]:
        label = {"lacuna": "缺葉", "blank": "空白正文",
                 "annotation": "批注", "insertion": "插入"}.get(m["type"], m["type"])
        lines.append(f"- [{label}] {m['orig']}"
                     + (f"（{m['note']}）" if m.get("note") else "")
                     + f" —— 錨定於第 {m.get('anchor_column_index')} 欄之後")
    return "\n".join(lines)
