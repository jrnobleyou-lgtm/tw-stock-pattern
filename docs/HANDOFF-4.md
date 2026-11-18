# 交接文件（續 4）

接在 `docs/HANDOFF-3.md` 後面。

## 2026-11-17（已上線＝✅）
- ✅ 新聞 AI：只用 Gemini flash-lite → flash（GitHub Models 已停用、移除；Groq、Cloudflare Workers AI 測過不夠好，金鑰仍存在 GitHub Secrets 備用）。提示詞補強（里程碑／多空並陳／法人只預估＝持平；訂單能見度延長算上修；外資點名無目標價＝點名；一次性收益＝持平；盤面一律持平）。`kind` 是盤面的一律不收。重測 40 篇：與 Haiku 顯示的上修／下修一致 31 篇，lite 偏保守（漏標多於誤標）。結論：先不買付費 Claude；用設定頁「每日新聞判斷統計」（`news-data/daily.json`，每天篇數、上修／持平／下修、各模型篇數、503／429、預估 Haiku 費用）累積幾天再決定。
- ✅ EPS 回補完成（`data/eps_fm.json` 1,987 檔）。B3 驗證：台積電 2025 四季單季加總＝全年 EPS；官方 2026Q3 累計對 FinMind 單季加總 1,595／1,865 吻合。**只改資料檔推 main 不會觸發 update.yml，要手動觸發**（現在路徑已補 `data/rev/**`、`data/eps_*.json`、`data/fin_meta.json`）。
- ✅ 前端：漲跌欄改「股價（上）＋漲跌幅（下）」，標題「股價／漲跌幅」兩行，漲跌停整塊紅／綠底（版本 2，`window.CPV`）；K 線反轉拆「K線反轉（轉好）」「K線反轉（轉壞）」（`cdlu`／`cdld`）；型態介紹頁：上班模式維持上班背景、目錄與放大圖右上角加 ✕、搜尋列／分類列／目錄／頁首改不透明；電腦寬螢幕頁首與內容對齊；綜合篩選頁（nwup／mops／revhi／yoyhi）；盤中背景分頁不重抓 data.js。
- ✅ **Fable 審查（11/17，最後一次用 Fable）**後修正：
  - V 形底第 4～10 天只加標籤、不改五種型態（比照島型，`engine.apply_patterns` 的 `late()`；全市場 11/16 改動 159 檔：弱轉強 621→474、走弱 1070→1181；固定檢查 `TestVLate`）。V 形頂未動。
  - 除權息日漲跌幅改用還原後參考價（`analyze.py` 的 `pc`、`chg`、`r5`）；新股（`s.new`）前 5 天不標漲跌停。
  - 排程：`news.yml` 加每小時 GitHub 備援排程；Worker 新聞觸發失敗記 KV `cron/newsfail`，設定頁標紅；看門狗改成「最後一次建置比最新 deploy 舊超過 4 分鐘」才補部署；`intraday_loop.sh` 休市判斷改成連續 10 輪抓不到今日資料且過 09:20 就結束；`update.yml` 發布前跑固定檢查（失敗不發布）；`weekly-adjust.yml` 推送失敗重試。
  - Worker：刪除 `/api/misraw`；`/api/us-ingest` GET 只能讀 `site/`、`state/`、`meta`；`/api/draw-list`（公開）加 90 秒快取。
