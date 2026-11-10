# 每日股票型態確認

台股上市櫃 1984 檔，依族群統計「轉強／型態好／盤整／走弱」，並在 K 線圖上標出盤整區間、突破訊號與各種型態。

- 網站：`site/`（純靜態，GitHub Pages 部署）
- 每日資料更新與重算：`.github/workflows/update.yml`
  - 上櫃（台灣時間週一～週五 15:10～17:40）、上市（週二～週六 06:00～07:30）各自排程，缺什麼補什麼
- 每週還原價校正：`.github/workflows/weekly-adjust.yml`
- 族群分類：`data/groups_tw_all.csv`
- 歷史行情（原始價，按月份）：`data/hist/`；除權息調整事件：`data/adjust.csv`
- 型態偵測：`scripts/engine.py`、`scripts/patterns.py`

內容由程式依公開資料自動計算，僅供研究參考，不構成投資建議。
