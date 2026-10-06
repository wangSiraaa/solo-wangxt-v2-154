# -*- coding: utf-8 -*-
"""HTTP API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import services
from ..database import get_db
from ..models import CollationRun, Passage, Witness
from ..schemas import (
    AdjustIn,
    CollateIn,
    JudgmentIn,
    JudgmentOut,
    PassageIn,
    PassageOut,
    PreviewIn,
    RuleIn,
    RuleOut,
    RunOut,
    WitnessIn,
    WitnessOut,
)

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- 段落

@router.post("/passages", response_model=PassageOut, tags=["passages"])
def create_passage(data: PassageIn, db: Session = Depends(get_db)):
    p = Passage(**data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.get("/passages", response_model=list[PassageOut], tags=["passages"])
def list_passages(db: Session = Depends(get_db)):
    return db.query(Passage).order_by(Passage.created_at.desc()).all()


@router.get("/passages/{pid}", response_model=PassageOut, tags=["passages"])
def get_passage(pid: str, db: Session = Depends(get_db)):
    p = db.get(Passage, pid)
    if p is None:
        raise HTTPException(404, "passage not found")
    return p


# ---------------------------------------------------------------- 見本

@router.post("/passages/{pid}/witnesses",
             response_model=WitnessOut, tags=["witnesses"])
def add_witness(pid: str, data: WitnessIn, db: Session = Depends(get_db)):
    if db.get(Passage, pid) is None:
        raise HTTPException(404, "passage not found")
    w = services.create_witness(db, pid, data)
    db.commit()
    db.refresh(w)
    return w


@router.patch("/witnesses/{wid}/transcription",
              response_model=WitnessOut, tags=["witnesses"])
def edit_transcription(wid: str, payload: dict,
                       db: Session = Depends(get_db)):
    w = db.get(Witness, wid)
    if w is None:
        raise HTTPException(404, "witness not found")
    text = payload.get("raw_transcription")
    if not isinstance(text, str):
        raise HTTPException(422, "raw_transcription 必須是字串")
    services.update_transcription(
        db, w, text, changed_by=payload.get("changed_by", "researcher"))
    db.commit()
    db.refresh(w)
    return w


# ---------------------------------------------------------------- 規則

@router.post("/passages/{pid}/rules",
             response_model=RuleOut, tags=["rules"])
def add_rule(pid: str, data: RuleIn, db: Session = Depends(get_db)):
    if db.get(Passage, pid) is None:
        raise HTTPException(404, "passage not found")
    r = services  # noqa: F841
    from ..models import NormalizationRule
    rule = NormalizationRule(passage_id=pid, **data.model_dump())
    db.add(rule)
    # 規則變更：現有見本依新規則重建 norm（orig 不動）
    db.flush()
    for w in db.query(Witness).filter(Witness.passage_id == pid).all():
        services.retokenize_witness(db, w)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/passages/{pid}/rules",
            response_model=list[RuleOut], tags=["rules"])
def list_rules(pid: str, db: Session = Depends(get_db)):
    from ..models import NormalizationRule
    return (db.query(NormalizationRule)
            .filter(NormalizationRule.passage_id == pid).all())


# ---------------------------------------------------------------- 預覽/對齊

@router.post("/preview", tags=["collation"])
def preview(data: PreviewIn, db: Session = Depends(get_db)):
    return {"tokens": services.preview_tokens(
        db, data.raw_transcription, data.passage_id)}


@router.post("/collate", response_model=RunOut, tags=["collation"])
def collate(data: CollateIn, db: Session = Depends(get_db)):
    try:
        run = services.collate(
            db, data.passage_id, data.include_punctuation,
            use_collatex=data.use_collatex, revision_note=data.revision_note)
    except KeyError:
        raise HTTPException(404, "passage not found")
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    db.commit()
    db.refresh(run)
    return run


@router.get("/passages/{pid}/runs",
            response_model=list[RunOut], tags=["collation"])
def list_runs(pid: str, db: Session = Depends(get_db)):
    return (db.query(CollationRun)
            .filter(CollationRun.passage_id == pid)
            .order_by(CollationRun.created_at.desc()).all())


@router.get("/runs/{rid}", response_model=RunOut, tags=["collation"])
def get_run(rid: str, db: Session = Depends(get_db)):
    run = db.get(CollationRun, rid)
    if run is None:
        raise HTTPException(404, "run not found")
    return run


# ---------------------------------------------------------------- 判斷/調整

@router.put("/runs/{rid}/judgments",
            response_model=JudgmentOut, tags=["judgments"])
def put_judgment(rid: str, data: JudgmentIn,
                 db: Session = Depends(get_db)):
    try:
        j = services.set_judgment(db, rid, data)
    except KeyError:
        raise HTTPException(404, "run not found")
    except IndexError:
        raise HTTPException(422, "column_index 超出範圍")
    db.commit()
    db.refresh(j)
    return j


@router.post("/adjust", response_model=RunOut, tags=["collation"])
def adjust(data: AdjustIn, db: Session = Depends(get_db)):
    try:
        run = services.adjust(db, data)
    except KeyError:
        raise HTTPException(404, "run not found")
    except (ValueError, IndexError) as exc:
        raise HTTPException(422, str(exc))
    db.commit()
    db.refresh(run)
    return run


# ---------------------------------------------------------------- 匯出

@router.get("/runs/{rid}/export", tags=["export"])
def export(rid: str, fmt: str = Query("json", pattern="^(json|csv|md)$"),
           db: Session = Depends(get_db)):
    try:
        media, body = services.export_run(db, rid, fmt)
    except KeyError:
        raise HTTPException(404, "run not found")
    filename = f"collation-{rid[:8]}.{ 'md' if fmt == 'md' else fmt}"
    return Response(content=body, media_type=media,
                    headers={"Content-Disposition":
                             f'attachment; filename="{filename}"'})
