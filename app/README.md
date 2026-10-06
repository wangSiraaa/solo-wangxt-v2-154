# 古籍并列见本校勘台

面向文献研究者的多见本（witness）并列校勘工具：**Vue 3** 展示并列见本与校勘条目，
**FastAPI** 调用 **CollateX** 生成对齐候选（无 CollateX 时退回内置渐进比对并如实标注），
**PostgreSQL** 保存原转录、规范化规则、自动候选与人工判断。

## 核心原则

| 原则 | 落地方式 |
| --- | --- |
| 原字形与规范形分别保留 | `witnesses.raw_transcription` 逐字符照录；规范化只写进对齐 token 的 `norm`，显示与导出始终带原字形 |
| 异体字 / 脱文 / 批注不混成一类 | 受控词表 11 类（`glyph_variant`、`omission`、`lacuna`、`annotation` 等），批注根本不进对齐列 |
| 标点是否参与对齐明确可选 | 每次运行带 `include_punctuation` 参数；两次运行各自留存，可回看对比 |
| 自动建议不替代研究者结论 | 列上 `suggested_*` 与 `researcher_*` 两套字段，界面分区、API 分端点，互不相覆 |
| 缺叶 ≠ 空白正文 | 解析为 `lacuna`（带缺几叶/几行）与 `blank` 两种 token，分类器拒绝与实字混列 |
| 插入片段锚定相邻位置 | `［批注：…］［添：…］［按：…］` 不占正文字位，带 `anchor_after / anchor_before` |
| 调整对齐不删原转录、不猜未知字 | override 只重建列快照；`□` 与实字合并/relink 返回 422；实字抹成缺文返回 422 |
| 导出含来源与校勘关系 | JSON（全量）、CSV（校勘表）、TEI XML（`<app>/<rdg>`，缺叶 `<lacuna>`、未知字 `<g type="unknown">□</g>`） |

## 原转录标记语法

```
〔缺〕〔缺三行〕〔缺二叶〕       缺叶/缺文（物理缺失，区别于脱文）
〔空白〕                        版面留白
□  □三                          残泐未知字（一个 □ 一个字位；永不据他本猜补）
［批注：燈下似有老人影］         天头/行间批注（锚在它前面字位之后）
［添：此處疑有脫簡］             栏外添补
［按：□當是『已』字，存疑不補］  整理者按语
【峯→峰】                        就地字形—规范形记录（显示峯，匹配峰）
```

其余汉字逐字切分；标点单独成 token，是否入对齐由运行参数决定。

## 快速开始（SQLite 离线模式，无需数据库/JDK）

```bash
cd backend
python3 -m pip install -r requirements.txt          # 离线可只用 fastapi uvicorn sqlalchemy pydantic httpx
DATABASE_URL='sqlite:///./jiaokan.db' COLLATEX_MODE=internal \
  uvicorn app.main:app --port 8000
# 启动自动建表并写入自制样例（《北山夜誦》拟古残卷，甲/乙/丙三个见本）

cd ../frontend
yarn install && yarn dev          # http://127.0.0.1:5173 （已配置 /api 代理到 8000）
```

## PostgreSQL + CollateX（完整形态）

```bash
docker compose up --build db backend frontend       # 先起核心三件套
psql "postgresql://jiaokan:jiaokan@localhost:5432/jiaokan" \
  -f backend/scripts/install_guard.sql             # 可选：安装原转录保护触发器
docker compose --profile collatex up collatex       # 需要真正 CollateX 时
```

- 后端 `COLLATEX_MODE`：`auto`（默认，探测 `http://localhost:7369/collate` 与 `collatex` CLI，失败退回内置实现并在 `collation_runs.engine` 标注 `internal-fallback`）、`http`、`cli`、`internal`。
- CollateX 输入按 `{"t": 原字形, "n": 规范形}` 的 token JSON 提交，Dekker 算法；标点/批注在送入前按参数过滤。

## API 概览

| 方法 路径 | 说明 |
| --- | --- |
| `POST /passages` / `GET /passages/{id}` | 段落与见本（raw_transcription 随见本保存） |
| `GET /passages/{id}/parse` | 预览原转录的 token 解析（不改数据） |
| `GET/POST /rules/passage/{id}`、`PATCH/DELETE /rules/{id}` | 规范化规则，可随时停用后重跑 |
| `POST /collations/run` | 生成对齐候选（`include_punctuation` 开关） |
| `GET /runs/{id}` | 列矩阵 + 批注锚点 + 调整历史 |
| `PUT /columns/{id}/judgment` | 写研究者结论（受控词表 + 按语 + 确认） |
| `POST /runs/{id}/overrides` | `split / merge / relink / mark_lacuna / anchor_insert`，带安全守卫 |
| `GET /runs/{id}/export.{json|csv|xml}` | 导出见本来源与校勘关系 |

## 自制样例覆盖的情形

《北山夜誦》残卷（纯虚构）三个见本：异体字（嵗/歲、峯/峰、覌/曉）、丙本缺二叶后紧跟卷面空白、
残泐 □（按语明确"存疑不补"）、乙本重复短句「燈火熒然。」、甲/乙/丙三处对"夜分誦聲"的不同断句、
丙本脱「窓月皎然，了無人跡」一段、三条批注/添补/按语。

## 验收测试

```bash
cd backend
PYTHONPATH=. DATABASE_URL='sqlite:///./test.db' COLLATEX_MODE=internal \
  python3 scripts/test_e2e.py
```

10 个用例覆盖：原字形保留、规范层匹配、脱文与缺叶/空白分类、未知字守卫、
标点开关双运行、自动/人工字段独立、调整不改原转录、批注锚点、三种导出内容。
