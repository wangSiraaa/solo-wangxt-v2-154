# -*- coding: utf-8 -*-
"""應用設定。

資料庫預設使用 PostgreSQL；本機展示與測試時可切換到 SQLite：

    DATABASE_URL=sqlite+pysqlite:///./collation.db uvicorn app.main:app

CollateX 若未啟動（DOCKER 中的 collatex 容器），
後端會自動退回內建的漸進式多序列比對器，
日誌中會標明每一次對齊候選的實際來源，便於研究者辨識。
"""
from __future__ import annotations

import os
from functools import lru_cache


class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://collator:collator@localhost:5432/collation",
    )
    # CollateX REST 服務位址；留空或連線失敗時改用內建比對器
    collatex_url: str = os.getenv("COLLATEX_URL", "http://localhost:7369")
    collatex_timeout: float = float(os.getenv("COLLATEX_TIMEOUT", "10"))
    cors_origins: list[str] = ["*"]
    # 首次啟動時載入自制古籍樣本
    seed_demo: bool = os.getenv("SEED_DEMO", "1") != "0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
