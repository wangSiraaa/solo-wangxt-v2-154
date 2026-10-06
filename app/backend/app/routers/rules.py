from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import NormalizationRule, Passage
from ..schemas import RuleIn, RuleOut

router = APIRouter(prefix="/rules", tags=["rules"])


@router.get("/passage/{pid}", response_model=list[RuleOut])
def list_rules(pid: int, db: Session = Depends(get_db)):
    return list(db.query(NormalizationRule)
                .filter((NormalizationRule.passage_id == pid)
                        | (NormalizationRule.passage_id.is_(None)))
                .order_by(NormalizationRule.priority.desc(), NormalizationRule.id))


@router.post("/passage/{pid}", response_model=RuleOut)
def create_rule(pid: int, body: RuleIn, db: Session = Depends(get_db)):
    if db.get(Passage, pid) is None:
        raise HTTPException(404, "passage not found")
    if body.witness_id is not None:
        from ..models import Witness
        if db.get(Witness, body.witness_id) is None or db.get(Witness, body.witness_id).passage_id != pid:
            raise HTTPException(400, "witness_id 不属于该 passage")
    r = NormalizationRule(passage_id=pid, **body.model_dump())
    db.add(r)
    db.commit()
    return r


@router.patch("/{rid}", response_model=RuleOut)
def update_rule(rid: int, body: RuleIn, db: Session = Depends(get_db)):
    r = db.get(NormalizationRule, rid)
    if r is None:
        raise HTTPException(404, "rule not found")
    for k, v in body.model_dump().items():
        setattr(r, k, v)
    db.commit()
    return r


@router.delete("/{rid}")
def delete_rule(rid: int, db: Session = Depends(get_db)):
    r = db.get(NormalizationRule, rid)
    if r is None:
        raise HTTPException(404, "rule not found")
    db.delete(r)
    db.commit()
    return {"ok": True}