- 美股 11/17 14:25 手動跑 us.yml 成功（今天的前端改動已帶上）。**美股新聞／月營收／EPS／重訊使用者說可能不做了。**
- Fable 其他建議尚未做（使用者沒指定）：島型第 4～10 天形態打架降級、停牌股標資料日期、登入防連續猜密碼（建議 14 字以上隨機密碼）、分析時抓不到新聞／重訊／畫線沿用上次結果、三大法人與期貨盤中不重抓、固定檢查再補（4609、6146、2406、1201、7848、除息日、假突破、雙重頂等案例；上線前「所有篩選頁各點一次」寫成固定 Playwright 腳本）、`data.js` 瘦身。
- 待辦：重訊觀察 2～3 天（`meta.mops.check`）決定按鈕名稱；季營收（使用者說月營收做好再想）；GitHub 金鑰（Worker secret `GH_TOKEN`）到期日待使用者告知。
- ✅ GitHub 金鑰（Worker secret `GH_TOKEN`，fine-grained token）使用者確認**永不到期**。
- ✅ 頁首改版（使用者選版本 3）：搜尋框在「上班模式」右邊撐滿、三個指數卡片置中、導覽列置中、「設定」鈕在最右邊（美股頁一定有、台股登入後〔cookie `adm=1`〕也有，`#n-set`）；只改電腦版（≥901px，用 `header .hr{display:contents}`），手機版導覽置中、設定接在後面。
- ✅ 新聞判斷優先順序（11/17 使用者）：全部文章都判，但排隊先判「關注清單＋成交值前 100 名」（`news.py` 的 `priority_codes()`／`is_priority()`；關注清單檔 `data/watchlist_tw.txt`，來源是 Google 試算表「Claude_網站分類_台股」的分頁「關注股票_台股」，另有空的「關注股票_美股」；成交值前 100 名讀線上 data.js）。每日統計表多「優先名單／其他」兩欄。**關注清單目前 176 檔（使用者截圖群組二～五逐檔抄的，期貨與大盤不要，已補齊；群組二第 21 檔「長榮」我加了長榮航 2618，請使用者確認）。清單改了要同步到 `data/watchlist_tw.txt`（要請我讀試算表，或把一行加進使用者每日族群同步排程）。**
- ✅ 台股試算表分頁「工作表1」已改名「族群分類」（使用者 11/17 指定）；美股試算表的「工作表1」尚未改。使用者自建的每週／每日族群同步排程指令若寫「工作表1」要改成「族群分類」，否則同步會找不到分頁。
- ✅ 美股關注清單（使用者 11/17 逐批截圖，ETF／槓桿 ETF／非美股略過，ADR 保留）：129 檔已寫進試算表「Claude_網站分類_台股」的分頁「關注股票_美股」。**不進版控**（和美股族群清單同理，公開 GitHub 不能放）；美股新聞還沒做，之後做時再存 KV。與美股股票池（KV `state/groups_us_all.csv`，4,086 檔）比對：找不到的 7 檔＝ANT（Anthropic 未上市）、OTC 的 ADR（FUWAY、TTDKY、SHECY、SUOPY、IFNNY、RNECY；股票池只含 NASDAQ 篩選器的 NYSE／NASDAQ／AMEX）。
- ✅ 美股股票池加 6 檔 OTC ADR（FUWAY 古河→光通訊/CPO、TTDKY TDK→電子零組件、SHECY 信越→矽晶圓、SUOPY 勝高→矽晶圓、IFNNY 英飛凌→功率半導體、RNECY 瑞薩→IC設計）：已寫進美股試算表（工作表1 第 603～608 列）與 KV `state/groups_us*.csv`，美股更新（台灣 11/17 20:08）已抓到價格，股票數 4,089。ANT（Anthropic）預計 11/21（週五）上市，上市當天使用者會通知。
- ✅ 台股試算表分頁「工作表1」→「族群分類」；**排程 `trig_01C1hrzzY2io3gRmGr7zX3ce`（每週六 15:15 同步台美股族群，從網頁建，只有使用者能編輯，網址 claude.ai/code/routines/<id>）指令仍寫「工作表1」，下週六 11/21 台股會讀不到，要使用者改**（台股改「族群分類」；美股先試「族群分類」，讀不到用「工作表1」）。另一條「code網站分類試算表同步」（週六 14:50，使用者隔壁線）11/17 18:11 已更新過。可同時加一步 2b：讀「關注股票_台股!A2:B500」寫 `data/watchlist_tw.txt`（使用者尚未回覆是否要）。
- 待辦：11/19 08:30 自動對照新聞統計（`trig_01EKR7bV9p6M9bjwKG983fWh`）；Haiku 速率限制已確認（Console 評估等級：Haiku 5.5 每分鐘輸入 50 萬／輸出 8 萬／請求 1,000，夠用；API 要先儲值才能呼叫，尚未決定）。

## 2026-11-17 晚：季營收、三率、🌟歷史新高（程式已寫好，資料回補中，未推 main）
- 使用者規格（grilling 全照建議＋）：消息分頁左欄「季營收與三率（近 3 季）」表：營收（三個月月營收加總）、季增%、年增%、毛利率／營益率／淨利率（單季）＋比上一季增減個百分點；標籤與綜合篩選鈕「三率三升」（`m3up`，三率都比上一季高）；**當月營收創歷史新高**（月營收長條最新月）與**當季營收創歷史新高**（季表最新一季）各打 🌟，只看最新月／最新一季。
- 程式：`scripts/margins.py`（`update` 官方最新季累計→`data/margin_cum.json`；`backfill` FinMind 單季→`data/margin_fm.json`，單位千元；`single()`、`summary()`），`revenue.summary()` 加 `mAth`，`analyze.py` 把 `q` 寫進 `site/f/<代號>.json`、加「三率三升」標籤；`update.yml`／`intraday_loop.sh` 已加 margin 檔；固定檢查 `scripts/tests/test_margins.py`。
- **回補**：本容器背景程式 `MARGIN_FM=<scratchpad>/margin_fm.json python3 scripts/margins.py backfill`，每檔 8 秒約 4.5 小時（台灣 11/17 約 21:00 開始）；可續跑（已有的略過）。補完後把 `margin_fm.json` 複製成 `data/margin_fm.json` 並提交（連同 `data/margin_cum.json`），再手動觸發 update.yml，檢查消息分頁與「三率三升」篩選頁（所有篩選鈕各點一次）。**盤中（08:50–13:50）不要推 main。**
- 金融業沒有毛利率（官方只抓一般業 `_ci`），三率顯示「—」。

