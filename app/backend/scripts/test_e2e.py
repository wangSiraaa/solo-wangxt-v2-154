"""端到端验收测试：直接打 FastAPI ASGI（无需起端口、不受代理影响）。

覆盖需求：
 1. 原转录逐字符保留，规范化只动匹配层（峯→峰、嵗→歲、覌→曉）
 2. 异体字/脱文/异文/断句/缺叶/空白/未知字分类互不混淆
 3. 标点参与与否是两次独立运行、结果不同
 4. 自动建议不覆盖研究者判断（两套字段独立）
 5. 调整对齐不删改原转录
 6. 未知字不得与实字合并（不猜补）；实字不得抹成缺文
 7. 插入片段(批注/添/按)锚定相邻字位
 8. 导出含见本来源与校勘关系（JSON/CSV/TEI）
 9. 重跑产生新候选，不覆盖旧 run
"""
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app

client = TestClient(app)


def _run(include_punct):
    r = client.post("/collations/run", json={
        "passage_id": 1, "include_punctuation": include_punct})
    assert r.status_code == 200, r.text
    return r.json()


def _types(run):
    return [c["suggested_type"] for c in run["columns"]]


def _col(run, predicate):
    return next(c for c in run["columns"] if predicate(c))


def test_health_and_seed():
    h = client.get("/health").json()
    assert h["status"] == "ok"
    p = client.get("/passages/1").json()
    assert len(p["witnesses"]) == 3
    raws = {w["siglum"]: w["raw_transcription"] for w in p["witnesses"]}
    assert "〔缺二叶〕" in raws["丙本"] and "〔空白〕" in raws["丙本"]
    assert "□" in raws["丙本"]
    assert "［批注：" in raws["甲本"] and "［添：" in raws["乙本"] and "［按：" in raws["丙本"]


def test_normalization_is_match_layer_only():
    run = _run(False)
    # 峯/峰：显示保留原字形，规范形归一
    col = _col(run, lambda c: any(t and t["display"] == "峯" for t in c["tokens"].values() if t))
    assert col["suggested_type"] == "glyph_variant"
    norms = {t["norm"] for t in col["tokens"].values() if t}
    assert norms == {"峰"}
    # 覌→曉 规则让异文归为异体字；原转录里仍是覌
    col2 = _col(run, lambda c: any(t and t["display"] == "覌" for t in c["tokens"].values() if t))
    assert col2["suggested_type"] == "glyph_variant"
    p = client.get("/passages/1").json()
    yi = next(w for w in p["witnesses"] if w["siglum"] == "乙本")
    assert "覌" in yi["raw_transcription"]


def test_omission_distinct_from_lacuna_and_blank():
    run = _run(False)
    types = _types(run)
    assert "omission" in types  # 丙本缺叶之后的整段缺文 → 多列脱文候选
    assert "lacuna" in types or "mixed_struct" in types
    # 缺叶与空白是两个不同 token
    kinds = [t["kind"] for c in run["columns"] for t in c["tokens"].values() if t]
    assert "lacuna" in kinds and "blank" in kinds
    lac = _col(run, lambda c: any(t and t["kind"] == "lacuna" for t in c["tokens"].values()))
    tok = next(t for t in lac["tokens"].values() if t and t["kind"] == "lacuna")
    assert tok["gap_amount"] == 2 and tok["gap_unit"] == "叶"


def test_unknown_not_guessable():
    run = _run(False)
    unk = _col(run, lambda c: any(t and t["kind"] == "unknown" for t in c["tokens"].values()))
    # 未知字不产生 norm（不会等于甲/乙本的「已」）
    ut = next(t for t in unk["tokens"].values() if t and t["kind"] == "unknown")
    assert ut["norm"] == "" and ut["display"] == "□"
    rid = run["id"]
    # 找一个丙本为空且他本有实字的列，尝试把 □ relink 过去 → 必须 422
    target = _col(run, lambda c: c["tokens"].get("3") is None
                  and any(t and t["kind"] == "char" for t in c["tokens"].values()))
    r = client.post(f"/runs/{rid}/overrides", json={"action": "relink", "payload": {
        "column_from": unk["id"], "column_to": target["id"], "witness_id": 3}})
    assert r.status_code == 422 and "猜" in r.json()["detail"]


