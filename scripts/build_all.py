"""合併 Yahoo 歷史（含還原係數）+ 官方近期資料 → data/prices_all.csv
欄位：date,code,name,market,open,high,low,close,volume,f   （f = 還原係數 = 還原收盤 / 原始收盤；原始價 × f = 還原價）
Yahoo 資料到哪一天為止，之後的日子改用官方（證交所/櫃買）每日資料補上（f=1）。
"""
import csv, glob, json, os, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
grp = {r["代號"]: r for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8"))}
YH = os.path.join(ROOT, "data", "yh")
RAW = os.path.join(ROOT, "data", "rawall")

# 官方每日資料（只收 ok 且有資料的日子）
official = {}      # date -> {code: (name,o,h,l,c,v,market)}
for f in sorted(glob.glob(os.path.join(RAW, "t*_*.json"))):
    base = os.path.basename(f)
    mk = "TWSE" if base.startswith("twse") else "TPEX"
    d = base.split("_")[1][:8]
    date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    j = json.load(open(f))
    if not j.get("ok") or not j.get("rows"):
        continue
    for r in j["rows"]:
        if None in r[2:6]:
            continue
        official.setdefault(date, {})[r[0]] = (r[1], r[2], r[3], r[4], r[5], r[6] or 0, mk)

out, nyh, nof = [], 0, 0
last_yh = {}
for code, g in grp.items():
    p = os.path.join(YH, code + ".json")
    rows = []
    last = ""
    if os.path.exists(p):
        j = json.load(open(p))
        for i, d in enumerate(j.get("d", [])):
            c = j["c"][i]
            f = (j["adj"][i] / c) if c else 1.0
            rows.append([d, code, g["名稱"], g["市場"], j["o"][i], j["h"][i], j["l"][i], c, j["v"][i], round(f, 6)])
            last = d
        nyh += 1 if rows else 0
    last_yh[code] = last
    out += rows
# 官方資料補在 Yahoo 最後一天之後
for date in sorted(official):
    for code, (name, o, h, l, c, v, mk) in official[date].items():
        if code in grp and date > last_yh.get(code, ""):
            out.append([date, code, grp[code]["名稱"], mk, o, h, l, c, v, 1.0]); nof += 1
out.sort(key=lambda r: (r[1], r[0]))
with open(os.path.join(ROOT, "data", "prices_all.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["date", "code", "name", "market", "open", "high", "low", "close", "volume", "f"])
    w.writerows(out)
dates = sorted({r[0] for r in out})
print(f"合併完成：{len(out)} 列；Yahoo 有資料 {nyh} 檔；官方補列 {nof}；日期 {dates[0]} ~ {dates[-1]}（{len(dates)} 天）")
