# -*- coding: utf-8 -*-
"""CollateX REST 適配層。

對外只暴露 :func:`run_collatex`：成功時把 CollateX 回應轉成與內建
引擎同構的結構；服務不存在、逾時或回應異常時拋 :class:`CollateXError`，
由服務層決定退回內建比對器，並在 run.engine 註明實際來源。

CollateX 不認識本系統的缺葉／批注記號，因此：
  * 送給 CollateX 的 witness 只含可比對 token（TEXT/UNKNOWN，
    以及可選 PUNCT），norm 作為 token 文字；
  * 回傳的 token 引用（ witness 序 + token 序）映射回本機 AlignToken；
  * 缺葉蓋位、批注錨定等一律由共用的 :func:`finalize_columns` 處理。
"""
from __future__ import annotations

import httpx

from ..models import Token
from .aligner import AlignToken, finalize_columns, prepare_sequences


class CollateXError(RuntimeError):
    pass


def _payload(sequences, witness_order):
    witnesses = []
    for wid in witness_order:
        witnesses.append({
            "id": wid,
            "tokens": [{"t": t.norm, "tokenId": t.token_id}
                       for t in sequences[wid]],
        })
    return {"witnesses": witnesses, "algorithm": "dekker"}


def run_collatex(client: httpx.Client, base_url: str,
                 witness_tokens: dict[str, list[Token]],
                 witness_order: list[str],
                 include_punctuation: bool):
    sequences, _, _ = prepare_sequences(
        witness_tokens, include_punctuation)

    url = base_url.rstrip("/") + "/collate"
    try:
        resp = client.post(url, json=_payload(sequences, witness_order))
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise CollateXError(str(exc)) from exc

    cell_columns = _map_response_to_columns(
        data, sequences, witness_order)
    return finalize_columns(cell_columns, witness_order, witness_tokens,
                            include_punctuation,
                            engine_detail="collatex:dekker")


def _map_response_to_columns(data, sequences, witness_order):
    """把 CollateX 的 table/alignedText 回應映射回 AlignToken 欄。

    相容兩種形狀：
      A) {"table": [[[{"_token_reference":"0"}], ...], ...]}  舊版
      B) {"witnesses":[{"id":..,"tokens":[{"tokenId":..}]}],
          "alignment":[[ {"w":"<id>","i":[0,1]}, ... ], ...]}  變體
    映射不到時明確報錯，不靜靜猜測。
    """
    # ---- 形狀 A：table（每行一個 witness，每格是 token 引用清單）----
    table = data.get("table")
    if isinstance(table, list) and table and isinstance(table[0], list):
        width = max(len(row) for row in table)
        columns: list[dict] = []
        for col_idx in range(width):
            cells = {}
            for row_idx, wid in enumerate(witness_order):
                refs = table[row_idx][col_idx] if col_idx < len(table[row_idx]) else []
                tok = _resolve_refs(refs, sequences[wid])
                cells[wid] = tok
            columns.append(cells)
        return columns

    # ---- 形狀 B：alignment 欄清單 ----
    alignment = data.get("alignment")
    if isinstance(alignment, list):
        by_id = {wid: sequences[wid] for wid in witness_order}
        columns = []
        for col in alignment:
            cells = {wid: None for wid in witness_order}
            for part in col:
                wid = part.get("w") or part.get("witness")
                idxs = part.get("i") or part.get("indices") or []
                if wid not in by_id:
                    continue
                seq = by_id[wid]
                picked = [seq[i] for i in idxs if 0 <= i < len(seq)]
                cells[wid] = picked[0] if picked else None
            columns.append(cells)
        return columns

    raise CollateXError(f"無法識別的 CollateX 回應形狀：{list(data)}")


def _resolve_refs(refs, seq):
    """一格中的 token 引用 → 首個 AlignToken（字符級比對每格至多一字）。"""
    if not refs:
        return None
    ref = refs[0]
    # 新版直接給 {"_token_reference": "n"}；部分版本給 "n"
    raw = ref.get("_token_reference") if isinstance(ref, dict) else ref
    if raw is None and isinstance(ref, dict):
        raw = ref.get("tokenId")
    try:
        return seq[int(raw)]
    except (TypeError, ValueError, IndexError):
        raise CollateXError(f"CollateX token 引用越界或無效：{raw!r}")
