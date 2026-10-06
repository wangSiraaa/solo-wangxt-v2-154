# 古籍並列見本校勘系統

比較同一段文字的多個**見本（witness）**，並在學理上把三類東西嚴格分開：

* **異體字／異文**——原字形（`爲/徳`）與比對用規範形（`為/德`）**分欄保存**；
* **脫文／增衍**——由字符級對齊產生，且只是**系統建議**，須研究者下人工判斷；
* **批注、缺葉、空白正文、插入片段、未知字**——各自是獨立記號類型，
  **絕不與普通文字差異混成一類**。

技術棧：**FastAPI + Vue 3 + PostgreSQL**，對齊優先呼叫 **CollateX**，
不可達時自動退回內建的 Needleman–Wunsch 多見本比對器，每次運行都記錄實際引擎。

---

## 一、原轉錄記號（輸入見本時使用）

| 記號 | 含義 | 系統行為 |
|---|---|---|
| 普通漢字 | 正文 | TEXT token，參與對齊 |
| `，。；：…` 等 | 標點 | PUNCT，**是否參與對齊由勾選開關決定** |
| `〖缺葉〗` | 整葉脫失 | LACUNA 佔位，蓋入欄位並標「缺葉」，**不算脫文** |
| `【空白】` | 漫漶／留白正文 | BLANK，與缺葉為不同類型 |
| `□` | 字位存而字形未知 | UNKNOWN，**永不被猜補成別的字** |
| `〔批：……〕`、`〔眉：……〕`、`〔注：……〕` | 批注 | ANNOTATION，錨定於前一正文之字之後 |
| `〔插：……〕` | 後人鈔補／插入片段 | INSERTION，同樣錨定相鄰位置 |

批注與插入不進入正文比對序列，只記 `anchor_after_position`，
所以既不會被誤判為脫文，調整對齊時也不會丟失其位置。

## 二、資料模型（不毀原則）

* `witnesses.raw_transcription`：**原轉錄原文，永不被對齊改動**。
* `tokens.orig` / `tokens.norm`：原字形與比對形分開；規範規則只改 `norm`。
* `transcript_revisions`：轉錄每次修改留史，舊文本可追溯。
* `collation_runs`：每次對齊／調整生成一版 JSON 快照（版本化），
  人工調整**新增 run 而不改舊 run**。
* `judgments`：研究者結論，與欄位裡的 `suggested_kind`（自動建議）分表存放，
  匯出時兩者並列，自動建議不會冒充人工結論。

後端硬性守衛：移動 `□`（未知字）到其他字欄會回 `422` 並拒絕。

## 三、快速開始

### 本機開發（無 Docker，用 SQLite）

```bash
# 後端
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cd backend
DATABASE_URL="sqlite+pysqlite:///../data/dev.db" \
COLLATEX_URL="" \
PYTHONPATH=. uvicorn app.main:app --reload

# 前端（另開終端）
cd frontend
npm install
npm run dev          # http://localhost:5173 ，/api 代理到 8000
```

首次啟動自動載入**自制樣本**《松窗讀書記·節錄（擬）》三個見本，
內含：異體字（爲/爲、徳/德）、重複短句（丙本「勿自欺也」重出）、
三種不同斷句、甲本缺葉、乙本空白正文、批注、插入、未知字「□」。

### Docker（PostgreSQL + CollateX）

```bash
docker compose up --build                       # PostgreSQL + API
docker compose --profile collatex up --build    # 連同 CollateX 服務
# 打開 http://localhost:8000
```

> `collatex` 的鏡像需替換為你實際使用的 CollateX REST 服務
> （見 `docker-compose.yml` 中 TODO）。它不可達時系統自動用內建比對器，
> 每筆 run 的 `engine` 欄會標明 `collatex` / `builtin` / `manual`。

## 四、操作流程

1. **並列見本**：查看各本原轉錄，記號依類型著色；新增見本時可先「預覽分詞」。
2. **規範規則**：如 `峯 → 峰`，只影響比對形，原字形照舊。
3. **對齊**：選擇「標點是否參與」，生成候選；缺葉/空白/批注/插入列在記號區。
4. **人工判斷**：點選任一欄，看到各本異同、系統建議，再選人工類別並寫校記理由。
5. **人工調整**：拆欄／移字生成新版本；舊版本、舊判斷、原轉錄全部保留。
6. **匯出**：JSON / CSV / Markdown 校勘記，含每個見本的**來源**與
   自動建議—人工判斷的**校勘關係**，記號（缺葉等）及錨點另段列出。

## 五、API 摘要

```
POST /api/passages/{id}/witnesses      建見本（自動分詞＋規範化）
PATCH /api/witnesses/{id}/transcription 改轉錄（留修訂史）
POST /api/passages/{id}/rules          加規範規則（orig 不動）
POST /api/preview                      貼文本預覽 token 類型
POST /api/collate                      {passage_id, include_punctuation, use_collatex}
PUT  /api/runs/{id}/judgments          人工判斷（kind + rationale）
POST /api/adjust                       move_cell / split_col / merge_col（出新 run）
GET  /api/runs/{id}/export?fmt=json|csv|md
```

## 六、測試

```bash
pytest tests/ -q
```

28 個測試覆蓋：記號解析（缺葉≠空白、批注/插入錨定、未知字不猜補）、
規範化分欄、異體對齊、重複短句不錯位、斷句開關、人工判斷與建議分離、
未知字移動守衛、調整版本化、轉錄修訂史、三種匯出。
