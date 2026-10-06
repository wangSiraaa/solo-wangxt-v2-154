# -*- coding: utf-8 -*-
"""規範化：原字形 → 比對用規範形。

兩者分欄保存，規則只作用於 ``norm``：

* 研究者自訂的字符對照規則（徳→德、爲→為、峯→峰……）；
* 缺葉、空白記號不參與比對，``norm`` 為空字串；
* 未知字「□」保持「□」——它是一個*未知的字位*，系統絕不替它猜字；
* 標點 token 的 norm 即原標點，由 include_punctuation 決定是否入列。

可選開啟 Unicode 兼容展開（NFKC，例如全形／兼容異體），
預設關閉，避免把校勘上有意義的差異悄悄抹平。
"""
from __future__ import annotations

import unicodedata

from sqlalchemy.orm import Session

from ..models import NormalizationRule, TokenType


def load_char_map(session: Session, passage_id: str) -> dict[str, str]:
    rules = (session.query(NormalizationRule)
             .filter(NormalizationRule.passage_id == passage_id,
                     NormalizationRule.enabled.is_(True))
             .order_by(NormalizationRule.pattern)
             .all())
    charmap: dict[str, str] = {}
    for rule in rules:
        # pattern 可寫成「徳」或「徳=>德」式，這裡以兩欄為準；
        # 若 pattern 含逗號則視為多原形共享一個規範形
        keys = [k.strip() for k in re_split(rule.pattern) if k.strip()]
        for k in keys:
            charmap[k] = rule.replacement.strip()
    return charmap


def re_split(s: str) -> list[str]:
    import re
    return re.split(r"[,，、/／]", s)


def normalize_char(ch: str, charmap: dict[str, str],
                   use_nfkc: bool = False) -> str:
    if ch in charmap:
        return charmap[ch]
    if use_nfkc:
        return unicodedata.normalize("NFKC", ch)
    return ch


def norm_for_token(orig: str, ttype: TokenType,
                   charmap: dict[str, str],
                   use_nfkc: bool = False) -> str:
    """依 token 類型產生比對形式。"""
    if ttype in (TokenType.LACUNA, TokenType.BLANK):
        return ""                       # 佔位不參與文字比對
    if ttype in (TokenType.ANNOTATION, TokenType.INSERTION):
        return ""                       # 批注/插入不進正文行列
    if ttype is TokenType.UNKNOWN:
        return UNKNOWN_NORM             # 保持未知，不猜補
    if ttype is TokenType.PUNCT:
        return orig
    # TEXT：逐字規範（古籍比對粒度為字符）
    return "".join(normalize_char(c, charmap, use_nfkc) for c in orig)


UNKNOWN_NORM = "□"
