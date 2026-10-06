# -*- coding: utf-8 -*-
"""API 整合測試：建檔、對齊、人工判斷、調整守衛、修訂史、匯出。"""
def test_health_and_seed(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert client.get("/api/passages").json()


def test_seeded_has_three_witnesses(seeded_passage):
    sigla = [w["siglum"] for w in seeded_passage["witnesses"]]
    assert sigla == ["甲本", "乙本", "丙本"]


def _collate(client, pid, punct=False):
    return client.post("/api/collate", json={
        "passage_id": pid, "include_punctuation": punct,
        "use_collatex": False}).json()


def test_collate_separates_concerns(client, seeded_passage):
    run = _collate(client, seeded_passage["id"])
    assert run["engine"] == "builtin"
    kinds = [c["suggested_kind"] for c in run["columns"]]
    assert "variant_form" in kinds
    mtypes = {m["type"] for m in run["markers"]}
    assert {"lacuna", "blank", "annotation", "insertion"} <= mtypes


def test_punctuation_toggle_changes_columns(client, seeded_passage):
    pid = seeded_passage["id"]
    n1 = len(_collate(client, pid, False)["columns"])
    n2 = len(_collate(client, pid, True)["columns"])
    assert n2 > n1


def test_human_judgment_distinct_from_suggestion(client, seeded_passage):
    pid = seeded_passage["id"]
    run = _collate(client, pid)
    target = next(i for i, c in enumerate(run["columns"])
                  if c["suggested_kind"] == "omission")
    r = client.put(f"/api/runs/{run['id']}/judgments", json={
        "column_index": target, "kind": "added",
        "rationale": "研究者定為增衍而非脫文"})
    assert r.status_code == 200
    again = client.get(f"/api/runs/{run['id']}").json()
    j = next(x for x in again["judgments"] if x["column_index"] == target)
    assert j["kind"] == "added" and j["rationale"].startswith("研究者")
    # 自動建議欄位未被改寫
    col = again["columns"][target]
    assert col["suggested_kind"] == "omission"


def test_unknown_glyph_cannot_be_moved_into_a_guess(client, seeded_passage):
    pid = seeded_passage["id"]
    run = _collate(client, pid)
    box = next(c for c in run["columns"]
               if any(cell and cell["type"] == "unknown"
                      for cell in c["cells"].values()))
    wid = next(w for w, cell in box["cells"].items()
               if cell and cell["type"] == "unknown")
    target = next(i for i, c in enumerate(run["columns"])
                  if i != box["index"] and c["cells"].get(wid) is None)
    r = client.post("/api/adjust", json={
        "action": "move_cell", "run_id": run["id"],
        "column_index": box["index"], "witness_id": wid,
        "target_column_index": target})
    assert r.status_code == 422
    assert "未知字" in r.json()["detail"]


def test_adjust_creates_new_run_without_touching_old(client, seeded_passage):
    pid = seeded_passage["id"]
    run = _collate(client, pid)
    # 找一欄僅部分見本有字，把那個字移到一個該見本為空的欄
    partial = next(c for c in run["columns"]
                   if any(v is None for v in c["cells"].values())
                   and any(v is not None for v in c["cells"].values()))
    wid, cell = next((w, v) for w, v in partial["cells"].items() if v)
    target = next(i for i, c in enumerate(run["columns"])
                  if i != partial["index"] and c["cells"].get(wid) is None)
    r = client.post("/api/adjust", json={
        "action": "move_cell", "run_id": run["id"],
        "column_index": partial["index"], "witness_id": wid,
        "target_column_index": target, "revision_note": "人工試移"})
    assert r.status_code == 200, r.text
    new_run = r.json()
    assert new_run["id"] != run["id"]
    assert new_run["engine"] == "manual"
    # 舊 run 仍在且內容不變
    old = client.get(f"/api/runs/{run['id']}").json()
    assert len(old["columns"]) == len(run["columns"])


def test_transcription_edit_keeps_history_and_orig(client, seeded_passage):
    wid = seeded_passage["witnesses"][0]["id"]
    before = client.get(
        f"/api/passages/{seeded_passage['id']}").json()["witnesses"][0]
    r = client.patch(f"/api/witnesses/{wid}/transcription",
                     json={"raw_transcription": before["raw_transcription"]})
    assert r.status_code == 200

    from app.database import SessionLocal
    from app.models import Token, TranscriptRevision
    db = SessionLocal()
    try:
        # 至少一條修訂史（建立時一條；本次若內容相同不新增）
        assert db.query(TranscriptRevision).filter_by(witness_id=wid).count() >= 1
        # 原字形獨立保留
        origs = {t.orig for t in db.query(Token).filter_by(witness_id=wid)}
        assert "爲" in origs and "徳" in origs
    finally:
        db.close()


def test_export_formats_and_sources(client, seeded_passage):
    run = _collate(client, seeded_passage["id"])
    rid = run["id"]
    j = client.get(f"/api/runs/{rid}/export?fmt=json").json()
    assert {w["siglum"] for w in j["witness_sources"]} == {"甲本", "乙本", "丙本"}
    assert "witness_id" in j["witness_sources"][0]
    assert j["columns"][0]["auto_suggested_kind"]
    assert j["columns"][0]["human_judgment"] is None
    assert client.get(f"/api/runs/{rid}/export?fmt=csv").text.startswith("# passage")
    md = client.get(f"/api/runs/{rid}/export?fmt=md").text
    assert "校勘記" in md and "甲本" in md and "缺葉" in md


def test_preview_reports_types(client, seeded_passage):
    r = client.post("/api/preview", json={
        "passage_id": seeded_passage["id"],
        "raw_transcription": "甲〖缺葉〗乙〔批：注〕丙□"})
    types = [t["type"] for t in r.json()["tokens"]]
    assert types == ["text", "lacuna", "text", "annotation", "text", "unknown"]
