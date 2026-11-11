"""盤中更新：向網站的 /api/mis（Cloudflare 代抓證交所即時行情）取全市場現價，
組成「今天的暫時日 K」寫到 data/intraday.csv（不進版控），build_prices.py 會把它接在歷史後面一起分析。
若某檔昨收參考價 ≠ 昨天收盤（今天除權息），另寫 data/intraday_adjust.csv 讓還原價正確。
輸出 data/intraday_meta.json（資料時間、檔數）；沒有新資料就不產生檔案。"""
import csv, glob, json, os, sys, time, urllib.request, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.environ.get("SITE_URL", "").rstrip("/")
if not SITE:
    sys.exit("缺少 SITE_URL")
for f in ("intraday.csv", "intraday_adjust.csv", "intraday_meta.json"):
    p = os.path.join(ROOT, "data", f)
    if os.path.exists(p): os.remove(p)

groups = list(csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8")))
mk = {g["代號"]: (g.get("市場") or "") for g in groups}
last = {}                                   # 每檔歷史最後一筆（日期, 收盤）
for f in sorted(glob.glob(os.path.join(ROOT, "data", "hist", "*.csv")))[-2:]:
    for r in csv.DictReader(open(f, encoding="utf-8")):
        if r["code"] not in last or r["date"] >= last[r["code"]][0]:
            last[r["code"]] = (r["date"], float(r["close"]))
adj_have = set()
ap = os.path.join(ROOT, "data", "adjust.csv")
if os.path.exists(ap):
    adj_have = {(r["code"], r["exdate"]) for r in csv.DictReader(open(ap, encoding="utf-8"))}

def fetch(chunk, tries=4):
    url = SITE + "/api/mis?ex_ch=" + "%7C".join(chunk)
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8")).get("msgArray") or []
        except Exception as e:
            print("  失敗", repr(e)[:80]); time.sleep(3 * (i + 1))
    return []

def num(x):
    try:
        v = float(str(x).replace(",", ""))
        return v if v > 0 else None
    except ValueError:
        return None

chs = [("tse_" if mk.get(g["代號"], "").upper().startswith("TWSE") else "otc_") + g["代號"].lower() + ".tw" for g in groups if g["代號"].isdigit() and len(g["代號"]) == 4]
rows, adjs, tmax, dmax = [], [], "", ""
got = set()
def take(m):
    global dmax, tmax
    code = m.get("c", "")
    d = str(m.get("d", ""))
    got.add(code)
    o, h, l, y = (num(m.get(k)) for k in ("o", "h", "l", "y"))
    z = num(m.get("z"))
    c = z if z else (num(str(m.get("b", "")).split("_")[0]) or o)
    if len(d) != 8 or None in (o, h, l, c) or code not in last:
        return
    date = f"{d[:4]}-{d[4:6]}-{d[6:]}"
    if date <= last[code][0]:
        return                                         # 官方資料已經有這天
    v = int((num(m.get("v")) or 0) * 1000)
    rows.append([date, code, "TWSE" if m.get("ex") == "tse" else "TPEX", o, max(h, c), min(l, c), c, v])
    if date > dmax: dmax, tmax = date, ""
    if date == dmax: tmax = max(tmax, m.get("t", ""))
    if y and abs(y / last[code][1] - 1) > 4e-4 and (code, date) not in adj_have:
        adjs.append([code, date, round(y / last[code][1], 6)])
todo = chs
for rnd, size in enumerate((100, 50, 25)):               # 第一輪每批 100 檔；沒抓到的再用小批次補抓
    for i in range(0, len(todo), size):
        for m in fetch(todo[i:i + size]):
            take(m)
        time.sleep(2)
    todo = [x for x in chs if x.split("_")[1].split(".")[0] not in got]
    print(f"第 {rnd + 1} 輪後還缺 {len(todo)} 檔")
    if not todo: break
print("盤中資料：", len(rows), "檔；日期", dmax, "時間", tmax, "；今日除權息", len(adjs))
if len(rows) < 100:
    sys.exit("資料太少（可能休市或來源失敗），不更新")
with open(os.path.join(ROOT, "data", "intraday.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["date", "code", "market", "open", "high", "low", "close", "volume"]); w.writerows(rows)
with open(os.path.join(ROOT, "data", "intraday_adjust.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["code", "exdate", "k"]); w.writerows(adjs)
json.dump({"date": dmax, "hms": tmax[:5], "n": len(rows)}, open(os.path.join(ROOT, "data", "intraday_meta.json"), "w"))