## 2026-11-17 深夜：Fable 其餘建議（使用者：除了登入防猜密碼，其他都做）
- ✅ 新聞、重訊、畫線抓不到時沿用上次結果：`analyze.py` 的 `cached()`，成功時存 `site/cache/<名稱>.json`（gitignore，隨網站發布），失敗從線上網站 `/cache/` 讀上次那份。
- ✅ 停牌股：資料日比該市場最新日舊的股票標 `stale`（資料日 MM-DD）＋標籤「停牌（資料至MM-DD）」，漲跌欄顯示灰色「停牌 MM-DD」、漲跌幅當 0。
- ✅ 島型第 4～10 天形態打架時降級（`patterns.resolve_conflicts` 的 `rk()` 給 2.5，同 V 形底超過 6 天）；全市場五種型態前後不變。
- ✅ 盤中（週一～五 15:00 前且有盤中資料）不重抓三大法人與外資台指期淨部位（只有收盤後才公布）：沿用 `site/cache/inst.json`、`fut.json`；抓不到仍不放舊數字。
- ✅ 固定檢查：`scripts/tests/test_pipeline.py`（整條流程 13 個案例＋凍結 6146 轉強／4609 走弱）、`test_margins.py`；`scripts/ui_check.js`＝所有篩選鈕（台股／綜合、含子分類）、族群頁在電腦與手機各點一次，有 pageerror 就失敗（上線前跑：先 `python3 scripts/analyze.py all`，再 `NODE_PATH=$(npm root -g) node scripts/ui_check.js`）。
- ⏸ `data.js` 瘦身：1.5MB（gzip 後只有 275KB），最大是各股 `geo`（386KB）；效益小，先不動。
- ❌ 登入防連續猜密碼：使用者決定不做。
- ✅ 每天台灣 07:47 的新排程 `trig_01Uhcg4uxGQoczg7zAGxg21B`（新對話，只讀）：算前一天新聞判斷量，含優先名單（關注清單＋成交值前 100）占比、各來源篇數、預估 Haiku 費用，推播給使用者。

