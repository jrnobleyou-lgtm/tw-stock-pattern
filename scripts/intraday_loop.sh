#!/usr/bin/env bash
# 盤中循環（由 GitHub Actions 在台灣時間 08:50 啟動一次，之後在同一個工作裡每輪重算）：
#   抓全市場現價 → 組成今日暫時日 K → 重新分析 → 發布到 deploy 分支；輪與輪之間休息 90 秒。
# 這樣不用依賴 GitHub 的「每 10 分鐘排程」（那種排程常被延遲或直接略過）。
# 休市日（開盤後一直抓不到今日資料）會自動結束。
cd "$(dirname "$0")/.."
export TZ=Asia/Taipei
end=$(date -d "today 13:50" +%s)
open=$(date -d "today 09:02" +%s)
cycle=0
while [ "$(date +%s)" -lt "$end" ]; do
  now=$(date +%s)
  if [ "$now" -lt "$open" ]; then sleep $((open - now)); continue; fi
  cycle=$((cycle + 1))
  echo "=== 第 $cycle 輪 $(date +%T) ==="
  # 每輪先取最新的網頁與程式（避免長時間運行的舊版覆蓋掉之後的修改）；不更新本檔案自己
  git fetch -q origin main 2>/dev/null && git checkout -q origin/main -- site/index.html site/worker.js site/wrangler.jsonc site/.assetsignore $(git ls-tree -r --name-only origin/main scripts | grep '\.py$') 2>/dev/null
  if python3 scripts/intraday.py; then
    python3 scripts/build_prices.py && python3 scripts/analyze.py all && {
      rm -rf /tmp/pub && mkdir /tmp/pub && cp -r site/. /tmp/pub/
      rm -f /tmp/pub/preview.html /tmp/pub/index_v1.html
      ( cd /tmp/pub && git init -q -b deploy && git config user.name github-actions && git config user.email actions@users.noreply.github.com \
        && git add -A && git commit -q -m "intraday $(date -u +%FT%TZ)" \
        && git push -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" deploy ) || echo "發布失敗，下一輪再試"
    }
  else
    if [ "$cycle" -le 1 ] && [ "$(date +%s)" -gt $(date -d "today 09:20" +%s) ]; then echo "開盤後仍沒有今日資料，視為休市"; exit 0; fi
  fi
  sleep 90
done
echo "盤中循環結束 $(date +%T)"
