# -*- coding: utf-8 -*-
"""規範化測試：原字形與比對形分離、未知字不被規則吞併。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.collate.normalization import norm_for_token
from app.models import TokenType


def test_variant_maps_but_unknown_stays():
    charmap = {"徳": "德"}
    assert norm_for_token("徳", TokenType.TEXT, charmap) == "德"
    # 沒有規則的字維持原樣
    assert norm_for_token("爲", TokenType.TEXT, charmap) == "爲"


def test_gap_and_markers_have_empty_norm():
    assert norm_for_token("〖缺葉〗", TokenType.LACUNA, {}) == ""
    assert norm_for_token("【空白】", TokenType.BLANK, {}) == ""
    assert norm_for_token("〔批：x〕", TokenType.ANNOTATION, {}) == ""
    assert norm_for_token("〔插：x〕", TokenType.INSERTION, {}) == ""


def test_unknown_norm_never_becomes_a_guess():
    # 即使存在看似相關的規則，未知字保持 □
    assert norm_for_token("□", TokenType.UNKNOWN, {"□": "德"}) == "□"


def test_punct_norm_is_itself():
    assert norm_for_token("，", TokenType.PUNCT, {}) == "，"
