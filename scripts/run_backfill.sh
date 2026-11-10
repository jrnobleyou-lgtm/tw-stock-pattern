#!/bin/bash
# 補抓歷史行情 → 合併 → 重算 → 重建預覽
cd /home/user/tw-stock-site
python3 scripts/fetch_tw.py 400 twse && python3 scripts/fetch_tw.py 400 merge && python3 scripts/analyze.py | sed -n '1,2p' && python3 scripts/build_preview.py && echo BACKFILL_READY
