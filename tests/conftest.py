# -*- coding: utf-8 -*-
"""pytest 共用 fixture：記憶體 SQLite + 自制樣本。"""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["COLLATEX_URL"] = ""          # 測試固定走內建引擎
os.environ["SEED_DEMO"] = "1"

from app.main import app          # noqa: E402
from app.database import engine    # noqa: E402
from app.models import Base        # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def seeded_passage(client):
    p = client.get("/api/passages").json()[0]
    detail = client.get(f"/api/passages/{p['id']}").json()
    return detail
