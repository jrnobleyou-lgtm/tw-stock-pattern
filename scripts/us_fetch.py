"""美股日 K（Yahoo Finance chart API）。
  - 第一次（該檔沒有資料）抓 range=5y；之後每日抓 range=5d 補最新幾天。
  - 還原價直接用 Yahoo 回傳的 adjclose（已含分割＋股利），存成係數 f = adjclose / close。
    5 天內若出現分割或除息事件，舊資料的 f 全部會變 → 該檔改抓 5y 重建。
  - 先抓 AAPL 確認 Yahoo 最新交易日；已經是最新的股票直接略過（中斷後重跑會從斷點接）。
  - 每次請求間隔 0.8 秒；遇到 HTTP 429 立刻停止，下次再接。
  - 只保留最近 KEEP_DAYS 個日曆日。
輸出 data/us/hist.csv（date,code,open,high,low,close,volume,f）與 data/prices_us.csv（analyze.py 用的格式）。"""
import csv, datetime, json, os, sys, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "data", "us", "hist.csv")
KEEP_DAYS = 800      # 約 550 根日 K（圖最多顯示 520 根）
GAP = 0.25           # 每條執行緒兩次請求的間隔
WORKERS = 6

def ysym(code):
    return code.replace(".", "-")

class RateLimited(Exception):
    pass

def chart(code, rng):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym(code)}?range={rng}&interval=1d&events=div%7Csplit&includeAdjustedClose=true"
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimited()
            if e.code == 404:
                return None
            time.sleep(3 * (i + 1))
        except Exception:
            time.sleep(3 * (i + 1))
    return None

def parse(j):
    r = (j or {}).get("chart", {}).get("result") or []
    if not r or not r[0].get("timestamp"):
        return [], False
    r = r[0]; off = r["meta"].get("gmtoffset", -18000)
    q = r["indicators"]["quote"][0]; adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose")
    out = []
    for i, t in enumerate(r["timestamp"]):
        o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
        if None in (o, h, l, c) or c <= 0:
            continue
        d = datetime.datetime.fromtimestamp(t + off, datetime.timezone.utc).date().isoformat()
        f = (adj[i] / c) if adj and adj[i] else 1.0
        out.append([d, round(o, 4), round(h, 4), round(l, 4), round(c, 4), int(v or 0), round(f, 6)])
    ev = r.get("events") or {}
    return out, bool(ev.get("dividends") or ev.get("splits"))

GFILE = os.path.join(ROOT, "data", "groups_us_all.csv")
if not os.path.exists(GFILE):
    GFILE = os.path.join(ROOT, "data", "groups_us.csv")
codes = [r["代號"] for r in csv.DictReader(open(GFILE, encoding="utf-8"))]
hist = {}
if os.path.exists(HIST):
    for r in csv.DictReader(open(HIST, encoding="utf-8")):
        hist.setdefault(r["code"], {})[r["date"]] = [r["date"], float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), int(float(r["volume"])), float(r["f"])]

latest = None
try:
    rows, _ = parse(chart("AAPL", "5d")); latest = rows[-1][0] if rows else None
except RateLimited:
    sys.exit("Yahoo 限流（429），稍後再跑")
print("Yahoo 最新交易日", latest)
import threading
from concurrent.futures import ThreadPoolExecutor
stop = threading.Event(); lock = threading.Lock(); stat = {"done": 0, "rebuilt": 0}
def work(code):
    if stop.is_set():
        return
    have = hist.get(code, {})
    if have and latest and max(have) >= latest:
        return
    try:
        time.sleep(GAP)
        full = not have
        rows, has_ev = parse(chart(code, "3y" if full else "5d"))
        if not full and has_ev:                      # 近幾天有分割或除息：整檔重建，讓舊資料的還原係數跟著更新
            time.sleep(GAP); rows, _ = parse(chart(code, "3y")); full = True
            with lock: stat["rebuilt"] += 1
    except RateLimited:
        stop.set(); return
    if not rows:
        return
    with lock:
        if full:
            hist[code] = {}
        for r in rows:
            hist.setdefault(code, {})[r[0]] = r
        stat["done"] += 1
with ThreadPoolExecutor(WORKERS) as ex:
    list(ex.map(work, codes))
if stop.is_set():
    print("遇到 429（Yahoo 限流），先停在這裡，下次從斷點接著抓")
done, rebuilt = stat["done"], stat["rebuilt"]
cut = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
with open(HIST, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["date", "code", "open", "high", "low", "close", "volume", "f"])
    for code in sorted(hist):
        for d in sorted(hist[code]):
            if d >= cut:
                w.writerow([d, code] + hist[code][d][1:])
names = {r["代號"]: r["名稱"] for r in csv.DictReader(open(GFILE, encoding="utf-8"))}
with open(os.path.join(ROOT, "data", "prices_us.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["date", "code", "name", "market", "open", "high", "low", "close", "volume", "f"])
    for code in sorted(hist):
        for d in sorted(hist[code]):
            if d >= cut:
                r = hist[code][d]; w.writerow([d, code, names.get(code, ""), "US", r[1], r[2], r[3], r[4], r[5], r[6]])
print("更新", done, "檔（其中重建", rebuilt, "檔）；共", len(hist), "檔")
