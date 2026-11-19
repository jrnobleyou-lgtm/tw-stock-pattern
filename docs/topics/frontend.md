# 主題：前端畫面（site/index.html）

首頁、K 線視窗、消息分頁、各種開關名。上線前跑 ui_check（見主檔）。

- 版面規則：改到原有東西的位置／順序前先講並等同意。外觀改動一律先截圖給使用者挑。
- 頁首（電腦 ≥901px）：標題框（㊙️、紫色發光、非首頁有「↩ 回首頁」）、搜尋框撐滿、上班模式在第一列最右、指數卡片與導覽置中、「設定」`#n-set`（美股頁／台股登入後）、外部連結「🔗 停利停損試算器 ↗」（`#xl`）；寬 1260px。手機導覽五顆一列（`html.nvA`），返回鈕 `#hbk`。
- 首頁：型態統計五卡（毛玻璃、置中）→「盤後一眼看懂」（預設收合，`mkcol`）→「強弱族群」（`swGroups()`／`swPanel()`，`SWV` 3，`grpcol`；中位數算法、≥5 檔、成交值 <1 千萬不算、6 成上漲／下跌、重疊過半留高者；相對抗跌族群；可點進族群 `data-swg`）。盤中每 2 分整頁重畫（`swLiveTick`→`home()`）；背景分頁不重抓。
- 首頁族群排序 `GSORTS`（存 `gsk`／`gsd`）＋自訂順序（`GSE`／`GSW`，存 `gso`，只存該裝置）：編輯列 🤚拖拉（pointer 事件、邊緣自動捲動）、雙上三角（`gsMove(name,-999)` 最上）、▲▼、雙下三角（最下），儲存／取消／重設。
- 股票列表：漲跌欄「股價／漲跌幅」（`chgCell`，`CPV` 2，漲跌停紅綠底，`tick`／`limPx`）；排序 `sortList()`／`SORTK`／`SORTD`；表頭 `#sth`；手機 `MCV` 3。
- 坑：頁內重畫前設 `navBack=false`（否則 `restoreNav` 捲回去）；inline handler 要寫 `window.scrollTo`。
- 返回：`navStack`、`goPrev()`、`navPos`／`restoreNav`；電腦 `#ttBack`、頂端／底部膠囊鈕（`TTV`／`TTA`）。
- 型態篩選頁：`FILTERS`、反轉小分類 `SUBF`（頂部只算 `dir==="bear"`）。綜合篩選：mops、revhi／yoyhi、m3up、nwup、本益比 6 顆、強勢、權值股 `wt`（`WTN` 50）。
- 美股綜合篩選只有本週強勢、今日強勢、三率三升。前端讀個股欄位一律防呆（`(s.candle||[])`）。
- 型態介紹頁 `#learn`（`learnPage()`，31 種自繪 SVG，突破箭頭黃 #facc15；目錄 `LIX` 3；`LZV` 2）。聯絡我們／免責聲明 `#about`。
- K 線視窗：日週月、還原價（有除權息預設開，`ADJDEF`）、均線、布林、DMI、KD、MACD、自訂區間、剪刀、區間框、形態（同時最多 2 個）、支撐、回檔%、反彈%（`RBV` 2，`rbk` 右側標籤）、管理者畫線（粉紅 #ff5fd2）。預設點選最新一根。
- 支撐：前低＝最高點之前最近一個未被跌破的波段低點（`calcStats().swingU`）；近期＝最高點後最低點。舊 `findSupport` 不用。
- 配色：MA 5 #facc15、10 #7FDBFF、20 #AF73E8、60 #e5e7eb、120 #FF9D70、250 #FFA300；綠 K #2DEB73；折線型態 #4D7CFF（突破實線、未成型虛線）；
  楔形 #D6DBE3（`WLV` 5）；頸線紅漲綠跌（`neckJobs`）；小字柔白 `--mute`（`MTV` 2）。
- 上一檔／下一檔（`__navList`、`NVV` 3、`location.replace`）。標題下一行 `valBar`（PE 等；>100 標「獲利低基期」）。
- 消息分頁（版本 2：左財報右新聞）：月營收長條、季營收與三率、EPS（含累計與去年全年 `ey`）、近 60 天法人目標價（只在 `adm=1`）；字體 A－／A＋（`nz`）；AI 摘要框 `.aisum`（`AIV` 2）；▲上修／－持平／▼下修（`NWDIR`，附「AI 自動整理，僅供參考，非投資建議」）。資料 `site/f/<代號>.json`（不一定存在，要防呆）。
- data.js 瘦身：台股 `geo` 只留 kind/dir/status/day，座標在 `site/s/<代號>.json`（美股不變）。
- 搜尋容錯 `fuzzyStocks()`；跨市場跳轉一次 `__bounced`。
