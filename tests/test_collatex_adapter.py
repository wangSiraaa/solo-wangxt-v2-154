# -*- coding: utf-8 -*-
"""CollateX 適配層測試：用假 HTTP client，不需真服務。"""
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.collate.collatex_client import CollateXError, run_collatex
from app.collate.normalization import norm_for_token
from app.collate.tokenizer import tokenize
from app.models import Token, TokenType


def _tokens(text):
    out = []
    for pt in tokenize(text).tokens:
        if pt.type not in ("text", "unknown"):
            continue
        tt = TokenType.UNKNOWN if pt.type == "unknown" else TokenType.TEXT
        out.append(Token(id=f"t{pt.position}", witness_id="w",
                         position=pt.position, orig=pt.orig,
                         norm=norm_for_token(pt.orig, tt, {}), type=tt))
    return out


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload):
        self.payload = payload
        self.sent = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None):
        self.sent = {"url": url, "json": json}
        return FakeResponse(self.payload)


def _bundle():
    a = _tokens("爲德")
    for t in a:
        t.witness_id = "A"
    b = _tokens("為德")
    for t in b:
        t.witness_id = "B"
    return {"A": a, "B": b}, ["A", "B"]


def test_payload_uses_norm_and_table_shape_maps_back():
    bundle, order = _bundle()
    # CollateX table：兩行各兩欄；首欄用各自第 0 token 引用
    table = [
        [[{"_token_reference": "0"}], [{"_token_reference": "1"}]],
        [[{"_token_reference": "0"}], [{"_token_reference": "1"}]],
    ]
    fake = FakeClient({"table": table})
    res = run_collatex(fake, "http://x", bundle, order, False)
    # 送出去的 token 文字是 norm
    first = fake.sent["json"]["witnesses"][0]["tokens"][0]["t"]
    assert first == "爲"  # 無規則時 norm=orig
    # 映射回本機原字形
    col0 = res["columns"][0]["cells"]
    assert col0["A"]["orig"] == "爲" and col0["B"]["orig"] == "為"
    assert res["engine_detail"].startswith("collatex")


def test_service_error_raises_for_fallback():
    bundle, order = _bundle()

    class Boom:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None):
            raise httpx.ConnectError("connection refused")

    with pytest.raises(CollateXError):
        run_collatex(Boom(), "http://x", bundle, order, False)
