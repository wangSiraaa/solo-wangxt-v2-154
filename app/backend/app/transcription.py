"""原转录标记解析。

研究者在 raw_transcription 中使用的轻量标记（尽量接近古籍整理习惯）：

  〔缺〕 / 〔缺三行〕 / 〔缺叶〕 / 〔缺二叶〕
      缺文、缺叶标记。有明确"缺"的物理证据，与空白正文严格区分。
  〔空白〕
      版面留白（空行/空纸），并非缺叶。
  □ 或 □三
      残泐未知字：一个 □ 一个字位；□后紧跟数字表示连续 N 个未知字。
      未知字永远是未知字，规范化与对齐都不允许把它猜成某字。
  ［批注：文字］
      天头/行间批注。不属于正文流，锚定在它"之前"那个字位之后，
      供前端显示为挂在相邻位置的插入片段。
  ［添：文字］
      抄手/藏家在栏外添补的文字。同样不参与正文比对，锚定相邻位置。
  ［按：文字］
      整理者按语，性质同上。
  【某→某】
      转录者就地记录的"字形—规范形"提示（如【無→无】）。
      显示原字形，匹配时用规范形；等价于一条就地规范化规则。

未作标记的汉字/假名等普通字符按字切分；标点单独成 token，
是否参与对齐由运行参数 include_punctuation 决定，标记层不受影响。
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

# 参与识别的标点集合（断句差异样例会用到）
_PUNCT_CHARS = (
    "，。、；：？！．…—–\\-\\.,;:?!"
    "「」『』《》〈〉“”‘’\"'（）()\\[\\]【】〔〕［］"
    " \\n\\r\\t"
)
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_TOKEN_RE = re.compile(
    r"""
    (?P<lacuna>〔缺(?P<lacuna_n>[一二三四五六七八九十]+)?(?P<lacuna_unit>叶|行|字)?〕)
  | (?P<blank>〔空白〕)
  | (?P<unknown>□(?P<unk_n>[一二三四五六七八九十]+)?)
  | (?P<annot>［(?P<annot_kind>批注|添|按)：(?P<annot_text>[^］]*)］)
  | (?P<inline>【(?P<orig>[^→】]+)→(?P<norm>[^】]+)】)
  | (?P<punct>[""" + _PUNCT_CHARS + r"""])
  | (?P<char>\S)
    """,
    re.VERBOSE,
)


@dataclass
class Token:
    witness_id: int | None
    kind: str            # char | punct | lacuna | blank | unknown | annotation
    display: str         # 原字形/原标记的展示形式
    norm: str            # 用于匹配的形式；未知字/缺文/批注为 ""
    ordinal: int         # 正文流中的字位序号（批注不占字位）
    raw_start: int       # 在 raw_transcription 中的起止偏移
    raw_end: int
    note: str = ""
    # 插入片段锚定：anchor_after = 前一正文字位 ordinal；anchor_before = 后一
    anchor_after: int | None = None
    anchor_before: int | None = None
    # lacuna: 缺多少叶/行/字（未知量为 None）
    gap_amount: int | None = None
    gap_unit: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cn_to_int(s: str | None) -> int | None:
    if not s:
        return None
    if s in _CN_NUM:
        return _CN_NUM[s]
    # 简单处理十一…十九
    if len(s) == 2 and s[0] == "十" and s[1] in _CN_NUM:
        return 10 + _CN_NUM[s[1]]
    if len(s) == 2 and s[1] == "十" and s[0] in _CN_NUM:
        return _CN_NUM[s[0]] * 10
    return None


def parse_transcription(raw: str, witness_id: int | None = None) -> list[Token]:
    """把原始转录文本解析为 token 序列。

    返回的 token 保持 raw 中的出现顺序；annotation 类 token 带相邻锚点，
    不占正文字位。raw 文本本身原样保留在数据库中，不在此处改写。
    """
    tokens: list[Token] = []
    body_ordinal = 0  # 已处理的正文字位数
    last_body_index: int | None = None  # 上一个正文 token 在 tokens 中的下标

    for m in _TOKEN_RE.finditer(raw):
        g = m.lastgroup
        s, e = m.start(), m.end()

        if g == "lacuna":
            body_ordinal += 1
            t = Token(
                witness_id=witness_id, kind="lacuna",
                display=m.group("lacuna"), norm="", ordinal=body_ordinal,
                raw_start=s, raw_end=e,
                gap_amount=_cn_to_int(m.group("lacuna_n")),
                gap_unit=m.group("lacuna_unit") or "处",
            )
            tokens.append(t)
            last_body_index = len(tokens) - 1

        elif g == "blank":
            body_ordinal += 1
            t = Token(
                witness_id=witness_id, kind="blank",
                display="〔空白〕", norm="", ordinal=body_ordinal,
                raw_start=s, raw_end=e, note="版面留白，非缺叶",
            )
            tokens.append(t)
            last_body_index = len(tokens) - 1

        elif g == "unknown":
            n = _cn_to_int(m.group("unk_n")) or 1
            for _ in range(n):
                body_ordinal += 1
                t = Token(
                    witness_id=witness_id, kind="unknown",
                    display="□", norm="", ordinal=body_ordinal,
                    raw_start=s, raw_end=e,
                    note="残泐未知字，不得据他本径补为确定字形",
                )
                tokens.append(t)
                last_body_index = len(tokens) - 1

        elif g == "annot":
            kind_map = {"批注": "annotation", "添": "annotation", "按": "annotation"}
            label = m.group("annot_kind")
            anchor_after = tokens[last_body_index].ordinal if last_body_index is not None else 0
            t = Token(
                witness_id=witness_id, kind=kind_map[label],
                display=f"［{label}：{m.group('annot_text')}］",
                norm="", ordinal=-1, raw_start=s, raw_end=e,
                note=f"{label}，不属正文", anchor_after=anchor_after,
            )
            tokens.append(t)
            # 不更新 last_body_index：批注锚定的是它前后的正文字位

        elif g == "inline":
            body_ordinal += 1
            t = Token(
                witness_id=witness_id, kind="char",
                display=m.group("orig"), norm=m.group("norm"),
                ordinal=body_ordinal, raw_start=s, raw_end=e,
                note="就地规范形记录",
            )
            tokens.append(t)
            last_body_index = len(tokens) - 1

        elif g == "punct":
            t = Token(
                witness_id=witness_id, kind="punct",
                display=m.group(), norm="", ordinal=-1,
                raw_start=s, raw_end=e,
            )
            tokens.append(t)
            # 标点不占正文字位，但它仍可锚定其后的批注——锚点只看正文 token

        else:  # char
            body_ordinal += 1
            t = Token(
                witness_id=witness_id, kind="char",
                display=m.group(), norm=m.group(),
                ordinal=body_ordinal, raw_start=s, raw_end=e,
            )
            tokens.append(t)
            last_body_index = len(tokens) - 1

    # 回填批注的 anchor_before：下一个正文 token 的 ordinal
    for i, t in enumerate(tokens):
        if t.kind == "annotation":
            for nxt in tokens[i + 1:]:
                if nxt.kind != "annotation" and nxt.ordinal >= 0:
                    t.anchor_before = nxt.ordinal
                    break
    return tokens


def body_tokens(tokens: list[Token]) -> list[Token]:
    """正文流（不含批注；标点按参数另行过滤）。"""
    return [t for t in tokens if t.kind != "annotation"]