## 2026-11-17 深夜：data.js 瘦身上線、Google 模型自動換新
- ✅ `data.js` 瘦身（Opus 設計）：台股 `st["geo"]` 只留 kind/dir/status/day，畫圖座標（pts/lines/rect/neck/stop…）搬到 `site/s/<代號>.json` 的 `geo`；前端 `openStock` 載入後 `s.geo=j.geo`，`gm.pts||[]` 防呆。美股（`us` 模式）不變。線上 data.js 1.5MB→1.19MB（gzip 0.27→0.20MB），電腦／手機各開 3 檔形態股驗證 OK。
- ✅ 新聞 AI 型號自動挑（Opus 設計，`scripts/news.py`）：每輪 `list_models()` 取 Google 型號清單，`pick_models()` 挑最新正式版 flash-lite → flash（正規式只收 `gemini-<版本>-flash(-lite)`，排除 preview／exp／pro／omni 等；版本低於預設 3.5 不用；挑不到退回寫死預設）。新型號第一次用前跑 `self_check()`（8 篇編造樣本：3 上修／2 持平／3 下修，格式對、≥7 篇回、≥6 對、不可上下修顛倒）；沒過且還有舊型號就先不用。型號 404／免費額度 0 → `Gone` 直接換下一個。紀錄：`meta.json` 的 `models`／`model_ok`／`ai_ok_t`，`daily.json` 當天的 `models`／`gone`／`alert`／`allfail`。全部型號被停用 → 寫 `news_fatal.flag`，`news.yml` 最後一步讓工作失敗（GitHub 寄 email）。設定頁新聞列顯示 AI 型號、最後成功時間（06–23 點超過 3 小時標紅）、alert 紅字。固定檢查 `scripts/tests/test_news_models.py`；測試用環境變數 `NEWS_FORCE_MODELS`。
- 實測 11/17 晚：Google 清單已有 `gemini-3.8-flash`（比 3.5-flash 新），會在後備位被自我檢查後採用（當時 503 忙碌，未通過，下輪再試）。日報提示詞建議加一句「若 daily.json 今天有 alert，第一行照抄」（只有使用者能在 claude.ai 改排程，使用者尚未改；要提醒一次即可）。
- ✅ 各 AI 型號工作狀況 KPI（使用者 11/17 要長期追蹤）：`news.py` 的 `API`／`ev()` 記每型號呼叫 calls、成功 ok、忙碌 busy、額度 quota、格式錯 bad、不存在 gone、耗時 secs，每輪合併進 `daily.json` 當天的 `api`；設定頁「每日新聞判斷統計」下方多「各 AI 型號工作狀況」表；日報排程（`trig_01Uhcg4uxGQoczg7zAGxg21B`，我建的所以我能改）第 0 步先報警告、4b 列 KPI 表並跟前 7 天比。`api` 欄位從有新文章被判斷的下一輪才開始出現（11/17 22:40 空跑沒新文章，尚未見到線上資料；11/18 起確認）。3.8-flash 排在 flash-lite 之後、3.5-flash 之前（自我檢查連不上時照樣試用，失敗退回）。
- 使用者 11/17 決定：登入防猜密碼**不做，不用再提**；**美股新聞、美股月營收不做**（美股沒有月營收、資料難抓；美股關注清單 129 檔仍留在試算表「關注股票_美股」，不進版控）；「長榮」＝長榮航 2618 確認 OK。
- 「關注股票_台股」納入每週同步：11/17 已用本對話讀過，試算表 176 檔與 `data/watchlist_tw.txt` 完全一致（不用改）。每週自動同步要使用者在 claude.ai 的每週排程（trig_01C1hrzzY2io3gRmGr7zX3ce，只有使用者能編輯）加一步 2b：讀台股試算表「關注股票_台股!A2:B500」，用「代號,名稱」逐行覆寫 `data/watchlist_tw.txt`（保留第一行 # 註解）、有差異才提交推 main。
- ✅ 11/17 使用者同意上線：頁首「上班模式」移到第一列最右邊（電腦版，搜尋框右邊）；搜尋容錯 `fuzzyStocks()`（多打／少打／代號差一碼都找得到相近的，標「找不到完全符合…改顯示相近的」）。
- ✅ 每週同步排程的步驟搬成專案 skill `.claude/skills/weekly-sync/SKILL.md`（含 2b 關注清單同步）：以後改步驟改這個檔即可。排程 `trig_01C1hrzzY2io3gRmGr7zX3ce` 是早期對話用 http_api 建的，我（agent）不能改，使用者要自己把「指示」換成短版：`每週六族群同步。照專案 tw-stock-pattern 裡 .claude/skills/weekly-sync/SKILL.md 的步驟執行（沒有專案就先 git clone https://github.com/jrnobleyou-lgtm/tw-stock-pattern；用 Skill 工具叫 weekly-sync，找不到就直接讀該檔）。全程繁體中文。`
- ✅ 11/17 深夜 關注清單搬出公開 GitHub（使用者：傾向搬；repo 公開，歷史紀錄裡仍有舊版 `data/watchlist_tw.txt`，清歷史要使用者自己做，我的環境擋強制推送）：現在存在 Cloudflare KV `state/watchlist_tw`（每行「代號,名稱」）；寫入＝`scripts/apply_watchlist.py <試算表json>`（Cloudflare API，少於 20 檔拒寫）；讀取＝`news.py priority_codes()` 用 `us_sync.get()`（GitHub OIDC，`news.yml` 已加 `id-token: write`，Worker `/api/us-ingest` 只認 main 分支的工作）。`data/watchlist_tw.txt` 已從專案移除並加進 .gitignore；每週同步 skill 的 2b 改成呼叫 apply_watchlist.py。讀不到時只剩成交值前 100 名當優先名單（不會中斷）。
- 使用者 11/17 問「盤中報價抓 Yahoo 被發現？」：程式與資料來源在公開專案裡本來就看得到；台股盤中主來源是證交所 MIS（官方），Yahoo 只是備援（MIS 失敗）與台指期備援、美股盤中報價。
- ✅ 11/18 凌晨 使用者定案：頁首標題做成框（版本 2＋3：㊙️ 圖示〔使用者指定〕、紫色發光框；不在首頁時框內多「↩ 回首頁」小標，小標左邊不留空白；`#home-link` 的 CSS，`html.sub` 非首頁時才有小標），美股頁共用。
- ✅ 網站不再公開寫資料來源：`worker.js` 的 /api/quote、/api/tx 回傳拿掉 `src` 欄位（前端改用 `q.delay>0` 顯示「延遲約20分」）；頁尾與美股頁首改「資料來自公開市場資訊」；程式註解與重訊說明的來源名稱拿掉（新聞媒體名稱保留，作為連結文章的出處）。GitHub 公開 repo 內的程式碼與歷史紀錄不動（使用者決定：要藏 GitHub 上的來源得換 repo，成本高，暫不做）。
- 使用者 11/18 決定 ETF 專區（尚未開工，已 grilling）：只做台股 ETF；要有主動式／被動式區分、成分股（連到外部網站，不自己做）、折溢價與規模（評估中，較難：需要即時淨值；證交所 mis all_etf 在本環境被擋，要試 Actions/Worker）；ETF 不做型態判斷；放導覽列獨立「ETF專區」。另問台股是否顯示平均目標價／PE：PE（本益比）／PB／殖利率可用證交所 BWIBBU_d＋櫃買同類開放資料，平均目標價沒有可靠免費來源。

