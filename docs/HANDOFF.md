# 交接文件：每日股票型態確認

最後更新：2026-11-12。新的 Claude 對話接手時請完整讀過。

## 1. 網站在哪、怎麼部署
- 網址：`https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev/`
- GitHub：`jrnobleyou-lgtm/tw-stock-pattern`（公開）。`main` 放程式與台股資料；`deploy` 是自動產生的發布分支（只有 `site/` 的內容）。
- Cloudflare Workers：專案 `news-findstockpattern-swing-breakout`，Production branch 設 `deploy`，Deploy command 是
  `npx wrangler deploy --assets=./ --name news-findstockpattern-swing-breakout --compatibility-date 2025-01-01`，會讀 `site/wrangler.jsonc`（綁定 KV `US`）。
- Cloudflare 偶爾沒有自動建置：可用 API `POST /accounts/{acc}/builds/triggers/{trigger_uuid}/builds` 帶 `{"branch":"deploy"}` 手動觸發（trigger 用 `GET /accounts/{acc}/builds/workers/{script_tag}/triggers` 查）。Cloudflare 金鑰存在這個專案的雲端環境（network secret），不要另外存。

## 2. 排程（GitHub Actions）
| 檔案 | 時間（台灣） | 做什麼 |
|---|---|---|
| `update.yml` | 上櫃 15:10–17:40、上市隔天 06:00–07:30；push 到 main 也會跑 | 抓官方日 K（`daily_update.py`：證交所 OpenAPI、櫃買 OpenAPI、指數、成交值、台指期歷史）→ 盤中暫時價 → `build_prices.py` → `analyze.py all` → 推 `deploy` |
| `intraday.yml` | 08:50 啟動，一個工作內循環到 13:50（09:25 備援） | `intraday_loop.sh`：每輪向 `/api/mis` 取全市場現價 → 重算型態 → 推 `deploy` |
| `us.yml` | 06:20 週二～週六 | 美股：`us_sync.py pull` → `us_fetch.py`（Yahoo）→ `analyze.py us` → `make_us_page.py` → `us_sync.py push`（用 GitHub OIDC 身分上傳到 KV，不存金鑰） |
| `weekly-adjust.yml` | 週日 05:00 | Yahoo 重新檢查除權息還原 |

GitHub 的高頻排程常被延遲或略過，所以盤中改成單一長工作循環。

## 3. 即時資料（`site/worker.js`）
- `/api/quote?s=`：台股、指數走證交所 MIS（失敗重試 3 次，再退回 Yahoo，Yahoo 台股慢約 20 分）；美股直接 Yahoo（即時）。
- `/api/mis?ex_ch=`：批次取證交所現價（盤中重算用）。
- `/api/tx`：台指期近月日盤＋夜盤，期交所 MIS；期交所常擋 Cloudflare（520），會自動改用 Yahoo 奇摩股市 `StockServices.stockList;symbols=WTX&,WTX00`（只有目前時段）。
- `/api/draw?m=TW|US&c=代號`：管理者畫的型態線；GET 公開（美股需登入），POST 只有管理者。
- `/admin/*`：管理者專區（美股），密碼 PBKDF2 存 KV `auth`，cookie `us_auth`（Path=/，HttpOnly）＋ `adm=1`（給前端判斷）。`/admin/settings` 可改密碼、看資料狀態。
- `/api/us-ingest`：美股資料上傳／下載（GitHub OIDC 或 `X-Ingest-Key`，後者是 Worker secret `US_INGEST_KEY`）。

## 4. KV（綁定名稱 US）
- `site/index.html`、`site/data.js`：美股頁面與總表。
- `site/sh/<0-255>.json`：美股個股 K 線分 256 包（免費方案每天寫入上限 1000 次）。分包規則：`h=(h*31+charCode)%1000003`，`h%256`。
- `state/hist_<0-7>.csv.gz`：美股歷史（約 550 根）；`state/groups_us.csv`（使用者原始 234 檔分類）、`state/groups_us_all.csv`（全市場含自動分類）。
- `draw/<TW|US>/<代號>`：畫線資料。`auth`、`meta`。

## 5. 型態規則（使用者確認過的）
五種型態：轉強、弱轉強、型態好、盤整、走弱（走弱再分回檔走弱／破底走弱）。
- 轉強：帶量 1.5 倍突破盤整上緣（3 日內）、站回 5/10 日線（之前 10 天至少 3 天在 10 日線下）、或 3 日內由低點反彈 ≥ 20%。優先於走弱。
- 弱轉強：符合轉強，但 5>10>20 日線且 10、20 日線向上還沒成立（多頭回檔後站回不算）。是獨立的第五種。
- 盤整區間：10–60 根；上下緣各碰 2 次以上；高低差依股性（近 60 日平均振幅 ≥3% 用 25%，否則 20%）；影線不超出 5%；收盤不能連 2 天在外；區間中途有連 3 日收盤站上前段最高（或跌破最低）就切開；太斜不算（趨勢線漲跌 > 框高度 6 成，或 ≥10% 且 R² ≥ 0.75）；帶量突破 3 日內收回＝假突破；連 3 日在下緣下＝失效（紫色顯示 20 日）；沒帶量走出＝「無量突破待追蹤」。
- 支撐線：前低（前後各 5 根最低）＋回測（3% 內或刺破但收盤站上，距上次觸及 ≥5 根）；至少回測 1 次且沒被收盤跌破；只顯示股價下方最近的一條。
- 雙重底／頂畫成完整 W／M，第二個底（頂）要已經反轉才算；兩底差 ≤4%、頸線高出 ≥8%（使用者在考慮放寬）。

## 6. 前端重點（`site/index.html`）
- 美股頁 `site/us/index.html` 由 `make_us_page.py` 從同一份產生（資產路徑加 `../`），以 `D.market==="US"` 切換行為。
- K 線圖功能：日週月 K、還原價、均線（預設展開）、布林、DMI、KD（鈍化）、MACD、自訂區間（輸入起止日期）、剪刀（自訂盤整框／放大）、區間框開關、形態、支撐、管理者畫線（粉紅色）。
- 台指期：全盤／日盤／夜盤（夜盤 K 棒算下一個交易日；夜盤漲跌和前一交易日日盤收盤比）。
- 手機：K 線視窗一屏顯示、選項在上方橫滑、長按看 K 棒資訊。

## 7. 待辦／使用者提過要做的
- 比例線（回檔 0.382/0.5/0.618）。
- 美股自動分類的「不確定」清單給使用者確認。
- 雙重底兩底差距是否放寬到 8%。
- 6174 安碁是否屬於資安。
- GitHub 舊紀錄（初版那筆）裡的美股清單：已改寫歷史，但 GitHub 可能還快取舊 commit，可請 GitHub 客服清除。
- 其他：新聞、財報、重訊（最初規劃，尚未開始）。
