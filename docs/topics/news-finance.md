# 主題：新聞、重訊、目標價與財報

## 新聞來源（`scripts/news.py`）
- 經濟日報（股市／產業／要聞）、工商（stock＋tech＋industry）、鉅亨（API＋逐檔搜尋 `search_arts`、`meta.rot`，每分類重試 3 次）、MoneyDJ（MB010000＋MB06＋MB07＋MB070100，排除 5850web）、中央社、優分析（`/articles/<數字>`）、科技新報（finance＋全部）、Yahoo股市（tw-market＋research）。
- 抓不到全文＝付費跳過；DIGITIMES／財訊／自由抓不到不做；經濟日報兩岸、基金、房地產不補。MoneyDJ 等 RSS 只有最新 20 篇（所以加夜間兩輪）。
- 手動補文章：`data/news_extra.txt` 每行一個網址（已判斷過自動略過）。查漏：抓該站其他分類 RSS，算 `md5(連結)[:16]` 是否在 news-data 的 `seen.json`。
- 改版排查：`curl -s -m 20 -A "Mozilla/5.0" <網址>`，200 有內容＝改版，403／429／空白＝被擋；抽取要正規化網址、標題取最長片段、每家獨立 try/except。

## AI 與節流
- 只用 Gemini 免費（secret `GEMINI_API_KEY`），不花錢；`pick_models()` 自動挑最新正式 flash-lite→flash，新型號先 `self_check()`；全掛寫 `news_fatal.flag`。
- 11/20 使用者決定：暫停 gemini-3.8-flash（太慢）與 gemini-3.5-flash（常忙碌），只留 flash-lite（`BLOCKED_MODELS`，要恢復就拿掉）。
- kind 盤面不收；同篇轉載比對標題前 18 字。每批 ≤10 篇、批間 7 秒；Quota 429 暫停 1 小時、503 只暫停 10 分鐘（待確認：舊寫法「429 等 50 秒」是否仍在）。
- 優先判關注清單＋成交值前 100（`priority_codes()`）；單輪 16 分鐘收工；補抓 `backfill=yes`（`NEWS_BACKFILL`）。
- Worker `jobsAt()` 排程（見主檔）含台灣 01:00、03:30 兩輪夜間新聞。

## 輸出與防呆
- news-data 分支（強制推送）：`s/<h%64>.json`、items/seen/tries/meta/daily/mops.json。**防清空**：先 `git ls-remote`，clone 失敗重試 4 次仍失敗不推；文章數少一半以上不推。發布前 `rm -f targets.json`。
- 近期消息偏多／偏空 `news_bias()`：近 7 天、只算事件＋法人、同檔同天同方向一次、差 ≥2。
- 設定頁：各來源篇數（連 3 輪 0 篇標紅）、每日判斷統計、各型號狀況（`daily.json` 的 `api`、`dirby`＝各型號上修／持平／下修篇數）；最上方「新聞判斷日報（前一天）」由 Worker 讀 daily.json／meta.json 算（`rptBlk`，site/worker.js）。
- 手機通知是每天 07:47 排程 `trig_01Uhcg…`（獨立背景對話，使用者只收到通知）；日報是否讀 `dirby`（待確認，不必問使用者）。

## 重訊、目標價、關注清單
- 重訊 `scripts/mops.py`（鉅亨公告分類＋證交所／櫃買開放資料隔天校正）；「今天有重訊」＝上一交易日 13:30 後；連續重複只算第一次。
- 目標價 `scripts/targets.py`：FactSet 速報（`factset_rows`，每 2 小時）＋具名券商句子；0.3～3 倍現價、60 天、同家留最新、≥3 家才算最高／中位數／最低；存 KV `state/targets_tw.json`，**只有登入看得到**（`SHOW_TARGETS` 預設關）。
- 一句多檔時只收「名稱＋目標價＋價格」緊貼的（`targets._multi`），名稱並排或「分別」不收；`meta.tp_bf2` 一次性補撈 30 天標題含「目標價」的文章（每輪 40 篇）。待查：2454 有沒有資料。
- 關注清單：KV `state/watchlist_tw`，`scripts/apply_watchlist.py` 寫入（<20 檔拒寫），來源試算表分頁「關注股票_台股」，每週同步 skill 處理；不放 GitHub。

## 財報與估值
- 月營收 `scripts/revenue.py`（`data/rev/<YYYY-MM>.json` 千元；`due()`：1～12 號每天，其他日子只在週日或有營收重訊）。
- EPS `scripts/eps.py`（`data/eps_cum.json` 官方累計＋`data/eps_fm.json` FinMind 單季，`single()`、`ytd()`）；三率 `scripts/margins.py`（`margin_cum/fm.json`，金融業無毛利率顯示「—」）。
- 不足 13 個月不標月營收創新高、不足 36 個月不標年增新高。補資料：`revenue.py`／`eps.py`／`margins.py backfill`（可續跑；`REV_DIR`／`EPS_FM`／`MARGIN_FM` 指到 scratchpad）。
- **FinMind**：金鑰在本環境 network secret（api.finmindtrade.com）；免費版逐檔、約 8 秒一次、402 等整點；**使用者平日白天自己在用，回補要台灣 18:00 後**。Actions 用 Secrets `FINMIND_TOKEN_1／_2`（第一把優先）。
- PE／PB／殖利率 `scripts/valuation.py`：上市 `BWIBBU_d`、上櫃 `tpex_mainboard_peratio_analysis`（日期要和上市同天）；每檔 `pe/pb/dy/pq/pl`、data.js `valDate`；盤中固定收盤值。