## 2026-11-18 凌晨：待辦與排程（壓縮前最終狀態）
- **凌晨 01:00 自動開工**（`trig_01QaNkXDqfrQAnLACT6sowWf`，send_later 叫醒本對話）：依序做 ①PE／PB／殖利率 ②目標價參考清單 ③ETF 專區第一版；成分股連結、折溢價、規模使用者說明天再說（先略過）。提醒內文已寫好完整規格（Opus 顧問 11/17 的設計）。外觀改動（PE 顯示樣式）先做好放著、早上截圖給使用者確認再上線；資料與固定檢查可先做；盤中 08:50–13:50 不推 main。
- Opus 顧問結論重點：
  - PE：上市 `twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json&date=YYYYMMDD&selectType=ALL`（當天收盤後就有，含收盤價、股利年度、財報年季）、`openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL`（慢一天）；上櫃 `tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis`（虧損寫 N/A）。自算 PE（收盤價÷近四季單季 EPS）對台積電 22.08 vs 官方 22.09。盤中不讓 PE 跳，固定收盤值標日期；虧損顯示「虧損」；極端 PE 標「獲利低基期」。
  - 目標價：無免費正式來源；做「近 60 天法人目標價」參考清單（鉅亨 FactSet 速報＋新聞法人類 AI 抽取，程式驗證 0.3～3 倍現價、原文含該數字，只存數字／券商／日期／標題／連結），≥3 家才顯示最高最低中位數，<2 家只列清單，標上調下調，存 news-data `targets.json`；錯誤率 >10% 不上線。
  - ETF：不要放進 `groups_tw_all.csv`／`D.stocks`（1,980 檔數字前後必須一致）；清單用 `openapi.twse.com.tw/v1/opendata/t187ap47_L`（基金類型含主動式、槓桿反向；發行單位數×收盤價＝約略規模）＋ 上櫃行情（`tpex_mainboard_daily_close_quotes` 118 檔 ETF）；尾碼 A 主動股票、D 主動債券、B 被動債券、T 平衡、L 槓桿、R 反向，名稱「主動」開頭；舊代號無尾碼要看官方類型；市值型／高股息／主題用名稱關鍵字＋`data/etf_class.csv`；歷史另存 `data/hist_etf/`；`site/etf.json`＋`site/s/<代號>.json`；`openStock()` 要能讀 etf.json；`intraday` 要加 ETF 代號；固定檢查加 ETF 案例；驗證：1,980 檔 total／groups／五種型態前後一致、抽查 0050／00878／00981A／00679B／00631L。第二版再測 Cloudflare 能不能抓 mis `all_etf.txt`（折溢價）。成分股連結：Yahoo `https://tw.stock.yahoo.com/quote/{代號}.TW/holding`（上櫃 `.TWO`）、MoneyDJ `https://www.moneydj.com/ETF/X/Basic/Basic0007.xdjhtm?etfid={代號}.TW`（上櫃也用 `.TW`）。
- **三率回補**（背景 byhj0sule，`MARGIN_FM=<scratchpad>/margin_fm.json python3 scripts/margins.py backfill`，剩約 1,811 檔，預計 11/18 03:00 前後完成；程式被環境收掉就重跑，可續跑）；檢查提醒 `trig_01YDGL5r8Cuqw9objv8GA9sT` 台灣 03:30：完成就複製成 `data/margin_fm.json` 提交推 main（13:50 後或 08:50 前）、手動觸發 update.yml、驗證消息分頁／「三率三升」／所有篩選鈕（`scripts/ui_check.js`）。
- **每天 07:47 日報**（`trig_01Uhcg4uxGQoczg7zAGxg21B`）：第一行報新聞 AI 警告，並含各型號工作狀況 KPI（`daily.json` 的 `api`，從 11/18 起有資料）；3.8-flash 在後備位試用。11/19 08:30 對照新聞統計（`trig_01EKR7bV9p6M9bjwKG983fWh`）。
- 使用者已把每週同步排程（`trig_01C1hrzzY2io3gRmGr7zX3ce`）指示換成短版（讀 `.claude/skills/weekly-sync/SKILL.md`）；關注清單存 Cloudflare KV `state/watchlist_tw`，由 `scripts/apply_watchlist.py` 寫入、`news.py` 讀取（已驗證優先名單 198 檔）。
- 開放問題：使用者還沒決定「標題框」以外的事：無。待決定：美股 EPS／三率與其他美股功能（Opus 建議先做 52 週新高低／相對強度／財報日與財報後跳空，EPS／三率走 SEC EDGAR 排第 3）；台股「平均目標價」排在 PE、ETF 之後。ANT（Anthropic）預計 11/21 上市，使用者上市當天通知。Haiku API 付費決定等 11/19 比較。🌟 目前在消息分頁（月營收長條與季表），若要放 K 線圖使用者再說。
- 使用者規則（再次確認）：待確認的事只講一次；回報 ✅／❓、台灣時間、繁體中文；外觀改動先給截圖；登入防猜密碼不做、美股新聞不做、美股月營收不做。

