"""11/21：把「只重算畫線股」的結果（site/partial.json、site/s/<代號>.json）補進線上目前的網站資料。
用法：merge_partial.py <線上網站資料夾（deploy 分支內容）>。族群統計不動，等下一次排程或「全部重算」才一致。"""
import json, os, shutil, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
live = sys.argv[1]
SRC = os.path.join(ROOT, "site", sys.argv[2]) if len(sys.argv) > 2 else os.path.join(ROOT, "site")      # 美股傳 "us"
new = json.load(open(os.path.join(SRC, "partial.json"), encoding="utf-8"))
dp = os.path.join(live, "data.js")
t = open(dp, encoding="utf-8").read()
assert t.startswith("window.DATA=")
D = json.loads(t[len("window.DATA="):].rstrip().rstrip(";"))
n = 0
for code, st in new.items():
    old = D["stocks"].get(code)
    if old is None:
        continue
    for k in ("drawUpd", "dch"):
        old.pop(k, None)
    old.update({k: v for k, v in st.items() if not k.startswith("_")})      # _w／_s 是分析途中的暫存欄，全市場版最後會刪掉
    sp = os.path.join(SRC, "s", code + ".json")
    if os.path.isdir(os.path.join(live, "s")) and os.path.exists(sp):
        shutil.copy(sp, os.path.join(live, "s", code + ".json"))
    n += 1
if n == 0 and not new:
    print("沒有任何畫線股，不用更新"); sys.exit(0)
assert n > 0 and len(D["stocks"]) > 100, "補進的檔數或股票總數不對，不上傳"      # 防呆：壞資料不要覆蓋線上
open(dp, "w", encoding="utf-8").write("window.DATA=" + json.dumps(D, ensure_ascii=False, separators=(",", ":")) + ";")
shutil.copy(os.path.join(SRC, "recmp.json"), os.path.join(live, "recmp.json"))
print("已補進", n, "檔")
open(os.path.join(live, ".merged"), "w").write("1")
