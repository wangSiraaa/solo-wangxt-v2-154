# -*- coding: utf-8 -*-
"""比對器單元測試：異體對齊、重複短句、斷句、缺葉/空白分類。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.collate.aligner import align_witnesses
from app.collate.normalization import norm_for_token
from app.collate.tokenizer import tokenize
from app.models import Token, TokenType


def _tokens(wid, text, charmap=None):
    charmap = charmap or {}
    out = []
    for pt in tokenize(text).tokens:
        tt = {"text": TokenType.TEXT, "punct": TokenType.PUNCT,
              "lacuna": TokenType.LACUNA, "blank": TokenType.BLANK,
              "annotation": TokenType.ANNOTATION,
              "insertion": TokenType.INSERTION,
              "unknown": TokenType.UNKNOWN}[pt.type]
        out.append(Token(id=f"{wid}-{pt.position}", witness_id=wid,
                         position=pt.position, orig=pt.orig,
                         norm=norm_for_token(pt.orig, tt, charmap),
                         type=tt, note=pt.note,
                         anchor_after=(str(pt.anchor_after_position)
                                       if pt.anchor_after_position is not None
                                       else None)))
    return out


def _run(texts, punct=False, charmap=None):
    wids = list(texts)
    wt = {wid: _tokens(wid, texts[wid], charmap) for wid in wids}
    res = align_witnesses(wt, wids, include_punctuation=punct)
    return res, wt


def test_variant_forms_align_via_normalization():
    res, _ = _run({"A": "爲徳", "B": "為德"},
                  charmap={"爲": "為", "徳": "德"})
    kinds = [c["suggested_kind"] for c in res["columns"]]
    assert kinds == ["variant_form", "variant_form"]
    # 原字形仍在
    assert res["columns"][0]["cells"]["A"]["orig"] == "爲"
    assert res["columns"][0]["cells"]["A"]["norm"] == "為"


def test_repeated_short_phrase_not_misaligned():
    # B 把「勿自欺也」重複一次，A 僅一次：兩本的首見應同欄
    res, _ = _run({"A": "臥勿自欺也終",
                   "B": "臥勿自欺也勿自欺也終"})
    cols = res["columns"]
    # 找出 A/B 皆有字且 norm 相同的欄
    def shared(char):
        return [c for c in cols
                if all(c["cells"][w] and c["cells"][w]["norm"] == char
                       for w in ("A", "B"))]
    for ch in "勿自欺也":
        assert shared(ch), f"{ch} 應在兩本同欄對齊"
    # B 的第二輪「勿自欺也」應有 A 為空的欄
    b_only = sum(1 for c in cols
                 if c["cells"]["A"] is None and c["cells"]["B"] is not None)
    assert b_only == 4


def test_different_sentence_breaks_only_show_with_punctuation():
    texts = {"A": "學者讀書，先須正心",
             "B": "學者讀書。先須正心"}
    no_p, _ = _run(texts, punct=False)
    assert all(c["cells"]["A"] and c["cells"]["B"]
               for c in no_p["columns"])          # 不計標點時完全同欄
    with_p, _ = _run(texts, punct=True)
    assert any(c["suggested_kind"] == "punctuation"
               for c in with_p["columns"])


def test_lacuna_and_blank_are_distinct_markers():
    res, _ = _run({"A": "甲〖缺葉〗乙", "B": "甲【空白】乙"})
    mtypes = sorted(m["type"] for m in res["markers"])
    assert mtypes == ["blank", "lacuna"]
    # 缺葉/空白被蓋進欄位，其分類只能是 lacuna/blank，絕不能是脫文
    stamped_kinds = {
        c["suggested_kind"] for c in res["columns"]
        if any(cell and cell.get("type") in ("lacuna", "blank")
               for cell in c["cells"].values())
    }
    assert stamped_kinds <= {"lacuna", "blank"}


def test_annotation_and_insertion_do_not_become_omissions():
    res, _ = _run({"A": "爲德〔批：注意〕不欺",
                   "B": "爲德不欺〔插：補文〕"})
    # 正文欄位中不應出現批注/插入的內文
    for c in res["columns"]:
        for cell in c["cells"].values():
            if cell:
                assert cell["type"] in ("text", "unknown", "punct")
    m = {x["type"]: x for x in res["markers"]}
    assert "annotation" in m and "insertion" in m
    # 錨點存在
    assert m["annotation"]["anchor_column_index"] is not None


def test_unknown_glyph_only_matches_unknown():
    res, _ = _run({"A": "□者", "B": "學者"})
    # □ 與 學 不應被判 same
    box_col = next(c for c in res["columns"]
                   if any(cell and cell["type"] == "unknown"
                          for cell in c["cells"].values()))
    assert box_col["suggested_kind"] != "same"


def test_identical_text_all_same():
    res, _ = _run({"A": "讀書正心", "B": "讀書正心", "C": "讀書正心"})
    assert all(c["suggested_kind"] == "same" for c in res["columns"])
