"""CollateX 适配层。

优先调用真正的 CollateX（REST 或 CLI）；当环境中没有 Java/CollateX 时，
退回内置的多序列渐进比对实现，并在 engine 字段中如实标注。

对外只暴露 collate(witness_tokens, include_punctuation) -> AlignedResult。
输入：{witness_id: [token_dict, ...]}（已解析、已规范化，仅正文流）
输出：对齐列矩阵 + 引擎标识。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field

import httpx

from .internal_align import progressive_align


@dataclass
class AlignedResult:
    # columns: 每列为 {witness_id: token_dict | None}
    columns: list[dict] = field(default_factory=list)
    engine: str = "internal-fallback"
    note: str = ""


def _collatex_payload(sequences: dict[int, list[dict]]) -> dict:
    witnesses = []
    for wid, toks in sequences.items():
        witnesses.append(
            {
                "id": f"w{wid}",
                # CollateX 的 token 形式：{"t": 显示, "n": 规范形}
                "tokens": [{"t": t["display"], "n": t["norm"] or t["display"]} for t in toks],
            }
        )
    return {
        "witnesses": witnesses,
        "algorithm": "dekker",  # 近东亚标点本可换 medite；Dekker 对短句重复更稳
        "tokenize": False,
        "output_format": "json",
        "indent": False,
    }


def _parse_collatex_table(data: dict, id_to_wid: dict[str, int]) -> list[dict]:
    """解析 CollateX JSON alignment table。

    形态：{"table": [[ [token-or-null, ...], ... ], ...]}，
    每个内层数组按 witnesses 顺序排列，token 为 {"t","n",...} 或 null/"-"。
    我们把 token 按 (witness_id, ordinal) 找回原始 token_dict。
    """
    table = data.get("table") or data.get("alignmentTable") or []
    wids = [id_to_wid[w["id"]] for w in data.get("witnesses", [])] if data.get("witnesses") else None
    columns: list[dict] = []
    for pos, col in enumerate(table):
        out: dict = {}
        items = col if isinstance(col, list) else [col]
        for i, cell in enumerate(items):
            wid = wids[i] if wids and i < len(wids) else list(id_to_wid.values())[i]
            if cell is None or cell == "-" or cell == []:
                out[wid] = None
            else:
                # cell 可能是 token 或 token 列表（合并列）。退回按 n 顺序展开。
                cell_tokens = cell if isinstance(cell, list) else [cell]
                for ct in cell_tokens:
                    out.setdefault("__raw__", []).append(ct)
        columns.append(out)
    return columns


def _try_http(url: str, sequences: dict[int, list[dict]], timeout: float = 4.0) -> list[dict] | None:
    payload = _collatex_payload(sequences)
    id_to_wid = {f"w{wid}": wid for wid in sequences}
    try:
        r = httpx.post(url, json=payload, timeout=timeout)
        if r.status_code != 200:
            return None
        return _parse_collatex_table(r.json(), id_to_wid)
    except Exception:
        return None


def _try_cli(cli: str, sequences: dict[int, list[dict]], timeout: float = 8.0) -> list[dict] | None:
    if not shutil.which(cli):
        return None
    payload = _collatex_payload(sequences)
    try:
        proc = subprocess.run(
            [cli, "-f", "json", "-"],
            input=json.dumps(payload), capture_output=True, text=True, timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        id_to_wid = {f"w{wid}": wid for wid in sequences}
        return _parse_collatex_table(json.loads(proc.stdout), id_to_wid)
    except Exception:
        return None


def collate(
    sequences: dict[int, list[dict]],
    mode: str = "auto",
    url: str = "http://localhost:7369/collate",
    cli: str = "collatex",
) -> AlignedResult:
    """生成对齐候选。找不到 CollateX 时使用内置实现并明确标注。"""
    if mode in ("auto", "http"):
        cols = _try_http(url, sequences)
        if cols is not None:
            return AlignedResult(columns=cols, engine="collatex-http", note="CollateX REST")
    if mode in ("auto", "cli"):
        cols = _try_cli(cli, sequences)
        if cols is not None:
            return AlignedResult(columns=cols, engine="collatex-cli", note="CollateX 命令行")
    if mode == "http":
        return AlignedResult(
            columns=[], engine="unavailable",
            note=f"无法连接 CollateX REST：{url}，未生成对齐",
        )
    if mode == "cli":
        return AlignedResult(
            columns=[], engine="unavailable",
            note=f"找不到 CollateX 命令行：{cli}，未生成对齐",
        )
    cols = progressive_align(sequences)
    return AlignedResult(
        columns=cols, engine="internal-fallback",
        note="环境中未检测到 CollateX，采用内置渐进比对候选；部署 CollateX 后重跑即可获得一致结果",
    )
