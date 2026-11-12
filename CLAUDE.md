# 每日股票型態確認：給 Claude 的工作須知

開新對話時先讀這份，再讀下面引用的交接檔（依序，每份約 200 行內，滿了開下一個數字並在這裡加一行引用）：

@docs/HANDOFF.md
@docs/HANDOFF-2.md

## 跟使用者溝通
- 一律用**繁體中文**回覆，不要夾英文句子（使用者看不懂英文）。專有名詞可附英文。
- 使用者不寫程式：說明要用白話，步驟要具體到「按哪個按鈕」。
- 改完上線前，**自己先實際打開線上網站檢查一輪**再回報，不要等使用者發現壞掉。
- 需要使用者在別的網站操作（Cloudflare、GitHub）時，給一步一步的說明，畫面跟說明不同就請他截圖。
- 金鑰、密碼不要貼在對話裡；用 request_credential 安全表單。

## 專案重點
- 網站：Cloudflare Workers（靜態網站＋`site/worker.js` 後端），從 GitHub `deploy` 分支自動部署。
- 台股公開；`/admin/` 是「管理者專區」（美股，密碼登入），資料放 Cloudflare KV，**不能放進公開的 GitHub**。
- 美股族群清單（`data/groups_us*.csv`）、美股歷史資料都不進版控（.gitignore 已排除）。
- 主程式：`scripts/analyze.py`（台股 `all`、美股 `us`）、`scripts/engine.py`（盤整區間與五種型態）、`scripts/patterns.py`（幾何形態）、`site/index.html`（整個前端，台股與管理者專區共用）。
- 推到 `main` 會觸發 `.github/workflows/update.yml` 重建並推到 `deploy`；Cloudflare 偶爾沒自動部署，可用 Cloudflare API 觸發建置（見 HANDOFF）。
