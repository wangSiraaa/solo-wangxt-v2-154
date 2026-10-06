"""把对齐列自动分类为校勘候选。

类别（与研究者人工判断共用同一套受控词表）：
  identical     各见本一致
  glyph_variant 异体/俗字：规范形相同而原字形不同
  substitution  异文：规范形不同的实字替换
  omission      脱文：一个或多个见本于此缺席，而至少两个见本有实字
  addition      添入：仅个别见本有实字，他本皆无（与 omission 一体两面，
                分类视角取决于底本；此处按"少数派有字"判 addition）
  punctuation   仅断句/标点差异（include_punctuation=True 时出现）
  lacuna        缺叶/缺文标记：有明确缺失证据，绝不与脱文混类
  blank         空白正文：版面留白
  unknown_char  残泐未知字（□）：不猜字、不并入异文
  mixed_struct  结构性差异混合（如缺文对未知字），交人工
  divergent     其他多字分歧，交人工

注意：分类结果只是 suggested_*；研究者可在 researcher_* 字段给不同结论。
"""
from __future__ import annotations

from typing import Any

REAL = {"char"}
STRUCT = {"lacuna", "blank", "unknown"}


def classify_column(col: dict[int, dict | None]) -> tuple[str, str]:
    """返回 (suggested_type, suggested_reason)。"""
    present = {w: t for w, t in col.items() if t is not None}
    if not present:
        return "divergent", "空列"

    kinds = {t["kind"] for t in present.values()}
    missing = [w for w in col if col[w] is None]

    # 1) 标点：逐见本核对"此处是否有断句"
    if kinds <= {"punct"}:
        marks = sorted({t["display"] for t in present.values()})
        if not missing and len(marks) == 1:
            return "identical", f"各本同以「{marks[0]}」断句"
        if not missing and len(marks) > 1:
            return "punctuation", f"断句标记不同：{'/'.join(marks)}"
        if present:
            return "punctuation", f"断句位置不同：{'、'.join(marks)} 对无断句（{_names(missing)} 无）"
        return "punctuation", "断句差异"

    # 2) 结构性标记不与实字/标点混类
    if kinds & STRUCT:
        labels = {"lacuna": "缺叶/缺文", "blank": "空白正文", "unknown": "残泐未知字"}
        struct_kinds = kinds & STRUCT
        other = kinds - STRUCT  # char / punct
        if not other and len(struct_kinds) == 1 and len(present) + len(missing) >= 2:
            sk = next(iter(struct_kinds))
            # 同一结构标记对齐
            displays = {t["display"] for t in present.values()}
            if len(displays) == 1 and not missing:
                return "identical", f"各本同为{labels[sk]}标记"
            if sk == "unknown":
                return "unknown_char", "残泐未知字位，保留 □，不据他本补字"
            if sk == "lacuna":
                return "lacuna", "缺叶/缺文标记（物理缺失，非脱文）"
            return "blank", "空白正文标记（非缺叶）"
        return "mixed_struct", "缺文/空白/残泐与文字或断句相对，需人工判定"

    # 以下皆为实字
    chars = present  # kind == char
    norms = {t.get("norm") or t["display"] for t in chars.values()}
    displays = {t["display"] for t in chars.values()}

    # 3) 缺席与添入
    if missing:
        present_count = len(chars)
        if present_count == 1:
            w = next(iter(chars))
            return "addition", f"仅见本 {w} 有「{chars[w]['display']}」，他本无文（添入/异文待判）"
        if len(norms) == 1 and len(displays) == 1:
            d = next(iter(displays))
            return "omission", f"见本 {_names(missing)} 脱「{d}」"
        return "divergent", "部分见本缺席且在者字形不一，需人工判定"

    # 4) 全到齐：比较原字形与规范形
    if len(norms) == 1:
        if len(displays) == 1:
            return "identical", "各本一致"
        return "glyph_variant", f"异体字：规范形同为「{next(iter(norms))}」，原字形 {'/'.join(sorted(displays))}"

    # 5) 规范形不同：单字异文
    if all(len(t["display"]) <= 1 for t in chars.values()):
        return "substitution", f"异文：{'/'.join(sorted(displays))}"
    return "divergent", "多字分歧，需人工判定"


def _names(wids: list[int]) -> str:
    return "、".join(f"#{w}" for w in wids)


def classify(columns: list[dict[int, dict | None]]) -> list[dict[str, Any]]:
    out = []
    for col in columns:
        st, reason = classify_column(col)
        out.append({"suggested_type": st, "suggested_reason": reason})
    return out
