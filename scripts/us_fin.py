"""11/18 美股季財報（營收、毛利率、營益率、淨利率、EPS）——資料來源：SEC 官方公開資料（companyfacts，免費）。
  python3 scripts/us_fin.py            → 抓全部美股，寫 data/us/fin.json（分析用）與 site/us/fn/<0-31>.json（上傳到管理者專區用，K 線視窗「消息」分頁）
美股資料不進公開的 GitHub（data/us、site/us 都不進版控）。外國公司的 ADR（只交年報）抓不到季資料，會自動略過。
請求量：每秒最多約 8 次（SEC 上限 10 次），約 4,000 檔、約 10 分鐘；單檔失敗沿用上次 KV 裡的那份。"""
import csv, datetime as dt, hashlib, json, os, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = os.environ.get("SEC_UA", "stock research swingbreakout888@gmail.com")      # SEC 規定要留名稱與聯絡信箱（用網站「聯絡我們」公開的專用信箱）
NB = 32
REV = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet"]
NI = ["NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"]
COST = ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"]

_lock, _last = threading.Lock(), [0.0]
def _throttle():
    with _lock:                                   # 全部執行緒合計每秒約 8 次
        w = _last[0] + 0.125 - time.time()
        if w > 0:
            time.sleep(w)
        _last[0] = time.time()

def get(url, tries=3):
    for i in range(tries):
        _throttle()
        r = subprocess.run(["curl", "-s", "-m", "40", "-A", UA, url], capture_output=True)
        try:
            return json.loads(r.stdout)
        except Exception:
            time.sleep(2 * (i + 1))
    return None

def shard(code, n=NB):
    h = 0
    for ch in code:
        h = (h * 31 + ord(ch)) % 1000003
    return h % n

def days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days

def pick(g, names, unit="USD"):
    rows = []
    for n in names:                               # 公司會換會計科目名稱：新舊全部合併，同一期間取最後申報的
        if n in g and unit in g[n]["units"]:
            rows += g[n]["units"][unit]
    best = {}
    for r in rows:
        k = (r.get("start"), r["end"])
        if k not in best or r.get("filed", "") >= best[k].get("filed", ""):
            best[k] = r
    return list(best.values())

def quarters(rows):
    """單季值：10-Q 的三個月期間；第四季＝全年 − 前三季。回傳 {季末日: 值}"""
    q, ann = {}, {}
    for r in rows:
        if "start" not in r:
            continue
        d = days(r["start"], r["end"])
        if 80 <= d <= 100:
            q[r["end"]] = r["val"]
        elif 350 <= d <= 380:
            ann[r["end"]] = (r["start"], r["val"])
    for e, (s, v) in ann.items():
        inyr = [x for k, x in q.items() if s < k < e]
        if len(inyr) == 3 and e not in q:
            q[e] = v - sum(inyr)
    return dict(sorted(q.items()))

def company(cik):
    d = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
    if not d:
        return None
    g = d.get("facts", {}).get("us-gaap", {})
    rev = quarters(pick(g, REV))
    if len(rev) < 2:
        return {}                                 # 沒有季資料（例如只交年報的外國公司、銀行沒有營收科目）
    gp = quarters(pick(g, ["GrossProfit"]))
    if not gp:
        cost = quarters(pick(g, COST))
        gp = {k: rev[k] - v for k, v in cost.items() if k in rev}
    op, ni = quarters(pick(g, ["OperatingIncomeLoss"])), quarters(pick(g, NI))
    eps = quarters(pick(g, ["EarningsPerShareDiluted", "EarningsPerShareBasic"], "USD/shares"))
    ks = sorted(rev)[-9:]
    if days(ks[-1], dt.date.today().isoformat()) > 400:
        return {}                                 # 資料太舊（已下市或不再申報）
    return {"d": ks, "rev": [rev[k] for k in ks], "gp": [gp.get(k) for k in ks], "op": [op.get(k) for k in ks], "ni": [ni.get(k) for k in ks], "eps": [None if eps.get(k) is None else round(eps[k], 2) for k in ks]}

