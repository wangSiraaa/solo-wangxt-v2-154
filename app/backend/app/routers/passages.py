from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Passage, Witness
from ..schemas import PassageIn, PassageOut, WitnessIn, WitnessOut
from ..transcription import parse_transcription

router = APIRouter(prefix="/passages", tags=["passages"])


@router.post("", response_model=PassageOut)
def create_passage(body: PassageIn, db: Session = Depends(get_db)):
    p = Passage(title=body.title, description=body.description)
    db.add(p)
    db.flush()
    for i, w in enumerate(body.witnesses):
        db.add(Witness(
            passage_id=p.id, siglum=w.siglum, label=w.label,
            source_note=w.source_note, raw_transcription=w.raw_transcription,
            sort_order=w.sort_order or i,
        ))
    db.commit()
    return db.get(Passage, p.id)


@router.get("", response_model=list[PassageOut])
def list_passages(db: Session = Depends(get_db)):
    return list(db.scalars(select(Passage).order_by(Passage.id)))


@router.get("/{pid}", response_model=PassageOut)
def get_passage(pid: int, db: Session = Depends(get_db)):
    p = db.get(Passage, pid)
    if p is None:
        raise HTTPException(404, "passage not found")
    return p


@router.post("/{pid}/witnesses", response_model=WitnessOut)
def add_witness(pid: int, body: WitnessIn, db: Session = Depends(get_db)):
    if db.get(Passage, pid) is None:
        raise HTTPException(404, "passage not found")
    w = Witness(passage_id=pid, **body.model_dump())
    db.add(w)
    db.commit()
    return w


@router.get("/{pid}/parse")
def preview_parse(pid: int, db: Session = Depends(get_db)):
    """预览原转录解析结果（原字形 / 规范前的结构标记）。"""
    ws = list(db.scalars(select(Witness).where(Witness.passage_id == pid)))
    return {
        w.siglum: [t.to_dict() for t in parse_transcription(w.raw_transcription, w.id)]
        for w in ws
    }
