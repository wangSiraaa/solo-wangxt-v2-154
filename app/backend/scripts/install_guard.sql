-- 在 SQLAlchemy 建表（应用已启动过一次）之后安装：
--   psql "$DATABASE_URL" -f scripts/install_guard.sql
CREATE OR REPLACE FUNCTION raw_transcription_guard() RETURNS trigger AS $$
BEGIN
  IF OLD.raw_transcription IS DISTINCT FROM NEW.raw_transcription
     AND current_setting('app.allow_raw_revision', true) IS DISTINCT FROM 'on' THEN
    RAISE EXCEPTION 'raw_transcription 受保护：转录修订必须走专门修订流程并记录原因';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_guard_raw_transcription ON witnesses;
CREATE TRIGGER trg_guard_raw_transcription
BEFORE UPDATE ON witnesses
FOR EACH ROW EXECUTE FUNCTION raw_transcription_guard();
