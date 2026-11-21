---
name: weekly-sync
description: 每週六 15:15 同步台美股族群與台股關注清單（關注清單存 Cloudflare KV）（讀 Google 試算表 → 套用到網站 → 寫異動紀錄 → 回報）。排程「每週六同步台美股族群」使用；步驟改動都改這個檔，不必改排程指令。
---

# 每週六族群＋關注清單同步

全程用繁體中文（連做事途中的說明也是），白話、時間一律台灣時間，回報用 ✅／❓。專案在工作目錄 `tw-stock-pattern`（沒有就 `git clone https://github.com/jrnobleyou-lgtm/tw-stock-pattern`）。先讀 `CLAUDE.md` 和 `docs/HANDOFF.md`。

試算表 ID：台股 `1wvK-q5yX7jhtqMkZc-Qg4mQphJghomKsUA21am7NKwc`、美股 `1Hhj5ZJ4sui-bI2lT7WzGbW4upBFqUPh_6Y2UZfdO7YM`。

## 1. 讀試算表
用 Google Sheets 的 `get_values`：台股讀「族群分類!A1:D3000」，美股讀「工作表1!A1:D3000」（美股若讀不到再試「族群分類」）。values 的處理方式見最下面「省事做法」（整張表不必逐列存 JSON）（二維陣列）到暫存資料夾：`tw.json`、`us.json`。讀不到或少於 50 列就停止並回報，不要動網站。
也讀兩個試算表的「異動紀錄!A1:D1000」，只看最後一列「網站同步」之後新增的紀錄，回報時一起提。異動紀錄不要清空、不要刪改舊列。

## 2. 套用族群
在**乾淨的 origin/main 工作樹**操作（`git fetch origin main`；`git worktree add /tmp/mainwt origin/main`；不要在工作分支 `pull --rebase`，會衝突），然後：
- `python3 scripts/apply_groups.py tw tw.json`；有變動就 commit（訊息「每週族群同步」）並 push 到 main。
- `python3 scripts/apply_groups.py us us.json --upload`（直接寫 Cloudflare KV，**美股清單絕不能進 GitHub**）。美股有變動就執行 `gh api -X POST repos/jrnobleyou-lgtm/tw-stock-pattern/actions/workflows/us.yml/dispatches -f ref=main`。

## 2b. 同步關注清單（不進公開的 GitHub，存 Cloudflare KV）
用 `get_values` 讀台股試算表的「關注股票_台股!A1:B500」，原封不動存成 `wl.json`（二維陣列），執行 `python3 scripts/apply_watchlist.py wl.json`（直接寫 Cloudflare KV `state/watchlist_tw`；少於 20 檔會自己拒絕、不動舊清單）。**不要把關注清單寫進專案檔案或 commit。** 回報裡寫程式印出的「新增／移除」。讀不到就略過並回報。
（美股「關注股票_美股」不處理。）

## 3. 確認上線
約 10 分鐘後確認 https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev/data.js 的族群有沒有更新、`us.yml` 有沒有成功。

## 4. 寫異動紀錄
用 `append_values` 在兩個試算表的「異動紀錄!A1」各加一列：`[日期, "網站同步", 變動內容（代號 名稱 舊族群 → 新族群，多檔用；分隔；沒變動寫「沒有變動」）, 失敗或備註]`。

## 5. 回報
白話回報：台股、美股各變動哪些股票、關注清單新增／移除哪幾檔、有沒有失敗。沒有變動就說「這週族群與關注清單沒有變動」。

## 省事做法與禁止事項（使用者 11/21 兩度抱怨「這種事你自己處理好」）
- **使用者說「試算表已更新」＝要我整張同步完，不准反問「你改了哪幾檔」**，也不准只改看得出來的那一兩檔。
- 步驟 1 一定要先讀兩個試算表「異動紀錄」最後一次「網站同步」之後的新列（含改名、新增、改產業別），回報時逐項說明有沒有處理；族群沒變但名稱／產業別改了的（例：美股 PSX 改名）要另外核對。
- 整張表不必原封不動存 JSON（太長）：把 get_values 的結果只抽成純文字 `代號|主族群` 逐行寫進暫存檔，再用小程式跟網站現況比對，只列差異：台股比對 `data/groups_tw_all.csv`（主族群＋副族群用「+」連起來；用 `git worktree` 的 origin/main 版本），美股比對 KV `state/groups_us_all.csv` 的第 4 欄。
- 有差異再建完整 JSON（名稱、產業別用網站現有的，主族群用試算表的）餵 `apply_groups.py`；沒差異就說「沒有變動」。
- 台股網站的股票名稱來自官方簡稱（例：意藍，試算表寫意藍資訊），不會因試算表改名而變，回報時註明即可。
- 做完推 main 前要 `git fetch`，在乾淨的 origin/main 工作樹操作（工作分支可能有別的未上線改動，`pull --rebase` 會衝突）。
