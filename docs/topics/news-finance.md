# 主題：新聞、重訊、目標價與財報

新聞來源與 AI、目標價、月營收／EPS／三率／估值、FinMind。

## 新聞／重訊／目標價
- `scripts/news.py`：經濟日報、工商、鉅亨（API＋逐檔搜尋 `search_arts`，`meta.rot`）、MoneyDJ（排除 5850web）、中央社、優分析（相對路徑 `/articles/<數字>`）、科技新報、Yahoo股市；抓不到全文＝付費跳過；DIGITIMES／財訊／自由抓不到不做。
- AI：只用 Gemini 免費（secret `GEMINI_API_KEY`），`pick_models()` 自動挑最新正式 flash-lite→flash，新型號先 `self_check()`；全掛寫 `news_fatal.flag`。
  不花錢；kind 盤面不收；同篇轉載比對標題前 18 字。
- 節流：每批 ≤10 篇、批間 7 秒、429 等 50 秒；優先判關注清單＋成交值前 100（`priority_codes()`）；單輪 16 分鐘收工；補抓模式 `backfill=yes`（`NEWS_BACKFILL`）。
- 輸出 news-data 分支（強制推送）：`s/<h%64>.json`、items/seen/tries/meta/daily/mops.json。**防清空**：先 `git ls-remote`，clone 失敗重試 4 次仍失敗不推；文章數少一半以上不推。發布前 `rm -f targets.json`。
- 近期消息偏多／偏空（`news_bias()`）：近 7 天、只算事件＋法人、同檔同天同方向一次、差 ≥2。
- 重訊 `scripts/mops.py`（鉅亨公告分類＋證交所／櫃買開放資料隔天校正）；「今天有重訊」＝上一交易日 13:30 後；連續重複只算第一次。
- 目標價 `scripts/targets.py`：FactSet 速報（`factset_rows`，每 2 小時）＋具名券商句子；0.3～3 倍現價、60 天、同家留最新、≥3 家才算最高／中位數／最低；存 KV `state/targets_tw.json`，**只有登入看得到**（`SHOW_TARGETS` 預設關）。
- 關注清單：KV `state/watchlist_tw`，由 `scripts/apply_watchlist.py`（<20 檔拒寫）寫入，來源試算表分頁「關注股票_台股」，每週同步 skill 處理。不放 GitHub。
- 設定頁：各來源篇數（連 3 輪 0 篇標紅）、每日新聞判斷統計、各 AI 型號工作狀況（`daily.json` 的 `api`）。
- 改版排查：`curl -s -m 20 -A "Mozilla/5.0" <網址>`，200 有內容＝改版，403／429／空白＝被擋；抽取程式要正規化網址、標題取最長片段、每家獨立 try/except。

## 財報與估值
- 月營收 `scripts/revenue.py`（`data/rev/<YYYY-MM>.json` 千元；`due()`：1～12 號每天，其他週日或有營收重訊）。
- EPS `scripts/eps.py`（`data/eps_cum.json` 官方累計＋`data/eps_fm.json` FinMind 單季，`single()`、`ytd()`）；三率 `scripts/margins.py`（`margin_cum/fm.json`，金融業無毛利率顯示「—」）。
- 不足 13 個月不標月營收創新高、不足 36 個月不標年增新高。補資料指令：`revenue.py backfill`、`eps.py backfill`、`margins.py backfill`（可續跑；環境變數 `REV_DIR`／`EPS_FM`／`MARGIN_FM` 指到 scratchpad）。
- **FinMind**：金鑰存本環境 network secret（api.finmindtrade.com）；免費版只能逐檔查、約 8 秒一次、402 要等整點；**使用者平日白天自己在用，回補要台灣 18:00 後**。GitHub Actions 用要 Secrets `FINMIND_TOKEN_1／_2`（第一把優先）。
- PE／PB／殖利率 `scripts/valuation.py`：上市 `BWIBBU_d`、上櫃 `tpex_mainboard_peratio_analysis`（日期要和上市同天）；每檔 `pe/pb/dy/pq/pl`、`data.js` 的 `valDate`；盤中不跳，固定收盤值。
