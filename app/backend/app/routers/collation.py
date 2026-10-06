from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import exporter
from ..database import get_db
from ..models import AlignmentColumn, CollationRun, Witness
from ..overrides import OverrideError, apply_override
from ..schemas import CollateRequest, JudgmentIn, OverrideIn, RunOut
from ..services import VARIANT_TYPES, VARIANT_TYPE_LABELS, parse_witness, load_rules, run_collation
from ..transcription import parse_transcription

router = APIRouter(tags=["collation"])


def _serialize_run(db: Session, run: CollationRun) -> dict:
    columns = list(db.scalars(
        select(AlignmentColumn).where(AlignmentColumn.run_id == run.id)
        .order_by(AlignmentColumn.position)
    ))
    witnesses = list(db.scalars(
        select(Witness).where(Witness.passage_id == run.passage_id).order_by(Witness.sort_order)
    ))
    # 批注（插入片段）：重新从原转录解析（只读），带相邻锚点
    rules = load_rules(db, run.passage_id)
    annotations = []
    for w in witnesses:
        for t in parse_witness(w, rules):
            if t.kind == "annotation":
                annotations.append(t.to_dict())
    return {
        "id": run.id, "passage_id": run.passage_id, "engine": run.engine,
        "include_punctuation": run.include_punctuation, "status": run.status,
        "note": run.note, "created_at": run.created_at,
        "columns": [
            {
                "id": c.id, "position": c.position, "tokens": c.tokens,
                "suggested_type": c.suggested_type, "suggested_reason": c.suggested_reason,
                "researcher_type": c.researcher_type, "researcher_note": c.researcher_note,
                "confirmed": c.confirmed,
            }
            for c in columns
        ],
        "annotations": annotations,
        "overrides": [
            {"id": o.id, "action": o.action, "payload": o.payload,
             "author": o.author, "created_at": o.created_at}
            for o in sorted(run.overrides, key=lambda x: x.id)
        ],
    }


@router.get("/variant-types")
def variant_types():
    return [{"value": v, "label": VARIANT_TYPE_LABELS[v]} for v in VARIANT_TYPES]


@router.post("/collations/run")
def create_run(body: CollateRequest, db: Session = Depends(get_db)):
    try:
        run = run_collation(db, body.passage_id, body.include_punctuation, body.witness_ids)
        db.commit()
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _serialize_run(db, run)


@router.get("/passages/{pid}/runs")
def list_runs(pid: int, db: Session = Depends(get_db)):
    runs = list(db.scalars(
        select(CollationRun).where(CollationRun.passage_id == pid).order_by(CollationRun.id.desc())
    ))
    return [{"id": r.id, "engine": r.engine,
             "include_punctuation": r.include_punctuation, "status": r.status,
             "note": r.note, "created_at": r.created_at} for r in runs]


@router.get("/runs/{rid}")
def get_run(rid: int, db: Session = Depends(get_db)):
    run = db.get(CollationRun, rid)
    if run is None:
        raise HTTPException(404, "run not found")
    return _serialize_run(db, run)


@router.put("/columns/{cid}/judgment")
def set_judgment(cid: int, body: JudgmentIn, db: Session = Depends(get_db)):
    """研究者结论。只写 researcher_*，绝不动 suggested_*。"""
    col = db.get(AlignmentColumn, cid)
    if col is None:
        raise HTTPException(404, "column not found")
    if body.researcher_type is not None and body.researcher_type not in VARIANT_TYPES:
        raise HTTPException(400, f"受控词表之外的类型：{body.researcher_type}")
    col.researcher_type = body.researcher_type
    col.researcher_note = body.researcher_note
    col.confirmed = body.confirmed
    db.commit()
    return {"ok": True, "column_id": cid,
            "researcher_type": col.researcher_type, "confirmed": col.confirmed}


@router.post("/runs/{rid}/overrides")
def add_override(rid: int, body: OverrideIn, db: Session = Depends(get_db)):
    if db.get(CollationRun, rid) is None:
        raise HTTPException(404, "run not found")
    try:
        ov = apply_override(db, rid, body.action, body.payload, body.author)
        db.commit()
    except OverrideError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, "override_id": ov.id, "run": _serialize_run(db, db.get(CollationRun, rid))}


@router.get("/runs/{rid}/export.{fmt}")
def export_run(rid: int, fmt: str, db: Session = Depends(get_db)):
    try:
        if fmt == "json":
            return Response(
                exporter.export_json(db, rid), media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="collation_{rid}.json"'},
            )
        if fmt == "csv":
            return Response(
                exporter.export_csv(db, rid),
                media_type="text/csv; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="collation_{rid}.csv"'},
            )
        if fmt in ("xml", "tei"):
            return Response(
                exporter.export_tei(db, rid), media_type="application/xml",
                headers={"Content-Disposition": f'attachment; filename="collation_{rid}.xml"'},
            )
    except KeyError:
        raise HTTPException(404, "run not found")
    raise HTTPException(400, "fmt 仅支持 json / csv / xml")
