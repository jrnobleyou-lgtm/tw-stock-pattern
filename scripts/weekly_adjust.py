"""每週一次：用 Yahoo 重新核對全市場的除權息調整事件（證交所上市股沒有「次日參考價」，靠這支補上）。
每檔一次請求、每 2 秒一次；遇到 429 就停止，已核對的檔照常寫入。結果寫回 data/adjust.csv（逐檔替換該檔的事件）。"""
import csv, json, os, sys, time, datetime, urllib.request, urllib.error
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TW = datetime.timezone(datetime.timedelta(hours=8))
rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8")))
ap = os.path.join(ROOT, "data", "adjust.csv")
old = {}
for r in csv.DictReader(open(ap, encoding="utf-8")):
    old.setdefault(r["code"], []).append((r["exdate"], r["k"]))
new, ok, fail = {}, 0, 0
for g in rows:
    code, sym = g["代號"], g["代號"] + (".TW" if g["市場"] == "TWSE" else ".TWO")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d&includeAdjustedClose=true"
    time.sleep(2.0)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=40) as r:
            j = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print("429 請求太多，停止（已核對", ok, "檔）"); break
        fail += 1; continue
    except Exception:
        fail += 1
        if fail >= 20: print("連續失敗太多，停止"); break
        continue
    res = (j.get("chart") or {}).get("result")
    if not res:
        continue
    r0 = res[0]; ts = r0.get("timestamp") or []
    q = (r0["indicators"].get("quote") or [{}])[0]; adj = (r0["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    if not adj or not q.get("close"):
        continue
    f = [(datetime.datetime.fromtimestamp(t, TW).date().isoformat(), a / c) for t, a, c in zip(ts, adj, q["close"]) if a and c]
    ev = [(f[i][0], f"{f[i-1][1] / f[i][1]:.6f}") for i in range(1, len(f)) if abs(f[i-1][1] / f[i][1] - 1) > 4e-4]
    new[code] = ev; ok += 1
merged = {c: e for c, e in old.items() if c not in new}
merged.update({c: e for c, e in new.items() if e})
with open(ap, "w", newline="", encoding="utf-8") as fo:
    w = csv.writer(fo); w.writerow(["code", "exdate", "k"])
    for c in sorted(merged):
        for d, k in sorted(merged[c]):
            w.writerow([c, d, k])
print("核對", ok, "檔；失敗", fail, "；有除權息事件的檔數", len(merged))
