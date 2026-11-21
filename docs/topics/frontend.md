# 主題：前端畫面（site/index.html）
上線前跑 ui_check；動頁首照 CLAUDE.md 量間距。配色、版本常數見 `docs/archive/archive_frontend.md`。

## 頁首與導覽
- 電腦 ≥901px、寬 1260px：`#ttl` 兩行（h1；資料日期 `#asof`＋🧰小工具 `#xl` 同列 `.arow`）、搜尋框撐滿、上班模式最右、設定 `#n-set`（美股頁／台股登入後）。
- ≥1200px 用 `#ttl{margin-bottom:-24px}` 讓指數列貼近搜尋框；900～1200px 不拉（會壓到標題）。手機導覽五顆一列 `html.nvA`、返回鈕 `#hbk`。
- 手機（≤640px）：小工具與「美股／設定／A－／A＋」同一排（`#ttl`／`.arow` 設 `display:contents`）。管理者有🔍全市場型態比對鈕 `#cmpb`（電腦在設定左、手機在資料日期那排右；天空藍毛玻璃）：POST `/api/recompare?m=TW|US` 叫 GitHub 重算（update.yml／us.yml；防連按台股 10 分、美股 30 分）。
- 🧰小工具：停利停損試算器、台股玄學預測（外部網址）；點外面／Esc 關閉。
- 返回：`navStack`、`goPrev()`、`navPos`／`restoreNav`；電腦 `#ttBack`、頂端／底部膠囊鈕 `TTV`／`TTA`。
- 坑：頁內重畫前設 `navBack=false`（否則 `restoreNav` 捲回去）；inline handler 要寫 `window.scrollTo`。
- 搜尋容錯 `fuzzyStocks()`；跨市場跳轉一次 `__bounced`；最近搜尋 5 筆（localStorage `sqh_T`／`sqh_U`）。

## 首頁
- 型態統計五卡 →「盤後一眼看懂」（收合 `mkcol`）→「強弱族群」（`swGroups()`／`swPanel()`／`grpcol`，點進族群 `data-swg`）。
- 五種型態統計鈕：各色透明漸層毛玻璃＋亮色大數字（`.sum .chip[data-st]`）；通道標記下降＝綠（`.tag.chn.chd`）、上升＝金褐，圖上通道線仍橘。
- 強弱族群：中位數算法、≥5 檔、成交值 <1 千萬不算、6 成上漲／下跌、重疊過半留高者；另有相對抗跌族群。盤中每 2 分重畫 `swLiveTick`→`home()`。
- 族群排序 `GSORTS`（存 `gsk`／`gsd`）＋自訂順序 `GSE`／`GSW`（存 `gso`，只存該裝置）：🤚拖拉、雙上三角＝`gsMove(name,-999)`、▲▼、雙下三角。

## 列表與篩選
- 漲跌欄 `chgCell`（漲跌停底色，`tick`／`limPx`）；排序 `sortList()`／`SORTK`／`SORTD`；表頭 `#sth`。
- 型態篩選 `FILTERS`、反轉小分類 `SUBF`（頂部只算 `dir==="bear"`）。綜合篩選：mops、revhi／yoyhi、m3up、nwup、本益比 6 顆、強勢、權值股 `wt`（`WTN` 50）。美股只有本週強勢、今日強勢、三率三升。
- 型態介紹 `#learn`（`learnPage()`）；聯絡／免責 `#about`。
- data.js：台股 `geo` 只留 kind/dir/status/day，座標在 `site/s/<代號>.json`（美股不變）。

## K 線視窗
- 還原價有除權息預設開 `ADJDEF`；形態同時最多 2 個；反彈% 標籤 `rbk`；通道鈕見 patterns.md；預設點最新一根。
- 支撐：前低＝最高點之前最近一個未被跌破的波段低點（`calcStats().swingU`）；近期＝最高點後最低點；舊 `findSupport` 不用。頸線紅漲綠跌 `neckJobs`。
- 上下一檔 `__navList`＋`location.replace`；標題下 `valBar`（PE>100 標「獲利低基期」）。
- 選股清單（頂端「2/N ▾」，`navList()`）：置中面板 `NVP` 3、搜尋、✕或點背景 `#nvbd` 關閉、欄位共用一組 grid、成交值／漲跌幅標題可排序、捲動條 `.nvt`、`NVG` 2；在消息頁切換仍留消息頁。

## 管理者畫線（粉紅 #ff5fd2；新 kind 要加進 worker 白名單）
- 平行線 kind=chan：畫一條自動帶第二條，可定位、加寬／縮小、翻面。杯柄 kind=cup：點 4 下（杯口左、杯底、杯口右、柄最低），杯身拋物線。
- 日K可點最後一根右邊空白；上一步／下一步（存檔、刪除各一步）。
- 線長度（日K；直線、平行線、水平線）：`extDraw` 左右端 ◀◀◀▶▶▶（5／1 根）沿斜率伸縮，按住連續動（「放開」要由 window 收：面板每動一次重畫）、放開 0.5 秒後存檔；`.dre`。

## 消息分頁：左財報右新聞（`site/f/<代號>.json`）；細節見 `docs/archive/archive_frontend.md`


## 專業機構多空比及市場情緒（`#funds`，`fundsPage()`，台美都有）
- CFTC 槓桿基金（標普 500／那斯達克 100／VIX 期貨）淨口數、多÷空、52 週百分位、3 年走勢；數值框 `.fro`；資料日 >10 天警示；公布美東週五 15:30＝台灣週六 04:30。
- 名稱依使用者 11/20 要求，避免寫「對沖基金」。NAAIM 不做（改付費）（待確認：主檔待辦仍寫要做）；待做個股空單比例（FINRA）。
- 市場情緒 `sentHTML()`：VIX、VIX÷VIX3M、CNN 恐懼貪婪（7 子指標）、SKEW，`.sgrid`、`sparkSvg`／`sentHover`。CNN 非官方：本雲端抓不到、Actions 抓得到；抓不到沿用舊檔，全無只顯示 VIX。
- 資料 `scripts/cftc_funds.py`→`data/funds.json`、`scripts/sentiment.py`→`data/sentiment.json`，各出 `site/`、`site/us/` 兩份（美股走 KV）；update.yml／us.yml／intraday_loop 都跑。
