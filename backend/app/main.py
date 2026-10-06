# -*- coding: utf-8 -*-
"""FastAPI 入口。

啟動：
    DATABASE_URL=sqlite+pysqlite:///./dev.db \\
        uvicorn app.main:app --reload
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes import router
from .config import get_settings
from .database import SessionLocal, engine
from .models import Base

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo:
        from .seed import seed_if_empty
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="古籍並列見本校勘系統", version="1.0.0",
              lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/api/health", tags=["meta"])
def health():
    db_kind = "postgresql" if settings.database_url.startswith("postgres") \
        else "sqlite"
    return {"status": "ok", "database": db_kind,
            "collatex_url": settings.collatex_url or None,
            "note": "CollateX 不可達時自動使用內建比對器，run.engine 標明來源"}


# 前端構建產物（vue/vite build 後生成）；不存在時不影響 API
_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if (_DIST / "index.html").is_file():
    from fastapi.responses import FileResponse

    app.mount("/assets", StaticFiles(directory=_DIST / "assets"),
              name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(_DIST / "index.html")