## 2026-11-18 凌晨 01:00～01:30：PE／目標價／ETF 已做好（前端畫面都還沒上線，等使用者早上看截圖）
- 分支狀態：**後端（scripts）已推 main**：`scripts/valuation.py`（PE／PB／殖利率）、`scripts/targets.py`＋`news.py`（目標價累積）、`analyze.py`、`eps.py`（summary n 參數）、測試 `test_targets.py`。**前端 `site/index.html`、ETF 相關（`scripts/etf.py`、`update.yml` ETF 步驟、`intraday_loop.sh`、`ui_check.js`、`data/etf_class.csv`）只在開發分支 `claude/zealous-johnson-tpqrow`**，使用者看過截圖說好才進 main。
- **PE／PB／殖利率**：官方收盤後資料（上市 `www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d`、上櫃 `tpex_mainboard_peratio_analysis`，上櫃日期要跟上市同一天才收），`analyze.py` 寫進每檔 `pe/pb/dy/pq/pl`（`pl`＝官方沒給 PE 且近四季單季 EPS 合計 ≤0）與 `data.js` 的 `valDate`；抓不到沿用線上 `/cache/val.json`。前端：K 線視窗標題下一行「本益比 22.1（近四季，115Q3）｜股價淨值比｜殖利率｜11/17 收盤值」（`valBar`）；綜合篩選新增 6 顆：本益比 ≤15／15～25／≥25、殖利率 ≥5%、PB ≤1、近四季虧損（表格多 PE／PB／殖利率三欄，排序可選）。PE>100 標「獲利低基期」。本機 1,980 檔有資料、435 檔近四季虧損。
- **目標價**：不用 AI。`targets.py`：①鉅亨速報「Factset 最新調查：○○(代號-TW)…預估目標價為X元」（多位分析師中位數）②新聞句子裡「具名券商（美銀／高盛／大摩…）＋同一檔股票＋目標價 X 元」，「外資」未具名不收。`news.py` 每輪把候選存進 news-data 分支 `targets.json`（首次用 items 標題補回 30 天）；`analyze.py` 讀它，用現價驗證 0.3～3 倍、近 60 天、同家只留最新、標上調／下調，≥3 家券商才算最高／中位數／最低（不算平均），寫進 `site/f/<代號>.json` 的 `tp`；消息分頁左欄「近 60 天法人目標價」表。固定檢查 `test_targets.py`。實際線上要等 news.yml 跑過幾輪才有資料；目前本機用 items 標題測試 22 筆。
- **ETF 專區第一版**：`scripts/etf.py`（`daily` 收盤後把代號 00 開頭的上市櫃 ETF 日 K 加進 `data/hist_etf/YYYY-MM.csv` 並更新 `data/etf_class.csv`；`backfill N` 逐檔逐月補歷史〔證交所 STOCK_DAY／櫃買 tradingStock，1.7 秒一筆，可續跑，快取 `ETF_CACHE`〕；`build` 產生 `site/etf.json` 與 `site/s/<代號>.json`，日期用字串）。分類：主動（名稱「主動」開頭或「平衡」）／被動；分類規則 `CAT`（槓桿 L、反向 R、期貨／商品 U K C、債券 B D、高股息、海外、市值型、主題、台股（一般）、其他），手動覆寫放 `data/etf_override.csv`（代號,主被動,分類）。ETF 不進 `data.js`／族群（1,980 檔統計不變）。前端：導覽「ETF專區」（美股頁隱藏）、`#etf`、`#etf-active`、`#etf-all.高股息` 等；清單可依主動／被動與分類篩選、槓桿／反向預設不顯示；點進去 `#e-<代號>` 開現有 K 線視窗（無型態、價格未還原配息）。`update.yml` 加 ETF 步驟（`continue-on-error`）與提交 `data/hist_etf`；`intraday_loop.sh` 每輪也跑 `etf.py build`（否則盤中發布會把 ETF 檔洗掉）。`ui_check.js` 加 ETF 頁，144 畫面 0 錯誤。
- **ETF 歷史回補**在背景（`ETF_CACHE=<scratchpad>/etfc python3 scripts/etf.py backfill 7`，台灣 01:10 起；證交所偶爾連不上很慢）。補完後：`python3 scripts/etf.py build` → 提交 `data/hist_etf`、`data/etf_class.csv` → 把 ETF 相關程式（含 workflow／intraday_loop）推 main（先別推 index.html，等使用者看過）。被環境收掉就重跑同指令（會續跑）。
- 待使用者看截圖後上線：PE 顯示（K 線標題列＋綜合篩選 6 顆）、目標價表、ETF 專區（清單頁＋K 線）；ETF 分類請使用者看 `data/etf_class.csv`（「其他」只剩 00981T）。成分股連結、折溢價、規模使用者說明天再說。
- 三率回補：第一輪 2 小時被環境停掉（只補到 363 檔，卡在 FinMind 整點額度），01:10 重新啟動（背景 `b40oi08zn`，`MARGIN_FM=<scratchpad>/margin_fm.json`）；03:30 檢查提醒仍在。

