"""一次性：把 data/prices_all.csv 拆成「按月份的原始價文字檔」＋「除權息調整事件」，方便放進 Git。
輸出：data/hist/YYYY-MM.csv（date,code,market,open,high,low,close,volume；原始價）
      data/adjust.csv（code,exdate,k；除權息日之前的價格 × k 還原；多次事件連乘）
"""
import csv, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "data", "hist"); os.makedirs(H, exist_ok=True)
by_month = collections.defaultdict(list)
series = collections.defaultdict(list)          # code -> [(date, f)]
for r in csv.DictReader(open(os.path.join(ROOT, "data", "prices_all.csv"), encoding="utf-8")):
    by_month[r["date"][:7]].append([r["date"], r["code"], r["market"], r["open"], r["high"], r["low"], r["close"], r["volume"]])
    series[r["code"]].append((r["date"], float(r["f"])))
for m, rows in by_month.items():
    rows.sort(key=lambda x: (x[0], x[1]))
    with open(os.path.join(H, m + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["date", "code", "market", "open", "high", "low", "close", "volume"]); w.writerows(rows)
ev = []
for code, s in series.items():
    s.sort()
    for i in range(1, len(s)):
        k = s[i - 1][1] / s[i][1] if s[i][1] else 1.0
        if abs(k - 1) > 4e-4:
            ev.append([code, s[i][0], round(k, 6)])
ev.sort()
with open(os.path.join(ROOT, "data", "adjust.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["code", "exdate", "k"]); w.writerows(ev)
print("月檔", len(by_month), "；除權息事件", len(ev), "；檔數", len({e[0] for e in ev}))
