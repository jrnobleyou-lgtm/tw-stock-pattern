# 交接文件（主檔，每次自動載入）

整理自舊的 HANDOFF 1～4（2026-11-12～11-19，最後更新 11/19 深夜；舊檔在 `docs/archive/`，要查歷史才翻）。工作規則看 CLAUDE.md。

## 碰到哪個主題，先去讀對應那一份（不要整包都讀）
| 要處理 | 先讀 |
|---|---|
| Worker API、KV 額度、資料來源、排程細節 | `docs/topics/data.md` |
| 型態、盤整、DMI、強勢、標籤規則 | `docs/topics/patterns.md` |
| 網頁畫面、K 線視窗、按鈕、外觀開關 | `docs/topics/frontend.md` |
| 新聞、AI、目標價、月營收／EPS／FinMind | `docs/topics/news-finance.md` |
| 族群試算表、美股、ETF | `docs/topics/groups-us-etf.md` |

## 1. 部署
- 網址 `https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev/`；GitHub `jrnobleyou-lgtm/tw-stock-pattern`（公開）。`main`＝程式＋台股資料，`deploy`＝自動產生（只有 `site/`）。
- Cloudflare Workers 專案 `news-findstockpattern-swing-breakout`，Production branch `deploy`，部署指令 `npx wrangler deploy --assets=./ ...`，讀 `site/wrangler.jsonc`（KV 綁定 `US`）。
- 沒自動建置時：API `POST /accounts/{acc}/builds/triggers/{trigger_uuid}/builds` 帶 `{"branch":"deploy"}`（trigger 用 `GET .../builds/workers/{script_tag}/triggers` 查）；Cloudflare 金鑰在本雲端環境 network secret。
- 部署看門狗：Worker cron 每 10 分，最後一次建置比最新 deploy 舊超過 4 分鐘就補建置（secret `CF_BUILD_TOKEN`）；KV `deploy/check`、`deploy/last`，設定頁可看。
- 推完要比對線上與 deploy 分支，**5～10 分鐘後再 curl 線上 grep 新程式碼一次**（曾被盤中循環舊版蓋掉）。使用者說「沒變」先查線上檔案。
- 只改資料檔推 main 不一定觸發 update.yml（路徑已含 `data/rev/**`、`data/eps_*.json`、`data/fin_meta.json`、margin 檔），其他要手動觸發。
- 不能用：`gh run cancel`（被擋，等結束或請使用者按）、`git push -f`（被擋）。

## 2. 排程
- 觸發主力＝Cloudflare Worker cron `*/10`（`jobsAt()` 判斷，用 secret `GH_TOKEN` 呼叫 workflow_dispatch）；GitHub cron 留作備援。
| workflow | 台灣時間 | 內容 |
|---|---|---|
| `update.yml` | 上櫃 15:10–17:40、上市隔天 06:00–07:30 每 30 分；push main 也跑 | `daily_update.py`→`build_prices.py`→`analyze.py all`→ETF 步驟→固定檢查（失敗不發布）→推 deploy；推送失敗先 pull --rebase |
| `intraday.yml` | 08:50 起單一長工作循環到 13:50 | `intraday_loop.sh`：每輪 `/api/mis` 取現價→重算→推 deploy；每輪先 checkout origin/main 的 index.html／worker.js／scripts 等；連 10 輪無今日資料且過 09:20＝休市結束；分析連 3 輪失敗讓工作失敗 |
| `us.yml` | 週二～六 08:10 | `us_sync.py pull`→`us_fetch.py`→`us_fin.py`→`analyze.py us`→`make_us_page.py`→`us_sync.py push` |
| `news.yml` | Worker：平日 06:00–23:30 每 30 分、週末每小時；GitHub 每小時備援 | 新聞＋重訊＋目標價，見第 7 節 |
| `weekly-adjust.yml` | 週日 05:00 | Yahoo 核對除權息（只替換近 2 年，舊事件保留） |
- `cron/last` 記最後觸發（新聞不寫）；新聞觸發失敗記 `cron/newsfail`。
- `GH_TOKEN` 永不到期（使用者確認）。
- **盤中 08:50–13:50 不推 main**（盤中循環會用 main 的檔案）。

## 固定檢查（上線前）
- `python3 -m unittest discover -s scripts/tests`（engine、patterns、dmi、island、margins、targets、strong、weights、exadj、pipeline〔只讀固定案例〕、news_models、worker…）。
- 上線前：`python3 scripts/analyze.py all` 後 `NODE_PATH=$(npm root -g) node scripts/ui_check.js`（所有篩選鈕、族群、ETF、K 線＋消息分頁、美股模式；`UI_LIVE=<網址>` 讀線上個股檔），pageerror 要 0。
- 截圖用 Playwright（`NODE_PATH=$(npm root -g) node`），本機用線上 data.js 做原型。

## 使用者已定、不要再提
- 登入防連續猜密碼不做；美股新聞／月營收不做；Haiku 付費不買（免費 Gemini 夠用）；權值股門檻、本週強勢（大型）5% 維持；KD 條件維持；減資不補；GitHub 上的資料來源歷史不清；data.js 不再瘦身。
- 「長榮」＝長榮航 2618；ANT（Anthropic）上市時使用者會通知：主族群軟體、副族群資安，不排程。

## 待辦與提醒
- 一週後（約 11/25）回報目標價每天新增檔數、事欣科 4916 有沒有進來。
- ANT（Anthropic）已於 11/20 加入美股（主族群 網路/軟體、副族群 資安，已寫 KV，手動跑 us.yml）；待確認 ANT 出現在美股頁。
- 重訊按鈕名稱（「今天有重訊」或「最新重訊」）看 `meta.mops.check` 後決定（待確認是否已定）。
- ETF 成分股連結（Yahoo `/quote/{代號}.TW/holding`、MoneyDJ）、折溢價、規模：使用者說之後再說。
- 季營收以外的美股功能（52 週新高低、相對強度、財報日跳空）待使用者決定。
- Opus 審查剩下的小項：`/api/mis`、`/api/quote` 公開（出事再說）、Cloudflare 每月建置分鐘數要到後台查、index.html 台美分支集中成設定表（不建議現在拆）。
- 美股試算表分頁「工作表1」是否改名「族群分類」（待確認）。
- 新聞補漏（11/19 推上，工商／科技新報／Yahoo 研究報告／MoneyDJ 多分類）待觀察一兩天：各家篇數、AI 每日用量有沒有爆；萬泰科 6190 那篇要出現在消息頁。
- 排程：每天 07:47 新聞日報 `trig_01Uhcg4uxGQoczg7zAGxg21B`（Haiku，我能改；daily.json 有 alert 要第一行照抄，待確認是否已加）。
- 交接檔濃縮規則（每份 ≤200 行、超過 160 行提醒）見 CLAUDE.md；舊版細節在 `docs/archive/`。