## 2026-11-18 白天（壓縮前最終狀態；已上線＝✅）
- ✅ 11/18 08:25 三率回補完成（1,977 檔）上線；「三率三升」574 檔。
- ✅ 本益比／股價淨值比／殖利率（K 線標題下一行＋綜合篩選 6 顆）、ETF 專區（導覽「ETF專區」、`#etf`、主動／被動＋分類、槓桿反向預設隱藏、`#e-<代號>` K 線）上線。ETF 歷史用 Yahoo 補近 1 年（`etf.py yahoo`，未還原配息）；每天由 `update.yml` 的 ETF 步驟更新、`intraday_loop.sh` 每輪 `etf.py build`。
- ✅ **目標價（使用者 11/18）：只有登入後看得到**。`news.py` 把 `targets.py` 整理的資料存 Cloudflare KV `state/targets_tw.json`（沒新資料不寫，省額度），Worker `/api/targets?c=&close=` 驗證登入（cookie `us_auth`）才回；前端消息分頁只有 `adm=1` 才抓。公開的 `f/<代號>.json` 沒有目標價；`analyze.py` 的 `SHOW_TARGETS=1` 才會寫進（預設關）。鉅亨「Factset 最新調查」速報標題本來就在公開新聞列表裡，使用者決定不拿掉（視為新聞標題＋連結）。
- ✅ 11/18 13:55 上線：華航 2610、長榮航 2618 改「航空/運輸」（台股試算表第 197、198 列＋異動紀錄；美股 UAL、CSX 是隔壁線改的，已用 API 寫進 KV `state/groups_us*.csv`，美股頁今晚 20:08 更新生效）；「聯絡我們／免責聲明」（頁尾連結 `#about`，正式語氣，信箱 swingbreakout888@gmail.com 用程式組字）；型態介紹頁電腦版圖放大＋「本站怎麼標、什麼時候失敗」收摺（`window.LZV` 2）；手機導覽五顆同一列（`html.nvA`）；手機股票列表版本 3（`MCV` 3：拿掉重複的成交值／收盤欄，標記放在每檔下面整排，名稱＋成交值、股價＋漲跌幅各用框框〔`MBX` 2、底色 `MBC` 4 較透明純黑〕、標記文字粗體淺灰 #cdd3e6、名稱成交值粗體、股價漲跌幅放大）；手機「底部」鈕放標題列右邊空白（`mc3`）。使用者決定：版本 1 細框線先 hold（`MBX=1` 可切）。
- ⏳ **外部連結（未上線，待使用者說好）**：頁首「上班模式」旁一顆淡紫框按鈕「🔗 母子單計算器 ↗」（`#xl`，連到 `https://timber-quiet-heart-sapphire.grok.me/`，使用者請 Grok 做的「台股波段母子單計算器」，新分頁開啟 `rel=noopener`；`window.XLV` 2 可改首頁橫幅）。環境網路已加這個網址（`update_environment`），名稱「母子單計算器」是我依內容暫取，使用者可改。
- 待辦／提醒：①09:00 前後日報 07:47 已跑；11/19 08:30 新聞統計對照（`trig_01EKR7bV9p6M9bjwKG983fWh`）；Haiku 付費不買（使用者同意免費 3.5 夠用）。②ETF 成分股連結、折溢價、規模使用者說之後再說。③美股 EPS／三率等待使用者決定；ANT 11/21 上市使用者會通知。④盤中 08:50–13:50 不推 main（使用者：保守規則，除非使用者明說現在推）。⑤目標價資料要新聞排程跑幾輪才有內容，登入後在消息分頁看。

## 2026-11-18 晚：新聞網站改版／抓不到的注意事項（使用者要求寫進交接）
- **事件**：優分析（uanalyze.com.tw）11/18 改版，文章連結由完整網址變成相對路徑 `/articles/<數字>`，`news.py` 的 `src_uanalyze` 只認完整網址，連續 26 輪抓到 0 篇（設定頁「新聞來源」紅字「連續 N 輪沒抓到」就是這個警訊）。網站本身沒有擋我們（直接 curl 回 200）。已修：同時認完整網址與相對路徑，標題取連結內最長一段文字（去掉分類字）。
- **判斷是「被擋」還是「改版」**：先在容器裡 `curl -s -m 20 -A "Mozilla/5.0" <網址>` 看狀態碼與大小；200 且有內容＝多半是改版（抽取規則失效）；403／429／空白＝被擋。再看原始碼裡連結長什麼樣（`grep -o 'href="[^"]*articles[^"]*"'`）。
- **要特別注意的改版類型**：①連結由絕對網址變相對路徑（或相反）②標題外多包分類、日期、圖片文字，抓到的是一長串雜訊 ③列表改成前端動態載入（原始碼裡沒有文章）④RSS／API 欄位改名 ⑤免費文改付費牆。
- **寫抽取程式的原則**：連結一律先正規化成完整網址再去重；標題取最長文字片段並要求長度（例如 ≥8 字）；每家來源獨立 try/except，一家壞不影響其他家；對每家來源寫一個「抓得到 ≥N 篇」的檢查。
- **監控**：設定頁「新聞來源（最後一輪）」每家來源篇數，連續 ≥3 輪 0 篇標紅；`news.yml` 工作失敗會寄 email。每日 07:47 日報也要順手看各來源篇數有沒有掉到 0，掉到 0 就要查是改版還是被擋。
- 鉅亨「Factset 速報」主動抓取（`news.py` 的 `factset_rows`）同樣靠搜尋 API／標題格式，標題格式一變就會抓到 0 筆；目標價資料變少時先查這個。

