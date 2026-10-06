"""FastAPI 入口。

启动时建表并（默认）写入自制样例数据。生产使用 PostgreSQL：
  DATABASE_URL=postgresql+psycopg://jiaokan:jiaokan@localhost:5432/jiaokan
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import Base, SessionLocal, engine
from .routers import collation, passages, rules

settings = get_settings()
app = FastAPI(title="古籍并列见本校勘台", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)
app.include_router(passages.router)
app.include_router(rules.router)
app.include_router(collation.router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    if settings.seed_on_startup:
        from .seed import seed_if_empty
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()


@app.get("/health")
def health():
    return {"status": "ok", "collatex_mode": settings.collatex_mode,
            "database": settings.database_url.split("://", 1)[0]}
