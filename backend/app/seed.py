# -*- coding: utf-8 -*-
"""自制展示樣本（虛構文本，便於演示各類校勘現象）。

《松窗讀書記》（擬題）三個見本分別埋入：

* 甲本（舊鈔本）：異體字「徳／爲／峯」、未知字「□」、批注〔批：…〕、缺葉〖缺葉〗；
* 乙本（初刻本）：規範字形、斷句不同、空白正文【空白】（與甲本缺葉位置相應）；
* 丙本（續鈔本）：重複短句「勿自欺也」重出、插入片段〔插：…〕、又一種斷句。

標點只在 include_punctuation 時入列，可直接對比「有／無標點對齊」。
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import NormalizationRule, Passage
from .services import create_witness

PASSAGE_TITLE = "松窗讀書記·節錄（擬）"
PASSAGE_REF = "擬古·松窗/一"

BASE = "學者讀書先須正心為德不欺闇室窮理以盡性至於夜分乃臥"

# 甲本：舊鈔本。異體字、□、批注、缺葉
JIA = ("學者讀書，先須正心爲徳；〔批：「爲徳」二字朱筆重點〕"
       "不欺闇室，窮理以盡性。〖缺葉〗至於夜半乃臥，□者慎之。"
       "勿自欺也。")

# 乙本：初刻本。規範字、不同斷句、空白正文（非缺葉），無批注
YI = ("學者讀書，先須正心，為德不欺，闇室窮理，以盡其性。"
      "【空白】至於夜半乃臥，學者慎之，勿自欺也。")

# 丙本：續鈔本。重複短句、插入、異體、另一種斷句
BING = ("學者讀書。先須正心，為徳不欺闇室，窮理以盡性。"
        "至於夜分乃臥，勿自欺也，勿自欺也。〔插：一本此下別有「君子慎獨」四字〕"
        "學者其勉之。")

RULES = [
    ("爲", "為", "舊鈔用字統一為通行形"),
    ("徳", "德", "異體「徳」→「德」，原字形仍保留"),
]


def seed_if_empty(db: Session) -> bool:
    if db.query(Passage).count() > 0:
        return False
    p = Passage(title=PASSAGE_TITLE, reference=PASSAGE_REF, base_text=BASE)
    db.add(p)
    db.flush()

    for pattern, repl, note in RULES:
        db.add(NormalizationRule(passage_id=p.id, pattern=pattern,
                                 replacement=repl, note=note))

    create_witness(db, p.id, _w("甲本", "某氏舊鈔本（虛構）", "擬元舊鈔",
                                JIA, 0))
    create_witness(db, p.id, _w("乙本", "松窗初刻本（虛構）", "擬明初刻",
                                YI, 1))
    create_witness(db, p.id, _w("丙本", "後人續鈔本（虛構）", "擬明中續鈔",
                                BING, 2))
    db.commit()
    return True


def _w(siglum, source, era, text, order):
    from .schemas import WitnessIn
    return WitnessIn(siglum=siglum, source=source, era=era,
                     raw_transcription=text, sort_order=order,
                     notes="自制樣本，文字純屬虛構")
