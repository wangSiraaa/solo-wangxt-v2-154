# -*- coding: utf-8 -*-
"""內建多見本漸進式比對器（CollateX 不可用時的確定性退回實作）。

策略：中心星（center-star）
  1. 取第一個見本為中心，與其餘見本逐一做 Needleman–Wunsch 字符級比對；
  2. 由「相對於中心的位置」把所有見本投影到同一欄位空間；
  3. 同一錨點下的多餘片段，僅當內容完全一致才合成「共有增入」欄，
     否則各自成欄——這樣重複短句不會被錯位強合；
  4. 缺葉／空白是*佔位*：佔若干欄位、註明 lacuna/blank，
     絕不與「脫文」（omission）同類；
  5. 未知字「□」只與「□」匹配，與任何實字一律判 mismatch——
     系統永不把未知字補成猜測字。

輸出結構見 :func:`align_witnesses`，與 CollateX 適配層輸出同構。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import Token, TokenType
from .normalization import UNKNOWN_NORM

# 計分：錯配必須比「兩個空位」更不划算，否則重複短句（如「勿自欺也」
# 兩見）會被錯位強配。gap_open + gap_extend 概念用單一空位罰分近似：
# 配齊兩邊需要兩個 gap（-2），故 mismatch 取 -3。
MATCH = 3
MISMATCH = -3
GAP = -1

# 參加正文比對的 token 類型
ALIGN_TYPES = {TokenType.TEXT, TokenType.UNKNOWN, TokenType.PUNCT}


@dataclass
class AlignToken:
    token_id: str
    orig: str
    norm: str
    type: str
    position: int


def _sub(a: AlignToken, b: AlignToken) -> int:
    """替換計分：未知字只匹配未知字；標點只匹配標點。"""
    if a.type == "unknown" or b.type == "unknown":
        return MATCH if (a.type == b.type and a.norm == b.norm) else MISMATCH
    if a.type == "punct" or b.type == "punct":
        return MATCH if (a.type == b.type and a.norm == b.norm) else MISMATCH
    return MATCH if a.norm == b.norm else MISMATCH


def needleman_wunsch(a: list[AlignToken], b: list[AlignToken]):
    """回傳 (aligned_a, aligned_b)，None 表示 gap。"""
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        dp[i][0] = i * GAP
    for j in range(1, m + 1):
        dp[0][j] = j * GAP
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            diag = dp[i - 1][j - 1] + _sub(a[i - 1], b[j - 1])
            up = dp[i - 1][j] + GAP
            left = dp[i][j - 1] + GAP
            dp[i][j] = max(diag, up, left)

    ai: list[AlignToken | None] = []
    bi: list[AlignToken | None] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + _sub(a[i - 1], b[j - 1]):
            ai.append(a[i - 1]); bi.append(b[j - 1]); i -= 1; j -= 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + GAP:
            ai.append(a[i - 1]); bi.append(None); i -= 1
        else:
            ai.append(None); bi.append(b[j - 1]); j -= 1
    ai.reverse(); bi.reverse()
    return ai, bi, dp[n][m]


def prepare_sequences(witness_tokens: dict[str, list[Token]],
                      include_punctuation: bool):
    """把 DB token 轉成比對序列；分開回傳記號（批注/插入/缺葉/空白）。"""
    sequences: dict[str, list[AlignToken]] = {}
    gaps: dict[str, list] = {}
    markers: dict[str, list] = {}

    for wid, toks in witness_tokens.items():
        seq: list[AlignToken] = []
        gap_list: list[dict] = []
        marker_list: list[dict] = []
        # token 已按 position 排序；記下正文 position → AlignToken 以錨定
        textpos_index: dict[int, AlignToken] = {}
        for t in toks:
            at = AlignToken(token_id=t.id, orig=t.orig, norm=t.norm,
                            type=t.type.value if isinstance(t.type, TokenType)
                            else t.type, position=t.position)
            if at.type in ("text", "unknown"):
                seq.append(at)
                textpos_index[t.position] = at
            elif at.type == "punct":
                if include_punctuation:
                    seq.append(at)
                    textpos_index[t.position] = at
            elif at.type in ("lacuna", "blank"):
                gap_list.append({"token_id": t.id, "orig": t.orig,
                                 "type": at.type, "position": t.position,
                                 "anchor_after_position": t.anchor_after})
            elif at.type in ("annotation", "insertion"):
                marker_list.append({"token_id": t.id, "orig": t.orig,
                                    "type": at.type, "position": t.position,
                                    "note": t.note,
                                    "anchor_after_position": t.anchor_after})
        sequences[wid] = seq
        gaps[wid] = gap_list
        markers[wid] = marker_list
    return sequences, gaps, markers


def finalize_columns(cell_columns, witness_order, witness_tokens,
                     include_punctuation, engine_detail, score=None):
    """兩個比對引擎共用的收尾：分類、記號錨定、缺葉蓋位。

    ``cell_columns``：已對齊的欄位清單，每欄是
    ``{witness_id: AlignToken | None}``（與見本序列來自同一批 token）。
    """
    sequences, gaps, markers_raw = prepare_sequences(
        witness_tokens, include_punctuation)

    columns = [_classify_one(cells, idx, witness_order)
               for idx, cells in enumerate(cell_columns)]

    token_column: dict[str, int] = {}
    for col in columns:
        for cell in col["cells"].values():
            if cell and cell.get("token_id"):
                token_column[cell["token_id"]] = col["index"]

    out_markers = []
    for wid in witness_order:
        for g in gaps[wid]:
            anchor = _nearest_anchor_column(g, sequences[wid], token_column)
            ext = _estimate_gap_span(g, sequences[wid], columns, wid,
                                     token_column)
            out_markers.append({
                "token_id": g["token_id"], "witness_id": wid,
                "type": g["type"], "orig": g["orig"], "note": "",
                "anchor_column_index": anchor,
                "span_columns": ext,
            })
        for mk in markers_raw[wid]:
            anchor = _nearest_anchor_column(mk, sequences[wid], token_column)
            out_markers.append({
                "token_id": mk["token_id"], "witness_id": wid,
                "type": mk["type"], "orig": mk["orig"], "note": mk["note"],
                "anchor_column_index": anchor,
                "span_columns": None,
            })

    _stamp_gaps_into_columns(columns, out_markers, witness_tokens,
                             witness_order)
    return {"columns": columns, "markers": out_markers,
            "engine_detail": engine_detail, "score": score}


def _classify_one(cells, idx, witness_order):
    kind, note = classify_column(cells, witness_order)
    return {
        "index": idx,
        "cells": {
            wid: (None if t is None else
                  {"token_id": t.token_id, "orig": t.orig,
                   "norm": t.norm, "type": t.type})
            for wid, t in cells.items()
        },
        "suggested_kind": kind,
        "suggested_note": note,
    }


def align_witnesses(witness_tokens: dict[str, list[Token]],
                    witness_order: list[str],
                    include_punctuation: bool = False):
    """內建引擎入口，輸出結構見 :func:`finalize_columns`。

    先各見本與中心做 NW，再沿中心序列逐位「編織」成統一欄：
    中心每推進一字開一欄；中心不動時，把各見本的增入段獨立排成
    若干欄（內容相同者共欄），解決同一區間內各本增入不同而錯位的問題。
    """
    sequences, _, _ = prepare_sequences(
        witness_tokens, include_punctuation)

    center_id = witness_order[0]
    center = sequences[center_id]

    # 各見本與中心的成對比對（ai 為中心行、bi 為該見本行）
    pair_ab: dict[str, tuple[list, list]] = {}
    scores: dict[str, int] = {}
    for wid in witness_order[1:]:
        a, b, score = needleman_wunsch(center, sequences[wid])
        pair_ab[wid] = (a, b)
        scores[wid] = score

    other_ids = witness_order[1:]
    cell_columns = _weave(center, pair_ab, witness_order, center_id,
                          other_ids)

    avg_score = (sum(scores.values()) / len(scores)) if scores else None
    return finalize_columns(cell_columns, witness_order, witness_tokens,
                            include_punctuation,
                            "builtin:center-star+NW", avg_score)


def _weave(center, pair_ab, witness_order, center_id, other_ids):
    """沿中心序列逐位編織；每個見本的成對行各有自己的游標。

    對每一個中心位置：
      1. 先讓各見本排出「中心為 gap」的增入（其成對行目前 ai 為 None），
         這些增入按規範形分組獨立成欄；
      2. 再開「中心欄」，各見本取其成對格（可能為 None＝該本脫此字）。
    中心走完後，各見本若還有尾部增入，再補段。
    """
    columns: list[dict] = []
    cursor = {w: 0 for w in other_ids}

    for ct in center:
        # 中心本位之前的增入段
        seg: dict[str, list[AlignToken]] = {w: [] for w in other_ids}
        for wid in other_ids:
            a, b = pair_ab[wid]
            k = cursor[wid]
            while k < len(a) and a[k] is None:
                if b[k] is not None:
                    seg[wid].append(b[k])
                k += 1
            cursor[wid] = k
        columns.extend(_lay_segment(seg, witness_order, center_id))

        # 中心欄
        cells = {center_id: ct}
        for wid in other_ids:
            a, b = pair_ab[wid]
            k = cursor[wid]
            if k < len(a) and a[k] is not None:
                cells[wid] = b[k]
                cursor[wid] = k + 1
            else:
                cells[wid] = None
        columns.append(cells)

    # 尾部增入
    tail: dict[str, list[AlignToken]] = {w: [] for w in other_ids}
    for wid in other_ids:
        a, b = pair_ab[wid]
        for k in range(cursor[wid], len(a)):
            if a[k] is None and b[k] is not None:
                tail[wid].append(b[k])
        cursor[wid] = len(a)
    columns.extend(_lay_segment(tail, witness_order, center_id))
    return columns


def _lay_segment(seg_tokens, witness_order, center_id):
    """把「中心無字」段裡各見本的增入序列排成欄。

    規則：
      * 各見本序列按位置逐字消費；
      * 每一步收集「下一個 norm」，相同 norm 的見本共一欄；
      * 不同 norm 各開一欄（見本順序），直到本段全部消費完。
    """
    queues = {w: list(seg_tokens.get(w, [])) for w in witness_order
              if w != center_id}
    out = []
    while any(queues.values()):
        # 選定第一個還有內容的見本的當前 norm 作為本欄 key
        anchor_w = next(w for w in witness_order[1:] if queues.get(w))
        key = queues[anchor_w][0].norm
        key_type = queues[anchor_w][0].type
        cells = {w: None for w in witness_order}
        for w in witness_order[1:]:
            if queues.get(w) and queues[w][0].norm == key \
                    and queues[w][0].type == key_type:
                cells[w] = queues[w].pop(0)
        out.append(cells)
    return out


def classify_column(cells: dict, witness_order: list[str]) -> tuple[str, str]:
    """對一欄做*建議性*分類。研究者可在人工判斷中覆蓋。"""
    present = [(wid, t) for wid, t in cells.items() if t is not None]
    types = {t.type for _, t in present}

    if len(present) == len(witness_order):
        origs = {t.orig for _, t in present}
        norms = {t.norm for _, t in present}
        if types == {"punct"}:
            if len(origs) == 1:
                return "same", "標點一致"
            return "punctuation", "斷句／標點不同"
        if len(origs) == 1:
            return "same", "各本原字一致"
        if len(norms) == 1:
            return "variant_form", "原字形不同而規範形相同，建議為異體字"
        return "variant_form", "各本異文"

    # 部分見本有字
    if len(present) < len(witness_order):
        absent = [wid for wid in witness_order if cells.get(wid) is None]
        if types <= {"punct"}:
            return "punctuation", f"僅部分見本有此斷句：缺 {_names(absent)}"
        return "omission", f"疑似脫文／增入，缺見本：{_names(absent)}"

    return "undecided", "無法自動分類"


def _names(wids):
    return "、".join(w[:6] for w in wids)


def _nearest_anchor_column(marker, seq: list[AlignToken],
                           token_column: dict[str, int]) -> int | None:
    """以 marker.anchor_after_position（前一正文 position）找欄號；
    找不到就退而用「下一個正文的前一欄」。"""
    anchor_pos = marker.get("anchor_after_position")
    if anchor_pos is not None:
        for t in seq:
            if t.position == anchor_pos:
                return token_column.get(t.token_id)
    # 找 position 比 marker 小的最後一個正文
    before = [t for t in seq if t.position < marker["position"]]
    if before:
        return token_column.get(before[-1].token_id)
    after = [t for t in seq if t.position > marker["position"]]
    if after:
        c = token_column.get(after[0].token_id)
        return c - 1 if c is not None else None
    return None


def _estimate_gap_span(gap, seq, columns, wid, token_column):
    """缺葉/空白覆蓋的欄位區間（推測）：前一正文欄+1 到後一正文欄-1。"""
    before = [t for t in seq if t.position < gap["position"]]
    after = [t for t in seq if t.position > gap["position"]]
    start = (token_column.get(before[-1].token_id, 0) + 1) if before else 0
    end = (token_column.get(after[0].token_id, len(columns)) - 1) if after \
        else len(columns) - 1
    if end < start:
        end = start
    return [start, end]


def _stamp_gaps_into_columns(columns, markers, witness_tokens, witness_order):
    """把缺葉/空白佔位蓋進 span 欄位的該見本儲存格。

    佔位用一種特殊 cell 表達：type=lacuna/blank, gap_token_id 指向記號，
    使前端能把「此本缺葉」與「此本脫一字」畫成完全不同的東西。
    """
    for mk in markers:
        if mk["type"] not in ("lacuna", "blank"):
            continue
        span = mk.get("span_columns") or [mk.get("anchor_column_index") or 0]
        start, end = span[0], span[1]
        wid = mk["witness_id"]
        for idx in range(max(0, start), min(len(columns), end + 1)):
            cell = columns[idx]["cells"].get(wid)
            if cell is None:
                columns[idx]["cells"][wid] = {
                    "token_id": None,
                    "orig": mk["orig"],
                    "norm": "",
                    "type": mk["type"],
                    "gap_token_id": mk["token_id"],
                }
        # 該段若被蓋進任何欄，建議分類改為 lacuna/blank
        for idx in range(max(0, start), min(len(columns), end + 1)):
            cells = columns[idx]["cells"]
            if any(c is not None and c.get("type") in ("lacuna", "blank")
                   for c in cells.values()):
                # 若整欄都是同一種 gap → 同類；否則保留並註明
                gtypes = {c["type"] for c in cells.values()
                          if c and c.get("type") in ("lacuna", "blank")}
                real = [c for c in cells.values()
                        if c and c.get("type") not in ("lacuna", "blank")]
                if not real and len(gtypes) == 1:
                    columns[idx]["suggested_kind"] = next(iter(gtypes))
                    columns[idx]["suggested_note"] = (
                        "缺葉佔位" if "lacuna" in gtypes else "空白正文佔位")
