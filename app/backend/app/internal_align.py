"""内置退回实现：渐进式多序列比对（progressive alignment）。

步骤：
1. 以 token 数最多的见本为骨干，用 Needleman–Wunsch 逐一与其余见本做双序列对齐
   （匹配键为规范形 norm；错配代价 1，缺/添代价 0.7，鼓励对齐而非整段删除）；
2. 每次把新见本按对齐路径投影进现存列矩阵，必要时复制出新列；
3. 结构性 token（缺文、空白、未知字）不与任何具体字匹配——
   未知字永远不会被"对齐成"某个猜测字。

这只是 CollateX 缺席时的本地候选，不追求语言学最优；结果列矩阵与
CollateX 路径同构，上层自动分类与人工修订流程完全一致。
"""
from __future__ import annotations

from typing import Any

MATCH_COST = 0.0
MISMATCH = 1.0
GAP_COST = 0.7  # 略低于错配：宁可引入缺/添列，也不强行错对


def _match_key(tok: dict | None) -> str | None:
    if tok is None:
        return None
    if tok["kind"] != "char":
        # lacuna / blank / unknown / punct 用带前缀的键，互不与具体字匹配
        return f"__{tok['kind']}__:{tok.get('display')}"
    return tok.get("norm") or tok["display"]


def _can_pair(a: dict, b: dict) -> bool:
    """结构性 token 的匹配纪律。"""
    if a["kind"] == "unknown" or b["kind"] == "unknown":
        return False  # 残泐字不与任何字配对，更不许拿他本之字"补全"
    kinds = {a["kind"], b["kind"]}
    if kinds != {"char"} and _match_key(a) != _match_key(b):
        return False
    if {"lacuna", "char"} <= kinds or {"blank", "char"} <= kinds or kinds == {"lacuna", "blank"}:
        return False
    return _match_key(a) == _match_key(b)


def needleman_wunsch(a: list[dict], b: list[dict]) -> list[tuple[int | None, int | None]]:
    """返回 (a_idx|None, b_idx|None) 的对齐路径，None 表示该边缺席。"""
    n, m = len(a), len(b)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = d[i - 1][0] + GAP_COST
    for j in range(1, m + 1):
        d[0][j] = d[0][j - 1] + GAP_COST
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            pair = MATCH_COST if _can_pair(a[i - 1], b[j - 1]) else MISMATCH
            d[i][j] = min(
                d[i - 1][j - 1] + pair,
                d[i - 1][j] + GAP_COST,
                d[i][j - 1] + GAP_COST,
            )
    # 回溯（并列时偏好配对，列结构更稳定）
    path: list[tuple[int | None, int | None]] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            pair = MATCH_COST if _can_pair(a[i - 1], b[j - 1]) else MISMATCH
            if abs(d[i][j] - (d[i - 1][j - 1] + pair)) < 1e-9:
                path.append((i - 1, j - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and (j == 0 or d[i - 1][j] <= d[i][j - 1]):
            path.append((i - 1, None))
            i -= 1
        else:
            path.append((None, j - 1))
            j -= 1
    path.reverse()
    return path


def progressive_align(sequences: dict[int, list[dict]]) -> list[dict[int, Any]]:
    """sequences: {witness_id: [token, ...]}（正文流，标点已按参数过滤）。"""
    if not sequences:
        return []

    order = sorted(sequences, key=lambda w: len(sequences[w]), reverse=True)
    pivot = order[0]
    # 列矩阵：每个现存列对应骨干 token 下标，或 -1（非骨干独有列）
    columns: list[dict] = [{pivot: tok, "_pivot_idx": i} for i, tok in enumerate(sequences[pivot])]

    def pivot_tokens(cols: list[dict]) -> list[dict]:
        out: list[dict] = []
        for c in cols:
            idx = c["_pivot_idx"]
            if idx >= 0:
                out.append(sequences[pivot][idx])
        return out

    for wid in order[1:]:
        ref_seq = pivot_tokens(columns)
        path = needleman_wunsch(ref_seq, sequences[wid])

        new_columns: list[dict] = []
        ref_cursor = 0
        for ai, bj in path:
            if ai is not None:
                # 消费现存列，直到与 ref 的第 ai 项相遇
                while ref_cursor < len(columns) and columns[ref_cursor]["_pivot_idx"] != ai:
                    new_columns.append(dict(columns[ref_cursor]))
                    ref_cursor += 1
                col = dict(columns[ref_cursor])
                ref_cursor += 1
            else:
                col = {"_pivot_idx": -1}  # 新见本独有：新列
            if bj is not None:
                col[wid] = sequences[wid][bj]
            new_columns.append(col)
        while ref_cursor < len(columns):
            new_columns.append(dict(columns[ref_cursor]))
            ref_cursor += 1
        columns = new_columns

    # 去掉内部键；补全所有 wid 为 None；丢弃全空列
    wids = list(sequences)
    full: list[dict] = []
    for col in columns:
        out = {w: col.get(w) for w in wids}
        if any(v is not None for v in out.values()):
            full.append(out)
    return full
