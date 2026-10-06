# -*- coding: utf-8 -*-
"""轉錄記號體系（parser）。

原轉錄純文字中使用以下顯式記號，解析後得到強類型 token：

    〖缺葉〗        缺葉（整葉脫失，一個跨段佔位記號）
    【空白】        空白正文（紙面留白／漫漶成段，不同於缺葉）
    □               未知字（字位尚存而字形不可識，保留原形，永不猜補）
    〔批：……〕      批注（眉批、旁注、夾注），錨定於前一正文之字之後
    〔插：……〕      插入片段（鈔補／他本多餘之文），同樣錨定相鄰位置
    〔眉：……〕      批注的別寫

其餘字符中，標點自成 PUNCT token；普通漢字為 TEXT token。
記號一律不進入正文比對序列，只記下 ``anchor_after``（所貼鄰的
前一個正文 token），因此它們既不會被誤判為脫文，也不會在調整
對齊時丟失位置。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------- 記號定義

LACUNA_MARK = "〖缺葉〗"
BLANK_MARK = "【空白】"
UNKNOWN_GLYPH = "□"

# 批注／插入：〔批：xxx〕〔插：xxx〕〔眉：xxx〕〔注：xxx〕
_MARKER_RE = re.compile(r"〔(批|插|眉|注)：([^〕]*)〕")
# 顯式佔位記號（跨段）
_GAP_MARK = {"〖缺葉〗": "lacuna", "【空白】": "blank"}

# 標點：常見中式與引號；句讀點也算
_PUNCT_CHARS = "，。、；：？！．·…—–－「」『』《》〈〉“”‘’（）()【】〖〗,.?!;:"
_PUNCT_RE = re.compile(rf"[{re.escape(_PUNCT_CHARS)}]")

ANNOTATION_PREFIXES = {"批", "眉", "注"}
INSERTION_PREFIXES = {"插"}


@dataclass
class ParsedToken:
    orig: str
    type: str                  # text / punct / lacuna / blank / annotation / insertion / unknown
    position: int
    note: str = ""
    anchor_after_position: int | None = None  # 同見本內前一正文 token 的 position


@dataclass
class TokenizeResult:
    tokens: list[ParsedToken] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def tokenize(text: str) -> TokenizeResult:
    """把原轉錄切成有序 token。

    掃描指針優先識別長記號（〖缺葉〗等）與〔…〕標注，
    其餘逐字符分類。position 是連續序號，供錨定與還原。
    """
    result = TokenizeResult()
    i = 0
    pos = 0
    last_text_pos: int | None = None  # 最近一個正文（text/unknown/punct?）位置

    # 只以正文/未知字作為批注貼鄰錨點；標點不單獨作為「相鄰正文」
    n = len(text)
    while i < n:
        ch = text[i]

        # 跨段佔位記號
        matched_gap = False
        for mark, kind in _GAP_MARK.items():
            if text.startswith(mark, i):
                result.tokens.append(ParsedToken(
                    orig=mark, type=kind, position=pos,
                    anchor_after_position=last_text_pos))
                pos += 1
                i += len(mark)
                matched_gap = True
                break
        if matched_gap:
            continue

        # 批注／插入
        m = _MARKER_RE.match(text, i)
        if m:
            kind = ("insertion" if m.group(1) in INSERTION_PREFIXES
                    else "annotation")
            result.tokens.append(ParsedToken(
                orig=m.group(0), type=kind, position=pos,
                note=m.group(2).strip(),
                anchor_after_position=last_text_pos))
            pos += 1
            i += m.end() - m.start()
            continue

        # 未知字：字位存在、字形未知。獨立一類，絕不猜補。
        if ch == UNKNOWN_GLYPH:
            result.tokens.append(ParsedToken(
                orig=ch, type="unknown", position=pos,
                anchor_after_position=last_text_pos))
            last_text_pos = pos
            pos += 1
            i += 1
            continue

        if _PUNCT_RE.match(ch):
            result.tokens.append(ParsedToken(
                orig=ch, type="punct", position=pos))
            pos += 1
            i += 1
            continue

        if ch.isspace():
            i += 1
            continue

        # 普通正文
        result.tokens.append(ParsedToken(
            orig=ch, type="text", position=pos,
            anchor_after_position=None))
        last_text_pos = pos
        pos += 1
        i += 1

    return result
