"""由 data/hist/*.csv（原始價）＋ data/adjust.csv（除權息事件）組出 data/prices_all.csv（含還原係數 f）。
還原係數 f（某日）＝ 該日之後所有除權息事件的 k 連乘；最新一天 f = 1。"""
import csv, glob, os, collections
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
names = {r["代號"]: r["名稱"] for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8"))}
events = collections.defaultdict(list)
ap = os.path.join(ROOT, "data", "adjust.csv")
if os.path.exists(ap):
    for r in csv.DictReader(open(ap, encoding="utf-8")):
        events[r["code"]].append((r["exdate"], float(r["k"])))
rows = []
for f in sorted(glob.glob(os.path.join(ROOT, "data", "hist", "*.csv"))):
    for r in csv.DictReader(open(f, encoding="utf-8")):
        rows.append(r)
ip = os.path.join(ROOT, "data", "intraday.csv")        # 盤中暫時日 K（只存在於盤中排程那次執行，不進版控）
if os.path.exists(ip):
    rows += list(csv.DictReader(open(ip, encoding="utf-8")))
    iap = os.path.join(ROOT, "data", "intraday_adjust.csv")
    if os.path.exists(iap):
        for r in csv.DictReader(open(iap, encoding="utf-8")):
            events[r["code"]].append((r["exdate"], float(r["k"])))
rows.sort(key=lambda r: (r["code"], r["date"]))
out = []
cur = None; evs = []
for r in rows:
    if r["code"] != cur:
        cur = r["code"]; evs = sorted(events.get(cur, []), reverse=True)
    f = 1.0
    for d, k in evs:
        if r["date"] < d:
            f *= k
    out.append([r["date"], r["code"], names.get(r["code"], ""), r["market"], r["open"], r["high"], r["low"], r["close"], r["volume"], round(f, 6)])
out.sort(key=lambda x: (x[0], x[1]))
with open(os.path.join(ROOT, "data", "prices_all.csv"), "w", newline="", encoding="utf-8") as fo:
    w = csv.writer(fo); w.writerow(["date", "code", "name", "market", "open", "high", "low", "close", "volume", "f"]); w.writerows(out)
print("prices_all.csv", len(out), "列；", out[0][0], "~", out[-1][0])
