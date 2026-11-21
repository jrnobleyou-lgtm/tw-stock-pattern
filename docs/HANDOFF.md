# 交接文件（主檔，每次自動載入）

整理自舊的 HANDOFF 1～4（2026-11-12～11-19；舊檔在 `docs/archive/`，要查歷史才翻）。最後整理 11/21。工作規則看 CLAUDE.md。

## 碰到哪個主題，先去讀對應那一份（不要整包都讀）
| 要處理 | 先讀 |
|---|---|
| Worker API、KV 額度、資料來源 | `docs/topics/data.md` |
| 排程（觸發、時間表） | 本檔第 2 節 |
| 型態、盤整、DMI、強勢、標籤、趨勢通道 | `docs/topics/patterns.md` |
| 網頁畫面、K 線視窗、按鈕、外觀開關 | `docs/topics/frontend.md` |
| 新聞、AI、目標價、月營收／EPS／FinMind | `docs/topics/news-finance.md` |
| 族群試算表、每週同步、美股、ETF | `docs/topics/groups-us-etf.md` |

## 1. 部署與分支
- 網址 `https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev/`；GitHub `jrnobleyou-lgtm/tw-stock-pattern`（公開）。`main`＝程式＋台股資料，`deploy`＝自動產生（只有 `site/`）。
- **新對話開在 `claude/*` 工作分支，可能含還沒上線的改動**：讀碼、推送一律以 `origin/main` 為準；要推 main 時用乾淨工作樹：`git worktree add /tmp/mainwt origin/main`，只 checkout 要上線的檔案、commit、`git push origin HEAD:main`（不要在工作分支 `pull --rebase`，會衝突；`git push -f` 被擋）。
- Cloudflare Workers 專案 `news-findstockpattern-swing-breakout`，Production branch `deploy`，部署指令 `npx wrangler deploy --assets=./ ...`，讀 `site/wrangler.jsonc`（KV 綁定 `US`）。
- 沒自動建置時：API `POST /accounts/{acc}/builds/triggers/{trigger_uuid}/builds` 帶 `{"branch":"deploy"}`（trigger 用 `GET .../builds/workers/{script_tag}/triggers` 查）；Cloudflare 金鑰在本雲端環境 network secret。
- 部署看門狗：Worker cron 每 10 分，最後一次建置比最新 deploy 舊超過 4 分鐘就補建置（secret `CF_BUILD_TOKEN`）；KV `deploy/check`、`deploy/last`，設定頁可看。
- 推完要比對線上與 deploy 分支，**5～10 分鐘後再 curl 線上 grep 新程式碼一次**（曾被盤中循環舊版蓋掉）。使用者說「沒變」先查線上檔案。
- 只改資料檔推 main 不一定觸發 update.yml（路徑已含 `data/rev/**`、`data/eps_*.json`、`data/fin_meta.json`、margin 檔、族群檔），其他要手動觸發。
- 美股頁（存在 KV）要等 `us.yml` 跑完才會更新；`us.yml` 同時只跑一個，新觸發會取消排隊中的舊的。
- 不能用：`gh run cancel`（被擋，等結束或請使用者按）、`git push -f`（被擋）。

## 2. 排程
- 觸發主力＝Cloudflare Worker cron `*/10`（`jobsAt()` 判斷，用 secret `GH_TOKEN`［永不到期］呼叫 workflow_dispatch）；GitHub cron 留作備援。`cron/last` 記最後觸發（新聞不寫）；新聞觸發失敗記 `cron/newsfail`。
| workflow／任務 | 台灣時間 | 內容 |
|---|---|---|
| `update.yml` | 上櫃 15:10–17:40、上市隔天 06:00–07:30 每 30 分；push main 也跑 | `daily_update.py`→`build_prices.py`→`analyze.py all`→ETF→市場情緒→固定檢查（失敗不發布）→推 deploy |
| `intraday.yml` | 交易日 08:50 起單一長工作循環到 13:50 | `intraday_loop.sh`：每輪 `/api/mis` 取現價→重算→推 deploy；每輪先 checkout origin/main 的 index.html／worker.js／scripts 等；連 10 輪無今日資料且過 09:20＝休市結束 |
| `us.yml` | 週二～六 08:10 | `us_sync.py pull`→`us_fetch.py`→`us_fin.py`→市場情緒→`analyze.py us`→`make_us_page.py`→`us_sync.py push` |
| `news.yml` | Worker：平日 06:00–23:30 每 30 分、夜間加 01:00／03:30、週末每小時；GitHub 每小時備援 | 新聞＋重訊＋目標價，細節見 news-finance.md |
| `weekly-adjust.yml` | 週日 05:00 | Yahoo 核對除權息（只替換近 2 年） |
| 每週六族群同步 `trig_01C1hrzzY2io3gRmGr7zX3ce` | 週六 15:15 | 照 `weekly-sync` 技能同步族群＋關注清單（使用者建，只有他能改） |
| 新聞日報 `trig_01Uhcg4uxGQoczg7zAGxg21B` | 每天 07:47 | Haiku，我能改；已含 alert 第一行 |
- **交易日 08:50–13:50 不推 main**（盤中循環會用 main 的檔案）；週末、休市日可推。

