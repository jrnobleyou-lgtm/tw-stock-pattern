"""抓大盤指數日 K：加權指數（Yahoo ^TWII）、櫃買指數（櫃買中心月查詢，約 25 次小請求）。
輸出 data/index_TWII.json / data/index_OTC.json：[[日期, 開, 高, 低, 收, 量, 1.0], ...]
"""
import json, os, time, datetime, urllib.request, urllib.parse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = {"User-Agent": "Mozilla/5.0"}
TW = datetime.timezone(datetime.timedelta(hours=8))
now = datetime.datetime.now(TW)

def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(5 * (i + 1))
    return None

def num(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None

def merge_old(name, rows):
    p = os.path.join(ROOT, "data", name)
    old = json.load(open(p)) if os.path.exists(p) else []
    return sorted({r[0]: r for r in (old + rows)}.values())

FULL = not os.path.exists(os.path.join(ROOT, "data", "index_TWII.json"))
# 加權指數
j = get("https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?range=" + ("2y" if FULL else "1mo") + "&interval=1d")
rows = []
if j and j["chart"]["result"]:
    r = j["chart"]["result"][0]; q = r["indicators"]["quote"][0]
    for i, t in enumerate(r["timestamp"]):
        d = datetime.datetime.fromtimestamp(t, TW).date()
        if now.hour < 14 and d == now.date():
            continue                                  # 盤中未完成
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        rows.append([d.isoformat(), round(o, 2), round(h, 2), round(l, 2), round(c, 2), 0, 1.0])
if rows:
    json.dump(merge_old("index_TWII.json", rows), open(os.path.join(ROOT, "data", "index_TWII.json"), "w"))
print("加權", len(rows), rows[-1] if rows else None, flush=True)

# 櫃買指數：逐月查詢
rows, m = [], datetime.date(now.year, now.month, 1)
months = []
for k in range(26 if FULL else 2):
    months.append(m)
    m = (m.replace(day=1) - datetime.timedelta(days=1)).replace(day=1)
for m in sorted(months):
    j = get("https://www.tpex.org.tw/www/zh-tw/indexInfo/inx?date=%s&response=json" % urllib.parse.quote(m.strftime("%Y/%m/01"), safe=""))
    if j and j.get("tables") and j["tables"][0].get("data"):
        for r in j["tables"][0]["data"]:
            o, h, l, c = (num(x) for x in r[1:5])
            if None in (o, h, l, c):
                continue
            rows.append([r[0].replace("/", "-"), o, h, l, c, 0, 1.0])
    time.sleep(1.0)
rows = sorted({r[0]: r for r in rows}.values())
if rows:
    json.dump(merge_old("index_OTC.json", rows), open(os.path.join(ROOT, "data", "index_OTC.json"), "w"))
print("櫃買", len(rows), rows[0][0] if rows else None, rows[-1] if rows else None, flush=True)
