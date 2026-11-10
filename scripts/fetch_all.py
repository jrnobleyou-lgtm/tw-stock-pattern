"""抓取全市場（上市＋上櫃 4 位數股票代號）每日行情。
- 從最近的日期往回抓：就算中途被限速，最近的資料也先到位。
- 全程可續跑：每天的原始資料快取在 data/rawall/，失敗不快取。
- 證交所對連續請求有上限，預設每 30 秒一次，被擋就等 10 分鐘。
用法：python3 fetch_all.py <往回幾天> [twse|tpex|merge|all]
"""
import csv, json, os, re, sys, time, datetime, threading, urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "rawall")
os.makedirs(RAW, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}
DAYS_BACK = int(sys.argv[1]) if len(sys.argv) > 1 else 400
MODE = sys.argv[2] if len(sys.argv) > 2 else "all"
TWSE_SLEEP = float(os.environ.get("TWSE_SLEEP", "30"))
CODE = re.compile(r"^\d{4}$")

def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            time.sleep(8 * (i + 1))
    return None

def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None

def twse(d):
    f = os.path.join(RAW, f"twse_{d:%Y%m%d}.json")
    if os.path.exists(f):
        return json.load(open(f))
    j = get("https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=%s&type=ALLBUT0999&response=json" % d.strftime("%Y%m%d"))
    if j is None:
        return None                      # 被擋或連線失敗：不快取
    rows = []
    if j.get("stat") == "OK":
        for t in j.get("tables", []):
            if "證券代號" in t.get("fields", []) and "收盤價" in t["fields"]:
                for r in t["data"]:
                    if CODE.match(r[0]):
                        rows.append([r[0], r[1].strip(), num(r[5]), num(r[6]), num(r[7]), num(r[8]), num(r[2])])
    out = {"ok": j.get("stat") == "OK", "rows": rows}
    json.dump(out, open(f, "w"), ensure_ascii=False)
    time.sleep(TWSE_SLEEP)
    return out

def tpex(d):
    f = os.path.join(RAW, f"tpex_{d:%Y%m%d}.json")
    if os.path.exists(f):
        return json.load(open(f))
    j = get("https://www.tpex.org.tw/www/zh-tw/afterTrading/otc?date=%s&type=EW&response=json" % urllib.parse.quote(d.strftime("%Y/%m/%d"), safe=""))
    if j is None:
        return None
    rows, ok = [], False
    if j.get("tables"):
        t = j["tables"][0]
        ok = bool(t.get("data"))
        for r in t.get("data", []):
            if CODE.match(r[0]):
                rows.append([r[0], r[1].strip(), num(r[4]), num(r[5]), num(r[6]), num(r[2]), num(r[7])])
    out = {"ok": ok, "rows": rows}
    json.dump(out, open(f, "w"), ensure_ascii=False)
    time.sleep(0.5)
    return out

def retry(fn, d):
    for _ in range(20):
        r = fn(d)
        if r is not None:
            return r
        print("  blocked/failed", fn.__name__, d, "wait backoff", flush=True)
        time.sleep(float(os.environ.get("TWSE_BACKOFF","1800")))
    raise SystemExit(f"giving up on {d}")

today = datetime.date.today()
days = [today - datetime.timedelta(n) for n in range(0, DAYS_BACK + 1)]      # 由近到遠
days = [d for d in days if d.weekday() < 5]

def run_twse():
    for k, d in enumerate(days):
        retry(twse, d)
        if k % 10 == 0:
            print("twse", d, k, "/", len(days), flush=True)
    print("twse done", flush=True)

def run_tpex():
    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(lambda d: retry(tpex, d), days))
    print("tpex done", flush=True)

def merge():
    out, ndays = [], 0
    for d in sorted(days):
        a = os.path.join(RAW, f"twse_{d:%Y%m%d}.json")
        b = os.path.join(RAW, f"tpex_{d:%Y%m%d}.json")
        if not os.path.exists(a):
            continue                                       # 還沒抓到的舊日期
        A = json.load(open(a))
        if not A["ok"]:
            continue                                       # 休市日
        B = json.load(open(b)) if os.path.exists(b) else {"rows": []}
        ndays += 1
        for r in A["rows"]:
            out.append([d.isoformat(), r[0], r[1], "TWSE"] + r[2:])
        for r in B["rows"]:
            out.append([d.isoformat(), r[0], r[1], "TPEX"] + r[2:])
    with open(os.path.join(ROOT, "data", "prices_all.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "code", "name", "market", "open", "high", "low", "close", "volume"])
        w.writerows(out)
    print("merged rows:", len(out), "codes:", len({r[1] for r in out}), "tradingdays:", ndays, flush=True)

if MODE in ("twse", "tpex", "all"):
    th = []
    if MODE in ("tpex", "all"):
        th.append(threading.Thread(target=run_tpex)); th[-1].start()
    if MODE in ("twse", "all"):
        run_twse()
    for t in th:
        t.join()
if MODE in ("merge", "all"):
    merge()