def test_punctuation_toggle_changes_runs():
    no_p = _run(False)
    with_p = _run(True)
    assert len(no_p["columns"]) < len(with_p["columns"])
    assert "punctuation" not in _types(no_p)
    assert "punctuation" in _types(with_p)
    assert no_p["id"] != with_p["id"]  # 两次运行各自留存


def test_researcher_judgment_independent_and_persists():
    run = _run(False)
    col = _col(run, lambda c: c["suggested_type"] == "glyph_variant")
    r = client.put(f"/columns/{col['id']}/judgment", json={
        "researcher_type": "substitution",
        "researcher_note": "研究者认为并非异体而是异文", "confirmed": True})
    assert r.status_code == 200
    again = client.get(f"/runs/{run['id']}").json()
    saved = next(c for c in again["columns"] if c["id"] == col["id"])
    # 自动建议保持不变，人工结论独立保存
    assert saved["suggested_type"] == "glyph_variant"
    assert saved["researcher_type"] == "substitution"
    assert saved["confirmed"] is True


def test_real_char_cannot_be_marked_lacuna():
    run = _run(False)
    col = _col(run, lambda c: all(t and t["kind"] == "char" for t in c["tokens"].values() if t)
               and all(v is not None for v in c["tokens"].values()))
    r = client.post(f"/runs/{run['id']}/overrides", json={
        "action": "mark_lacuna",
        "payload": {"column_id": col["id"], "witness_id": 1, "kind": "lacuna"}})
    assert r.status_code == 422


def test_anchor_insert_and_split_keep_raw():
    run = _run(False)
    before = client.get("/passages/1").json()
    raw_before = {w["id"]: w["raw_transcription"] for w in before["witnesses"]}
    r = client.post(f"/runs/{run['id']}/overrides", json={
        "action": "anchor_insert",
        "payload": {"witness_id": 1, "annotation_display": "［批注：燈下似有老人影］",
                    "after_position": 5, "before_position": 6}})
    assert r.status_code == 200
    col = _col(run, lambda c: any(t and t["display"] == "燈" for t in c["tokens"].values() if t))
    r = client.post(f"/runs/{run['id']}/overrides", json={
        "action": "split", "payload": {"column_id": col["id"], "witness_id": 2}})
    assert r.status_code == 200
    after = client.get("/passages/1").json()
    raw_after = {w["id"]: w["raw_transcription"] for w in after["witnesses"]}
    assert raw_before == raw_after  # 调整对齐绝不动原转录


def test_annotations_anchor_to_neighbors():
    run = _run(False)
    by_witness = {}
    for a in run["annotations"]:
        by_witness.setdefault(a["witness_id"], []).append(a)
    assert len(run["annotations"]) == 3
    for a in run["annotations"]:
        assert a["anchor_after"] is not None or a["anchor_before"] is not None


def test_exports_contain_sources_and_relations():
    run = _run(False)
    rid = run["id"]
    j = client.get(f"/runs/{rid}/export.json").json()
    assert all(w["source_note"] for w in j["witnesses"])
    assert j["collation"]["rules_snapshot"]
    assert j["apparatus"] and "auto_suggestion" in j["apparatus"][0]
    assert "researcher_judgment" in j["apparatus"][0]
    csv_text = client.get(f"/runs/{rid}/export.csv").text
    assert "甲本来源" in csv_text and "异体字" in csv_text
    xml = client.get(f"/runs/{rid}/export.xml").text
    assert "<app " in xml and 'type="lacuna"' in xml and 'type="illegible"' in xml
    # 未知字在 TEI 中保持 □，不被写成猜测字
    assert "<g type=\"unknown\">□</g>" in xml


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            # 每个用例重建库，保证干净
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
            from app.seed import seed_if_empty
            from app.database import SessionLocal
            db = SessionLocal(); seed_if_empty(db); db.close()
            fn()
            print(f"PASS {fn.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
    raise SystemExit(0 if passed == len(fns) else 1)