## 固定檢查（上線前）
- `python3 -m unittest discover -s scripts/tests`（目前 68 項）。
- 上線前：`python3 scripts/analyze.py all` 後 `NODE_PATH=$(npm root -g) node scripts/ui_check.js`（所有篩選鈕、族群、ETF、K 線＋消息分頁、美股模式；跑約 5 分鐘，放背景；`UI_LIVE=<網址>` 讀線上個股檔），pageerror 要 0。
- 截圖用 Playwright（`NODE_PATH=$(npm root -g) node`）；動到標題列／導覽列要量間距（見 CLAUDE.md）。

## 使用者已定、不要再提
- 登入防連續猜密碼不做；美股新聞／月營收不做；Haiku 付費不買（免費 Gemini 夠用）；權值股門檻、本週強勢（大型）5% 維持；KD 條件維持；減資不補；GitHub 上的資料來源歷史不清；data.js 不再瘦身；NAAIM 不做（改成付費）。
- 「長榮」＝長榮航 2618。

## 長歷史（2 年線，台股 480／美股 504）：台股 3 年版 11/21 已上線
- 台股歷史已補到 2023-11（3 年）：`data/hist_old`、`exdiv_old`、`adjust_old.csv` 已進 main；`build_prices` 預設 `HIST_FROM=2023-11-01`。驗證過：接縫（2330 11/8 收 1090→11/11 收 1085）、±11% 跳動、全市場前後比對只 2 檔狀態＋2 檔形態不同、ui_check 412 畫面 0 錯誤。
- **5 年版（使用者還沒要，新對話問他）**：2021-06 起的合併資料**已在 main**（`data/hist_old` 2021～2024 四檔＋`adjust_old.csv`，`data/fm` 原始檔不用再留）。要做只剩：`build_prices` 的 `HIST_FROM` 改 `2021-06-01`→analyze→驗證（接縫、±11% 跳動、全市場前後比對、ui_check）→**先量 `site/h` 大小與建置時間再決定上線**。
- 美股 5 年不急（使用者定）：`us_fetch.py` `KEEP_DAYS=800` 改 1900 並首抓 5y。

## 待辦（使用者 11/21 已驗收：趨勢通道、畫線、市場情緒、小工具、試算表同步等）
0. **11/21 晚三件事已上線**：畫的通道納入比對與篩選（`dch`）、設定頁「全市場比對紀錄」、設定頁靛藍毛玻璃「回台股／回美股」鈕；「全市場型態比對」鈕改成自製視窗（點旁邊關閉）：只重算畫線股（`recompare.yml`，約 3～4 分）或全部（台股約 6 分）。細節見 data.md「畫線比對」。型態介紹頁已拆成上升／下降趨勢通道兩則。
1. **日期提醒（使用者 11/21：平常不要提，11/24 當天提醒一次就好）**：回報目標價每天新增檔數與事欣科 4916 有沒有進來；2454 目標價是否出現；專業機構多空比 11/26 感恩節那週延到下週一公布。（已設 11/24 的排程提醒）
2. **觀察**：新聞補漏（11/19 推上，各家篇數、AI 每日用量有沒有爆；萬泰科 6190 要出現在消息頁）；2412 短通道若使用者再說不像，調 `patterns.py _chan_cands`。
3. **之後再說**：畫線杯柄的伸縮（第二階段，直線／平行線／水平線已做）；個股空單比例（FINRA）；ETF 成分股連結、折溢價、規模；季營收以外的美股功能（52 週新高低、相對強度、財報日跳空）；重訊按鈕名稱（「今天有重訊」或「最新重訊」）看 `meta.mops.check` 決定；Opus 審查剩下的小項（`/api/mis`、`/api/quote` 公開、Cloudflare 每月建置分鐘數、index.html 台美分支集中成設定表〔不建議現在拆〕）。
- 已上線的 VIX／CNN／黑天鵝市場情緒：`scripts/sentiment.py`，Actions 抓得到 CNN、本雲端抓不到；細節見 frontend.md。
- 交接檔濃縮規則（主檔 80 行、主題檔 50 行／5KB、單行 300 字）見 CLAUDE.md；舊版細節在 `docs/archive/`。