def qlabel(end):
    y, m = int(end[:4]), int(end[5:7])
    return f"{y}Q{(m - 1) // 3 + 1}"

def view(c):
    """給前端的格式（和台股消息分頁同一套）：eps＝[[季別,EPS]…近 3 季]、q＝[[季別,營收（千美元）,季增%,年增%,毛利率,營益率,淨利率,Δ毛利率,Δ營益率,Δ淨利率]…近 3 季]、m3＝三率三升"""
    n = len(c["d"])
    def pct(a, b):
        return None if a is None or not b else round((a / b - 1) * 100, 1)
    def rate(x, r):
        return None if x is None or not r else round(x / r * 100, 1)
    rows = []
    for i in range(n - 1, max(n - 4, -1), -1):
        r = c["rev"][i]
        cur = [rate(c[k][i], r) for k in ("gp", "op", "ni")]
        prv = [rate(c[k][i - 1], c["rev"][i - 1]) for k in ("gp", "op", "ni")] if i >= 1 else [None] * 3
        rows.append([qlabel(c["d"][i]), round(r / 1000), pct(r, c["rev"][i - 1]) if i >= 1 else None, pct(r, c["rev"][i - 4]) if i >= 4 else None]
                    + cur + [None if a is None or b is None else round(a - b, 1) for a, b in zip(cur, prv)])
    eps = [[qlabel(c["d"][i]), c["eps"][i]] for i in range(n - 1, max(n - 4, -1), -1) if c["eps"][i] is not None]
    last = rows[0] if rows else None
    m3 = bool(last and all(x is not None and x > 0 for x in last[7:10]))
    return {"eps": eps, "q": rows, **({"m3": 1} if m3 else {})}

def main():
    codes = [r["代號"] for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_us_all.csv"), encoding="utf-8"))]
    cik = {v["ticker"].upper(): v["cik_str"] for v in (get("https://www.sec.gov/files/company_tickers.json") or {}).values()}
    if not cik:
        sys.exit("讀不到 SEC 公司對照表")
    todo = {c: cik[c.replace(".", "-").replace("/", "-").upper()] for c in codes if c.replace(".", "-").replace("/", "-").upper() in cik}
    if os.environ.get("US_FIN_LIMIT"):
        todo = dict(list(todo.items())[:int(os.environ["US_FIN_LIMIT"])])
    print("美股", len(codes), "檔，有 SEC 編號", len(todo))
    out, fail = {}, []
    def one(item):
        c, k = item
        try:
            r = company(k)
        except Exception:
            r = None
        return c, r
    with ThreadPoolExecutor(6) as ex:
        for c, r in ex.map(one, todo.items()):
            if r is None:
                fail.append(c)
            elif r:
                out[c] = r
    print("有季資料", len(out), "檔；抓取失敗", len(fail))
    if len(fail) > max(20, len(todo) * 0.1):       # SEC 當機或擋我們：不要用殘缺的資料蓋掉上次的
        sys.exit("失敗太多，這次不更新（沿用上次）")
    os.makedirs(os.path.join(ROOT, "data", "us"), exist_ok=True)
    json.dump(out, open(os.path.join(ROOT, "data", "us", "fin.json"), "w"), separators=(",", ":"))
    sys.path.insert(0, os.path.dirname(__file__))
    fd = os.path.join(ROOT, "site", "us", "fn")
    os.makedirs(fd, exist_ok=True)
    bk = [dict() for _ in range(NB)]
    for c, r in out.items():
        bk[shard(c)][c] = view(r)
    n = 0
    for k in range(NB):
        open(os.path.join(fd, f"{k}.json"), "w", encoding="utf-8").write(json.dumps(bk[k], ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        n += len(bk[k])
    print("寫出", NB, "包，共", n, "檔")

if __name__ == "__main__":
    main()
