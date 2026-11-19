# 主題：族群、美股、ETF

試算表同步、美股更新鏈與限制、ETF 專區。

## 族群
- 台股試算表 `Claude_網站分類_台股`（ID `1wvK-q5yX7jhtqMkZc-Qg4mQphJghomKsUA21am7NKwc`，分頁「族群分類」）。
- 美股試算表 `Claude_網站分類_美股`（ID `1Hhj5ZJ4sui-bI2lT7WzGbW4upBFqUPh_6Y2UZfdO7YM`，分頁「工作表1」）。
- 欄位「代號,名稱,產業別,主族群」，多族群用「+」；「異動紀錄」分頁只看上次「網站同步」之後的新列。
- 套用 `scripts/apply_groups.py tw|us <json>`（美股 `--upload` 直接寫 KV）；台股寫 `data/groups_tw_all.csv`；`gl_of()` 支援「+」「、」。
- 每週六 15:15 排程 `trig_01C1hrzzY2io3gRmGr7zX3ce`（使用者建，只有他能改）照 `.claude/skills/weekly-sync/SKILL.md` 執行。雲端硬碟工具只看得到自己建立的檔案。
- 美股股票池 `scripts/us_universe.py`（NASDAQ 篩選器，約 4,089 檔，含 6 檔 OTC ADR）；使用者 234 檔分類優先，其餘自動對應。美股族群清單、歷史、關注清單都不進版控。

## 美股
- `us_fetch.py`（6 執行緒 Yahoo）、`us_fin.py`（SEC，User-Agent 用網站公開信箱；`site/us/fn/<0-31>.json`；失敗 >10% 不更新）、`us_sync.py`（含 `draw-list/US`→`data/us/draw.json`）。
- 美股有：五種型態、DMI、畫線比對、強弱族群、面板（指數＋VIX）、季財報／EPS／三率、本週／今日強勢（含大型）。
- **使用者決定不做**：美股新聞、月營收、重訊、本益比、目標價、權值股、漲跌停判斷。美股關注清單 129 檔只在試算表。

## ETF
- `scripts/etf.py`：`daily`（`data/hist_etf/YYYY-MM.csv`、`data/etf_class.csv`）、`yahoo`（近 1 年，未還原配息）、`build`（`site/etf.json`、`site/s/<代號>.json`）；手動覆寫 `data/etf_override.csv`。
- 不進 `data.js`／族群（1,980 檔統計不變）、不做型態判斷；`intraday_loop.sh` 每輪 `etf.py build`。前端 `#etf`、`#etf-active`、`#e-<代號>`；槓桿反向預設隱藏；美股頁隱藏。
