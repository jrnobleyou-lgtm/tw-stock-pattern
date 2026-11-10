"""Fetch daily OHLCV for the watchlist from TWSE (上市) and TPEx (上櫃).
Resumable: raw per-day JSON is cached in data/raw/. Output: data/prices_tw.csv
"""
import csv, json, os, sys, time, datetime, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
UA = {"User-Agent": "Mozilla/5.0"}
DAYS_BACK = int(sys.argv[1]) if len(sys.argv) > 1 else 260

def get(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            time.sleep(10 * (i + 1))
    return None

def num(s):
    s = str(s).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None

watch = {r["代號"] for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw.csv"), encoding="utf-8"))}

def twse(d):
    f = os.path.join(RAW, f"twse_{d:%Y%m%d}.json")
    if os.path.exists(f):
        return json.load(open(f))
    j = get("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=%s&type=ALLBUT0999&response=json" % d.strftime("%Y%m%d"))
    rows = []
    if j and j.get("stat") == "OK":
        for t in j.get("tables", []):
            if "證券代號" in t.get("fields", []) and "收盤價" in t["fields"]:
                for r in t["data"]:
                    if r[0] in watch:
                        rows.append([r[0], num(r[5]), num(r[6]), num(r[7]), num(r[8]), num(r[2])])
    if j is None:
        return None            # 被擋或連線失敗：不快取，稍後重試
    out = {"ok": j.get("stat") == "OK", "rows": rows}
    json.dump(out, open(f, "w"))
    time.sleep(float(os.environ.get('TWSE_SLEEP', '20')))
    return out

def tpex(d):
    f = os.path.join(RAW, f"tpex_{d:%Y%m%d}.json")
    if os.path.exists(f):
        return json.load(open(f))
    j = get("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=%s&type=EW&response=json" % urllib.parse.quote(d.strftime("%Y/%m/%d"), safe=""))
    rows = []
    ok = False
    if j and j.get("tables"):
        t = j["tables"][0]
        ok = bool(t.get("data"))
        for r in t.get("data", []):
            if r[0] in watch:
                rows.append([r[0], num(r[4]), num(r[5]), num(r[6]), num(r[2]), num(r[7])])
    if j is None:
        return None
    out = {"ok": ok, "rows": rows}
    json.dump(out, open(f, "w"))
    time.sleep(0.5)
    return out

from concurrent.futures import ThreadPoolExecutor
today = datetime.date.today()
days = [today - datetime.timedelta(n) for n in range(DAYS_BACK, -1, -1)]
days = [d for d in days if d.weekday() < 5]

def retry(fn, d):
    for k in range(12):
        r = fn(d)
        if r is not None:
            return r
        print("  blocked/failed", fn.__name__, d, "wait 600s", flush=True)
        time.sleep(600)        # 等封鎖解除
    raise SystemExit(f"giving up on {d}")

mode = sys.argv[2] if len(sys.argv) > 2 else "all"
if mode in ("twse", "all"):
    for k, d in enumerate(days):
        retry(twse, d)
        if k % 10 == 0:
            print("twse", d, k, "/", len(days), flush=True)
if mode in ("tpex", "all"):
    with ThreadPoolExecutor(max_workers=5) as ex:
        list(ex.map(lambda d: retry(tpex, d), days))
    print("tpex done", flush=True)

if mode in ("merge", "all"):
    allrows = []
    for d in days:
        a, b = twse(d), tpex(d)
        if not a["ok"]:
            continue   # 休市日
        for r in a["rows"]:
            allrows.append([d.isoformat(), r[0], "TWSE"] + r[1:])
        for r in b["rows"]:
            allrows.append([d.isoformat(), r[0], "TPEX"] + r[1:])
    with open(os.path.join(ROOT, "data", "prices_tw.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "code", "market", "open", "high", "low", "close", "volume"])
        w.writerows(allrows)
    print("merged rows:", len(allrows), "codes:", len({r[1] for r in allrows}), "of", len(watch))
