# -*- coding: utf-8 -*-
"""轉錄解析測試：異體字、缺葉、空白、批注、插入、未知字、標點互不混淆。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.collate.tokenizer import tokenize


def types_of(text):
    return [(t.orig, t.type, t.anchor_after_position)
            for t in tokenize(text).tokens]


def test_plain_text_and_punctuation():
    toks = tokenize("學者，讀書。").tokens
    assert [t.type for t in toks] == ["text", "text", "punct",
                                      "text", "text", "punct"]


def test_lacuna_is_its_own_type():
    toks = tokenize("甲〖缺葉〗乙").tokens
    lac = [t for t in toks if t.type == "lacuna"]
    assert len(lac) == 1
    assert lac[0].orig == "〖缺葉〗"
    # 缺葉錨定在前一正文「甲」之後
    assert lac[0].anchor_after_position == 0


def test_blank_differs_from_lacuna():
    toks = tokenize("甲【空白】乙").tokens
    kinds = {t.type for t in toks}
    assert "blank" in kinds and "lacuna" not in kinds
    blank = [t for t in toks if t.type == "blank"][0]
    assert blank.orig == "【空白】"


def test_annotation_anchors_to_preceding_text():
    toks = tokenize("爲徳〔批：重點〕不欺").tokens
    ann = [t for t in toks if t.type == "annotation"]
    assert len(ann) == 1
    assert ann[0].note == "重點"
    # 貼在「徳」(position 1) 之後，而非當成正文
    assert ann[0].anchor_after_position == 1
    assert "不" in [t.orig for t in toks if t.type == "text"]


def test_insertion_anchors_and_is_separate_type():
    toks = tokenize("勿自欺也〔插：別有四字〕學").tokens
    ins = [t for t in toks if t.type == "insertion"]
    assert len(ins) == 1
    assert ins[0].anchor_after_position == 3   # 貼在「也」後


def test_unknown_glyph_is_unknown_not_guessed():
    toks = tokenize("□者").tokens
    assert toks[0].type == "unknown"
    assert toks[0].orig == "□"
    # 未知字仍作為一個字位，後字正常
    assert toks[1].orig == "者"


def test_whitespace_ignored():
    assert [t.orig for t in tokenize(" 學\n者 ").tokens] == ["學", "者"]
