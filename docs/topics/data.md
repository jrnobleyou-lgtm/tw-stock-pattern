# 主題：排程資料與後端

Worker API、KV 額度、資料來源限制。上層索引見 docs/HANDOFF.md。

## Worker API
- `/api/quote?s=`：台股走證交所 MIS（重試 3 次）再退 Yahoo；美股 Yahoo 即時。回傳**不含 `src`**（前端用 `q.delay>0` 顯示「延遲約20分」）。
- `/api/mis`（批次現價）、`/api/tx`（台指期，期交所常回 520 改用 Yahoo 奇摩 `WTX&,WTX00`）、`/api/macro`（匯率／油／美債；`?m=US` 道瓊／標普／那指／費半／VIX）。
- `/api/news?c=`：讀 raw.githubusercontent news-data 分包（200 快取 300 秒、404 60 秒）。
- `/api/draw?m=&c=`（GET 公開、美股要登入、POST 管理者）、`/api/draw-list`（`span=1` 公開、90 秒快取、快取鍵只看 span；`all=1` 要登入）。
- `/api/targets?c=&close=`（要登入）、`/api/alerts`（要登入）。
- `/admin/*` 管理者專區：密碼 PBKDF2 存 KV `auth`；cookie `us_auth`（Path=/、HttpOnly）＋`adm=1`（前端判斷，Worker 會補）。`/admin/settings` 設定頁。
- `/admin/s/<代號>.json` 用文字搜尋切單檔（JSON.parse 會超 10ms CPU）；`/admin/f/<代號>.json` 美股財報。
- `/api/us-ingest`：OIDC 只認 main；`githubOidcOk` 回 full（只有 us.yml）或 limited（只能讀 `state/watchlist_tw`、讀寫 `state/targets_tw.json`）。
  `X-Ingest-Key`（secret `US_INGEST_KEY`）全權限；GET 只能讀 `site/`、`state/`、`meta`。
- 紅色提醒：`/api/alerts` 來源 KV `intraday/stale`（看門狗平日 09:20–13:40 發現 deploy 超過 15 分沒更新）、`cron/newsfail`、`deploy/check` 非正常；前端 `alertPoll()` 只在 `adm=1` 時每 5 分抓，顯示在頁首導覽下方（sticky），文字白話，休市日可能誤報一次。
- 頁面外觀：Worker `page()`（登入／設定頁）也讀 localStorage `work`（上班模式），改外觀兩邊都要改。
- 固定檢查：`scripts/tests/worker_check.js`（由 `test_worker.py` 呼叫）。

## KV 與額度
- 免費方案每天寫入 1000 次（台灣 08:00 重置），超過出錯 1101。**美股失敗重跑一天不要超過 2～3 次**；手動推前先看當天用量。
- 美股 K 線（方案 B，`scripts/us_store.py`）：底包 `site/sh/<h%256>`＋近期包 `site/rc/<h%16>`，存日期字串；週六／近期包 >12 根等條件整理（約 285 筆），平日約 28 筆；`check_cap()` 一次 >400 筆就停。分包雜湊 `h=(h*31+charCode)%1000003`。
- 其他鍵：`site/index.html`、`site/data.js`、`site/fn/<0-31>.json`、`state/hist_<0-7>.csv.gz`、`state/groups_us*.csv`、`state/watchlist_tw`、
  `state/targets_tw.json`、`draw/<TW|US>/<代號>`、`auth`、`meta`、`cron/*`、`deploy/*`、`intraday/stale`。
- 美股頁面存在 KV：前端改動要等下次 us.yml push 才換新。`site/.assetsignore` 排除 `us`、`us/*`。

## 資料來源與限制
- 台股日 K：證交所／櫃買 OpenAPI。除權息：上市當天由 `scripts/exadj.py` 算（收盤－漲跌價差＝參考價，差 >0.04%；價差 0 時要 TWT48U_ALL 有列），`daily_update.py` 呼叫，寫 `adjust.csv`；週日 Yahoo 補漏。只有除權息／分割，沒有減資（使用者定：不補）。
- 三大法人 `fetch_inst()`（BFI82U，僅上市）、外資台指期淨未平倉 `fetch_fut_foreign()`（期交所 futContractsDateDown CSV）；盤中（平日 15:00 前）不重抓，沿用 `site/cache/inst.json`、`fut.json`；抓不到不可放舊數字。
- 權值股股數 `fetch_shares()`（t187ap03_L，排除 91 開頭）、`index_weights()`。
- `analyze.py cached()`：新聞／重訊／畫線／PE／股數抓不到時讀線上 `/cache/<名稱>.json`（`site/cache/` 不進版控）。
- 盤中判斷要求暫時價日期＝台灣今天；各程式「今天」一律台灣日期。
- 不碰 mops.twse.com.tw／mopsov（觀測站擋程式、條款只允許開放資料）。證交所 mis `all_etf` 本環境被擋。
- 網站不公開寫資料來源（頁尾「資料來自公開市場資訊」）；新聞媒體名稱保留。GitHub 歷史不動。

## 畫線比對（11/21）
- `analyze.py`：`drawn_channels()` 把管理者畫的通道（kind=chan、4 點）用最新價算在通道內／出界，存 `stocks[code].dch`（篩選鈕 chin／chup／chdn 都算）；時間重疊的系統通道拿掉。`/api/draw-list?span=1` 對 chan 附 `pts`。
- 「只重算畫線股」：`recompare.yml`（`ONLY_DRAWN=1 LIVE_DIR=live`）算畫線股＋線上資料還帶畫線結果的股票（移除畫線也會補回系統通道），`merge_partial.py` 補進 deploy 的 data.js／s/；族群統計不動。結果檔 `recmp.json`（不進版控）給設定頁顯示，按鈕時間記 KV `recmp/log`。
- 移除畫線後系統不會自動補，要按鈕重算。美股只有「全部」。

