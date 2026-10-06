"""运行配置。只依赖标准库 + 环境变量，保持精简环境可运行。"""
import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    database_url: str
    collatex_mode: str  # auto | http | cli | internal
    collatex_url: str
    collatex_cli: str
    seed_on_startup: bool


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./jiaokan.db"),
        collatex_mode=os.getenv("COLLATEX_MODE", "auto"),
        collatex_url=os.getenv("COLLATEX_URL", "http://localhost:7369/collate"),
        collatex_cli=os.getenv("COLLATEX_CLI", "collatex"),
        seed_on_startup=os.getenv("SEED_ON_STARTUP", "true").lower() == "true",
    )