## 2026-11-18 晚（壓縮前最終狀態；以下都已上線＝✅，除非標示）
- **規則更新**：同一問題試兩次找不到 → 要問 Opus，**但問之前先問使用者同意**（已寫進 CLAUDE.md）。難題、背景程式要等很久時，先告訴使用者「在做什麼、大約多久」，不要埋頭做很久（使用者 11/18 抱怨）。
- ✅ 頁首外部連結「🔗 停利停損試算器 ↗」（使用者命名，連 Grok 做的頁面）上線；電腦版頁首加寬到 1260px 讓它和「上班模式」同一排。
- ✅ 修：K 線視窗標題列被 PE 那行擠壞（`.mhead .pevr{flex:0 0 100%;order:4}`）；標題的族群可點進族群頁（`.glk`＋`data-swg`，返回會回線圖）。
- ✅ **本週強勢／今日強勢**（`analyze.py strong_flags`，Opus 定案）：本週＝近 5 日漲 ≥10% 且贏全市場中位數 5 點、週量比（5 日均量÷前 20 日）≥1.5、5 日均成交值 ≥5000 萬；今日＝漲 ≥5% 且贏大盤今日中位數 3 點、**不設量能條件**（使用者：等量出來太晚）、漲停放行；盤中 09:30 前不標、標過漲幅 ≥3% 保留（`site/cache/tdprev.json`）。新股、停牌不標。欄位 `w5／vr／vd／a20`；站上 20 日線改成頁內可勾選（`window.A20F`）。綜合篩選鈕「本週強勢股／今日強勢股」＋表格三欄（5日漲幅、週量比、日量比）；標記與按鈕用火焰版本 2（毛玻璃，`window.FLV`）。五種型態與總檔數不變。
- ✅ 排序選單加「族群」，旁邊「⇅ 由大到小／由小到大」鈕（`SORTD`）；排序／勾選後不捲回頂端。**根因**：`restoreNav` 在 `navBack` 為真時 0/120/400ms 後把畫面捲回 `navPos`；頁內重畫前要 `navBack=false`；inline handler 裡 `scrollTo/scrollY` 會被元素自己的方法吃掉，要寫 `window.`。
- ✅ 消息頁字體 A－／A＋（最多放大三次，`localStorage nz`，CSS zoom）；消息頁 EPS 區塊：右邊「115累計 Q1～3／114同期」小方塊＋「114年全年 EPS」＋超越標記（`eps.ytd()`→`fin["ey"]`）；新聞下方小字改「✨ AI新聞摘要：」天藍毛玻璃框（`.aisum`，`window.AIV` 2，寬度貼合文字）；全站淡灰小字改柔白（`--mute:#e5e7eb`，`window.MTV` 2）；標記框線柔白。
- ✅ **法人目標價主動抓 FactSet**（`news.py factset_rows`：鉅亨搜尋 API 找 `(代號-TW)` 速報→讀文章頁完整標題；每 2 小時掃一次，只存標題數字，登入後才看得到）。事欣科 4916 在關注清單但新聞沒有它的目標價（FactSet 沒涵蓋）；一週後統計每天新增檔數再回報。
- ✅ **優分析抓不到（連續 26 輪 0 篇）**＝改版後連結變相對路徑 `/articles/<數字>`，已修（`src_uanalyze`）；新聞網站改版注意事項已寫在上一節。
- ✅ **美股季財報（SEC）**：`scripts/us_fin.py`（名稱「stock research」＋網站公開專用信箱當 User-Agent；環境已加 data.sec.gov、www.sec.gov）每日在 `us.yml` 抓（約 9 分鐘，失敗 >10% 不更新），寫 `site/us/fn/<0-31>.json`（KV `site/fn/<k>.json`，Worker `/admin/f/<代號>.json` 切出單檔），`analyze.py us` 加「三率三升」標籤與 `fn:1`，K 線視窗「消息」分頁左欄（EPS、季營收、三率；季別為日曆季）。11/18 23:10 實跑成功：2,871／4,089 檔有資料（銀行、ADR、新股沒有）。**使用者登入管理者專區後的實際畫面我還沒親眼看過**（用模擬資料測過）。11/18 當天 KV 已寫約 315＋其他次，今天不要再手動跑美股更新。
- 待辦：①一週後回報目標價每天新增檔數、事欣科有沒有進來 ②11/19 08:30 新聞統計對照（`trig_01EKR7bV9p6M9bjwKG983fWh`）③美股頁畫面使用者確認 ④ETF 成分股連結／折溢價／規模（使用者說之後再說）⑤ANT 11/21 上市使用者會通知 ⑥盤中 08:50–13:50 不推 main。
