"""每日收盤後更新：抓最近幾天的官方資料（證交所 + 櫃買各 1 次請求/天），再合併重算。
用法：python3 daily.py [回看天數，預設 3] [tpex|twse|both，預設 both]
注意：盤前／盤中抓到「沒有資料」的快取會被清掉重抓（避免把尚未收盤誤當休市日）。
"""
import json, os, sys, time, datetime, glob, re, urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "rawall")
UA = {"User-Agent": "Mozilla/5.0"}
CODE = re.compile(r"^\d{4}$")
back = int(sys.argv[1]) if len(sys.argv) > 1 else 3
market = sys.argv[2] if len(sys.argv) > 2 else "both"
TW = datetime.timezone(datetime.timedelta(hours=8))
now = datetime.datetime.now(TW)

def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None

def fetch_twse(d):
    j = get("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=%s&type=ALLBUT0999&response=json" % d.strftime("%Y%m%d"))
    if j is None:
        return None
    rows = []
    if j.get("stat") == "OK":
        for t in j.get("tables", []):
            if "證券代號" in t.get("fields", []) and "收盤價" in t["fields"]:
                rows = [[r[0], r[1].strip(), num(r[5]), num(r[6]), num(r[7]), num(r[8]), num(r[2])] for r in t["data"] if CODE.match(r[0])]
    return {"ok": j.get("stat") == "OK", "rows": rows}

def fetch_tpex(d):
    j = get("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=%s&type=EW&response=json" % urllib.parse.quote(d.strftime("%Y/%m/%d"), safe=""))
    if j is None:
        return None
    rows, ok = [], False
    if j.get("tables"):
        t = j["tables"][0]; ok = bool(t.get("data"))
        rows = [[r[0], r[1].strip(), num(r[4]), num(r[5]), num(r[6]), num(r[2]), num(r[7])] for r in t.get("data", []) if CODE.match(r[0])]
    return {"ok": ok, "rows": rows}

days = [(now - datetime.timedelta(n)).date() for n in range(back)]
days = [d for d in days if d.weekday() < 5]
if now.hour < 14:                         # 台灣時間 14:00 前，今天尚未收盤
    days = [d for d in days if d != now.date()]
for d in sorted(days):
    for name, fn in (("twse", fetch_twse), ("tpex", fetch_tpex)):
        if market != "both" and name != market:
            continue
        f = os.path.join(RAW, f"{name}_{d:%Y%m%d}.json")
        if os.path.exists(f):
            old = json.load(open(f))
            if old.get("ok") and old.get("rows"):
                continue
            os.remove(f)                  # 空的快取：重抓
        res = fn(d)
        if res is None:
            print("失敗", name, d, "（被擋或連線問題，不重試）"); continue
        json.dump(res, open(f, "w"), ensure_ascii=False)
        print(name, d, "ok" if res["ok"] else "休市/無資料", len(res["rows"]))
        time.sleep(3)
