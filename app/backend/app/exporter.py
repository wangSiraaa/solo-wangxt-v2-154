"""导出校勘成果。

* JSON：机器可读的完整关系（见本来源、原转录、规则快照、列、自动建议、人工判断、调整记录）
* CSV：校勘条目表（每列一行，含来源见本与自动/人工两套结论）
* TEI 风 XML：<app>/<rdg> 结构，结构标记用专门的 <lacunaEnd/> 等表达，
  未知字保留 <g type='unknown'>，绝不转写成猜测字。

导出只读取数据，不改动任何原转录。
"""
from __future__ import annotations

import csv
import io
import json
from xml.sax.saxutils import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import AlignmentColumn, CollationRun, ManualOverride, Passage, Witness
from .services import VARIANT_TYPE_LABELS


def _gather(db: Session, run_id: int) -> dict:
    run = db.get(CollationRun, run_id)
    if run is None:
        raise KeyError("run not found")
    passage = db.get(Passage, run.passage_id)
    witnesses = list(db.scalars(
        select(Witness).where(Witness.passage_id == run.passage_id).order_by(Witness.sort_order)
    ))
    columns = list(db.scalars(
        select(AlignmentColumn).where(AlignmentColumn.run_id == run_id)
        .order_by(AlignmentColumn.position)
    ))
    overrides = list(db.scalars(
        select(ManualOverride).where(ManualOverride.run_id == run_id).order_by(ManualOverride.id)
    ))
    return {"run": run, "passage": passage, "witnesses": witnesses,
            "columns": columns, "overrides": overrides}


def export_json(db: Session, run_id: int) -> str:
    g = _gather(db, run_id)
    run, passage = g["run"], g["passage"]
    payload = {
        "passage": {
            "id": passage.id, "title": passage.title, "description": passage.description,
        },
        "witnesses": [
            {"id": w.id, "siglum": w.siglum, "label": w.label,
             "source_note": w.source_note,
             "raw_transcription": w.raw_transcription}
            for w in g["witnesses"]
        ],
        "collation": {
            "run_id": run.id, "engine": run.engine,
            "include_punctuation": run.include_punctuation,
            "note": run.note, "created_at": run.created_at.isoformat(),
            "rules_snapshot": run.rules_snapshot,
        },
        "apparatus": [
            {
                "position": c.position,
                "readings": {
                    str(wid): (None if tok is None else {
                        "kind": tok["kind"], "text": tok["display"],
                        "matched_norm": tok.get("norm", ""),
                        "note": tok.get("note", ""),
                    })
                    for wid, tok in c.tokens.items()
                },
                "auto_suggestion": {
                    "type": c.suggested_type,
                    "label": VARIANT_TYPE_LABELS.get(c.suggested_type, c.suggested_type),
                    "reason": c.suggested_reason,
                },
                "researcher_judgment": {
                    "type": c.researcher_type,
                    "label": VARIANT_TYPE_LABELS.get(c.researcher_type, c.researcher_type)
                             if c.researcher_type else None,
                    "note": c.researcher_note, "confirmed": c.confirmed,
                },
            }
            for c in g["columns"]
        ],
        "manual_overrides": [
            {"id": o.id, "action": o.action, "payload": o.payload,
             "author": o.author, "created_at": o.created_at.isoformat()}
            for o in g["overrides"]
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_csv(db: Session, run_id: int) -> str:
    g = _gather(db, run_id)
    wmap = {w.id: w for w in g["witnesses"]}
    buf = io.StringIO()
    buf.write("﻿")  # Excel 友好 BOM
    writer = csv.writer(buf)
    header = ["列位"]
    for w in g["witnesses"]:
        header += [f"{w.siglum}字形", f"{w.siglum}类型", f"{w.siglum}来源"]
    header += ["自动建议", "建议理由", "人工判断", "人工按语", "已确认"]
    writer.writerow(header)
    for c in g["columns"]:
        row = [c.position]
        for w in g["witnesses"]:
            tok = c.tokens.get(str(w.id))
            if tok is None:
                row += ["—(无文)", "", w.source_note or w.siglum]
            else:
                row += [tok["display"], tok["kind"], w.source_note or w.siglum]
        row += [
            VARIANT_TYPE_LABELS.get(c.suggested_type, c.suggested_type or ""),
            c.suggested_reason,
            VARIANT_TYPE_LABELS.get(c.researcher_type, c.researcher_type or ""),
            c.researcher_note, "是" if c.confirmed else "",
        ]
        writer.writerow(row)
    return buf.getvalue()


def export_tei(db: Session, run_id: int) -> str:
    g = _gather(db, run_id)
    run, passage = g["run"], g["passage"]
    out: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<TEI xmlns="http://www.tei-c.org/ns/1.0">',
        "<teiHeader><fileDesc>",
        f"<titleStmt><title>{escape(passage.title)}</title></titleStmt>",
        "<sourceDesc>",
    ]
    for w in g["witnesses"]:
        out.append(
            f'<listWit><witness xml:id="w{w.id}">{escape(w.siglum)}'
            f'<note type="source">{escape(w.source_note)}</note></witness></listWit>'
        )
    out.append("</sourceDesc></fileDesc>")
    out.append(
        f'<projectDesc><p>对齐引擎：{escape(run.engine)}；'
        f'标点参与对齐：{"是" if run.include_punctuation else "否"}；'
        f'自动建议不构成定本结论。</p></projectDesc>'
    )
    out.append("</teiHeader><text><body><ab>")
    for c in g["columns"]:
        readings = []
        for wid, tok in c.tokens.items():
            w = next((x for x in g["witnesses"] if str(x.id) == str(wid)), None)
            rid = f"#w{wid}"
            if tok is None:
                readings.append(f'<rdg wit="{rid}" type="absent"/>')
            elif tok["kind"] == "lacuna":
                readings.append(
                    f'<rdg wit="{rid}" type="lacuna"><lacuna reason="missing-leaf"/></rdg>'
                )
            elif tok["kind"] == "blank":
                readings.append(f'<rdg wit="{rid}" type="blank"><space/></rdg>')
            elif tok["kind"] == "unknown":
                readings.append(f'<rdg wit="{rid}" type="illegible"><g type="unknown">□</g></rdg>')
            elif tok["kind"] == "annotation":
                readings.append(f'<note type="annotation" wit="{rid}">{escape(tok["display"])}</note>')
            else:
                attrs = f' wit="{rid}"'
                if tok.get("norm") and tok["norm"] != tok["display"]:
                    attrs += f' norm="{escape(tok["norm"])}"'
                readings.append(f"<rdg{attrs}>{escape(tok['display'])}</rdg>")
        judge = ""
        if c.researcher_type:
            judge = f'<note type="judgment" resp="researcher">{escape(c.researcher_type)} {escape(c.researcher_note)}</note>'
        auto = f'<note type="auto-suggestion">{escape(c.suggested_type or "")}</note>'
        out.append(f"<app n=\"{c.position}\">{''.join(readings)}{auto}{judge}</app>")
    out.append("</ab></body></text></TEI>")
    return "\n".join(out)
