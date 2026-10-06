-- 校勘台数据库初始化（docker-entrypoint-initdb.d 自动执行）。
-- 应用本身使用 SQLAlchemy create_all 建表；此脚本只准备扩展。
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 原转录保护触发器：应用首次建表后由 scripts/install_guard.sql 安装
-- （`! psql ... -f scripts/install_guard.sql`）。设计要点：
--   witnesses.raw_transcription 为只追加审计对象，校勘/对齐流程在应用层
--   从不写该列；确需修订转录时，事务内 SET app.allow_raw_revision = on
--   并通过专门修订接口留下修订原因。
