"""ETF 專區（11/18 使用者：只做台股；主動／被動區分；不做型態判斷；不進 D.stocks／族群，1,980 檔統計不能變）。
資料：上市＝證交所 STOCK_DAY_ALL（日資料）＋ STOCK_DAY（逐檔逐月，歷史回補）；上櫃＝櫃買 daily_close_quotes ＋ tradingStock。
代號以 00 開頭＝ETF。只存日 K（未還原，v1）。
指令：
  etf.py daily      收盤後把今天的日 K 加進 data/hist_etf/YYYY-MM.csv，並更新清單 data/etf_class.csv
  etf.py backfill [N] 逐檔逐月補最近 N 個月（預設 8；每筆請求間隔 1.7 秒，可續跑，快取在 ETF_CACHE 或 data/.etf_cache）
  etf.py build      產生 site/etf.json（清單）與 site/s/<代號>.json（K 線）
"""
import csv, glob, io, json, os, re, sys, time, urllib.request, urllib.error, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "data", "hist_etf")
CLASS = os.path.join(ROOT, "data", "etf_class.csv")
OVER = os.path.join(ROOT, "data", "etf_override.csv")      # 手動覆寫：代號,主被動,分類（有填才蓋掉自動判斷）
CACHE = os.environ.get("ETF_CACHE") or os.path.join(ROOT, "data", ".etf_cache")
UA = {"User-Agent": "Mozilla/5.0"}
BARS = 400


def get(url, tries=3, raw=False):
    for k in range(tries):
        try:
            b = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
            return b if raw else json.loads(b)
        except Exception:
            time.sleep(2 + 3 * k)
    return None


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except Exception:
        return None


def roc(s):
    s = str(s).replace("/", "")
    return f"{int(s[:-4]) + 1911}-{s[-4:-2]}-{s[-2:]}"


# ───────── 分類 ─────────
CAT = [
    ("槓桿", lambda c, n: c[-1] == "L"),
    ("反向", lambda c, n: c[-1] == "R"),
    ("期貨／商品", lambda c, n: c[-1] in "UKC" or n.startswith("期")),
    ("債券", lambda c, n: c[-1] in "BD" or re.search(r"債|公債|投等|非投|美債|政府", n)),
    ("高股息", lambda c, n: re.search(r"填息|高股息|高息|股息|股利|息收|收益|入息|優息|配息|低波高息", n)),
    ("海外", lambda c, n: re.search(r"美國|日本|日經|歐洲|中國|A50|滬深|深|上証|上證|香港|恒生|印度|越南|韓|那斯達克|NASDAQ|S&P|標普|費城|道瓊|全球|新興|北美|FANG|US|亞|日|納斯達克|世界|A股|中証", n)),
    ("市值型", lambda c, n: re.search(r"台灣50|臺灣50|台50|中型100|臺灣加權|台灣加權|MSCI台灣|摩台|富櫃50|臺灣中小|台灣中小|公司治理|永續|ESG|臺灣領袖|台灣領袖", n)),
    ("主題", lambda c, n: re.search(r"科技|半導體|AI|5G|電動車|生技|金融|資安|機器人|通訊|低碳|電池|綠能|航運|基建|不動產|龍頭|ESG|網路|動能|成長|價值|增長|智能車|未來車|元宇宙|太空|衛星|IC設計|晶圓|數據|電力|稀土|基因|數位|潔淨|創新|ARK|Smart|資源", n)),
    ("台股（一般）", lambda c, n: re.search(r"台灣|臺灣|台股|50|30|優選|旗艦|精彩|新星|卓越|強棒|豐收|台精", n)),
]


def classify(code, name):
    kind = "主動" if name.startswith("主動") or name.startswith("平衡") else "被動"
    cls = next((k for k, f in CAT if f(code, name)), "其他")
    return kind, cls


def overrides():
    o = {}
    if os.path.exists(OVER):
        for r in csv.DictReader(open(OVER, encoding="utf-8")):
            o[r["代號"]] = (r.get("主被動", "").strip(), r.get("分類", "").strip())
    return o


# ───────── 抓資料 ─────────
def universe_today():
    """今天的 ETF 日 K：{代號: dict(date,name,market,o,h,l,c,v)}（v＝股數）。"""
    out = {}
    b = get("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json", raw=True)
    if b:
        rows = list(csv.reader(io.StringIO(b.decode("utf-8", "replace"))))
        for r in rows[1:]:
            if len(r) >= 9 and r[1].startswith("00"):
                o, h, l, c = (num(r[k]) for k in (5, 6, 7, 8))
                if None not in (o, h, l, c):
                    out[r[1]] = {"date": roc(r[0]), "name": r[2].strip(), "market": "TWSE", "o": o, "h": h, "l": l, "c": c, "v": int(num(r[3]) or 0)}
    j = get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
    for r in j or []:
        c0 = r["SecuritiesCompanyCode"]
        if c0.startswith("00"):
            o, h, l, c = (num(r[k]) for k in ("Open", "High", "Low", "Close"))
            if None not in (o, h, l, c):
                out[c0] = {"date": roc(r["Date"]), "name": r["CompanyName"].strip(), "market": "TPEX", "o": o, "h": h, "l": l, "c": c, "v": int(num(r["TradingShares"]) or 0)}
    return out


def read_hist():
    rows = {}
    for f in sorted(glob.glob(os.path.join(HIST, "*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            rows[(r["code"], r["date"])] = r
    return rows


def write_month(month, rows):
    os.makedirs(HIST, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["code"], r["date"]))
    with open(os.path.join(HIST, month + ".csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "code", "name", "market", "open", "high", "low", "close", "volume"])
        for r in rows:
            w.writerow([r["date"], r["code"], r["name"], r["market"], r["open"], r["high"], r["low"], r["close"], r["volume"]])


def merge_rows(newrows):
    """newrows：[{date,code,name,market,open,high,low,close,volume}]，依月份合併進 data/hist_etf（同日同代號以新的為準）。"""
    by = collections.defaultdict(dict)
    for r in newrows:
        by[r["date"][:7]][(r["code"], r["date"])] = {k: str(v) for k, v in r.items()}
    for m, d in by.items():
        p = os.path.join(HIST, m + ".csv")
        cur = {}
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding="utf-8")):
                cur[(r["code"], r["date"])] = r
        cur.update(d)
        write_month(m, list(cur.values()))


def daily():
    u = universe_today()
    if not u:
        print("ETF 今天資料抓不到，略過")
        return
    rows = [{"date": v["date"], "code": c, "name": v["name"], "market": v["market"], "open": v["o"], "high": v["h"], "low": v["l"], "close": v["c"], "volume": v["v"]} for c, v in u.items()]
    merge_rows(rows)
    print("ETF 日 K：", max(v["date"] for v in u.values()), len(u), "檔")
    write_class(u)


def write_class(u=None):
    names = {}
    for r in read_hist().values():
        names[r["code"]] = (r["name"], r["market"])
    for c, v in (u or {}).items():
        names[c] = (v["name"], v["market"])
    ov = overrides()
    with open(CLASS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["代號", "名稱", "市場", "主被動", "分類"])
        for c in sorted(names):
            n, m = names[c]
            k, cl = classify(c, n)
            if c in ov:
                k, cl = ov[c][0] or k, ov[c][1] or cl
            w.writerow([c, n, m, k, cl])


def backfill(nmonths=8):
    """逐檔逐月補歷史（TWSE STOCK_DAY／TPEX tradingStock）。已抓過的 (代號,月) 存在快取，可續跑。"""
    os.makedirs(CACHE, exist_ok=True)
    u = universe_today()
    today = datetime.date.fromisoformat(max(v["date"] for v in u.values()))
    months = []
    y, m = today.year, today.month
    for _ in range(int(nmonths)):
        months.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    months.reverse()
    todo = [(c, y, m) for (y, m) in months for c in sorted(u)]
    print("待抓", len(todo), "筆（月份", months[0], "～", months[-1], "）", flush=True)
    n = 0
    for c, y, m in todo:
        cp = os.path.join(CACHE, f"{c}_{y}{m:02d}.json")
        if os.path.exists(cp):
            continue
        mk = u[c]["market"]
        rows = []
        if mk == "TWSE":
            j = get(f"https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date={y}{m:02d}01&stockNo={c}&response=json", 2)
            if j and j.get("stat") == "OK":
                for r in j["data"]:
                    o, h, l, cl = (num(r[k]) for k in (3, 4, 5, 6))
                    if None not in (o, h, l, cl):
                        rows.append({"date": roc(r[0]), "code": c, "name": u[c]["name"], "market": mk, "open": o, "high": h, "low": l, "close": cl, "volume": int(num(r[1]) or 0)})
            elif j is None:
                time.sleep(20)
                continue                              # 被擋：先不存快取，下次續跑
        else:
            j = get(f"https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock?code={c}&date={y}/{m:02d}/01&id=&response=json", 2)
            if j is None:
                time.sleep(20)
                continue
            for t in (j.get("tables") or []):
                for r in t.get("data") or []:
                    o, h, l, cl = (num(r[k]) for k in (3, 4, 5, 6))
                    if None not in (o, h, l, cl):
                        rows.append({"date": roc(r[0]), "code": c, "name": u[c]["name"], "market": mk, "open": o, "high": h, "low": l, "close": cl, "volume": int((num(r[1]) or 0) * 1000)})
        json.dump(rows, open(cp, "w"))
        if rows:
            merge_rows(rows)
        n += 1
        if n % 100 == 0:
            print("已抓", n, "筆", c, y, m, flush=True)
        time.sleep(1.7)
    print("回補完成")
    write_class(u)


def yahoo_backfill(rng="1y"):
    """用 Yahoo chart 一檔一次補近 rng 的日 K（原始價，未還原；每檔間隔 2 秒，429 就停 3 分鐘再試）。"""
    u = universe_today()
    allrows, n = [], 0
    for c in sorted(u):
        sym = c + (".TW" if u[c]["market"] == "TWSE" else ".TWO")
        j = None
        for k in range(3):
            try:
                j = json.loads(urllib.request.urlopen(urllib.request.Request(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval=1d", headers=UA), timeout=40).read())
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(180)
                else:
                    break
            except Exception:
                time.sleep(5)
        try:
            r = j["chart"]["result"][0]
            q = r["indicators"]["quote"][0]
            for i, t in enumerate(r["timestamp"]):
                o, h, l, cl, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
                if None in (o, h, l, cl):
                    continue
                d = (datetime.datetime.fromtimestamp(t, datetime.timezone.utc) + datetime.timedelta(hours=8)).strftime("%Y-%m-%d")
                allrows.append({"date": d, "code": c, "name": u[c]["name"], "market": u[c]["market"], "open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(cl, 2), "volume": int(v or 0)})
            n += 1
        except Exception:
            pass
        if n % 50 == 0 and n:
            print("Yahoo 已補", n, "檔", flush=True)
        time.sleep(2)
    # 官方日 K（證交所／櫃買）優先：已有的 (代號,日期) 不被 Yahoo 蓋掉
    have = set(read_hist().keys())
    merge_rows([r for r in allrows if (r["code"], r["date"]) not in have])
    print("Yahoo 回補完成", n, "檔", len(allrows), "筆")
    write_class(u)


def build():
    """site/etf.json（清單）＋ site/s/<代號>.json（K 線，日期用字串）。ETF 不進 data.js。"""
    hist = collections.defaultdict(list)
    for (c, d), r in sorted(read_hist().items()):
        hist[c].append(r)
    cls = {}
    if os.path.exists(CLASS):
        for r in csv.DictReader(open(CLASS, encoding="utf-8")):
            cls[r["代號"]] = r
    os.makedirs(os.path.join(ROOT, "site", "s"), exist_ok=True)
    items, last_all = [], ""
    for c, rs in hist.items():
        rs.sort(key=lambda r: r["date"])
        last = rs[-1]
        last_all = max(last_all, last["date"])
    for c, rs in hist.items():
        last = rs[-1]
        if last["date"] < last_all[:8] + "01" and last["date"] != last_all:      # 已下市（本月沒有資料）不列
            if (datetime.date.fromisoformat(last_all) - datetime.date.fromisoformat(last["date"])).days > 20:
                continue
        info = cls.get(c)
        if not info:
            k, cl = classify(c, last["name"])
            info = {"名稱": last["name"], "市場": last["market"], "主被動": k, "分類": cl}
        cl_ = float(last["close"])
        pc = float(rs[-2]["close"]) if len(rs) > 1 and rs[-2]["date"] < last["date"] else None
        chg = round((cl_ / pc - 1) * 100, 2) if pc else 0
        vol = int(float(last["volume"]))
        items.append([c, info["名稱"], info["市場"], info["主被動"], info["分類"], cl_, chg, round(pc, 2) if pc else None, round(vol / 1000), last["date"]])
        rows = [[r["date"], float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), round(int(float(r["volume"])) / 1000), 1] for r in rs[-BARS:]]
        json.dump({"bars": rows}, open(os.path.join(ROOT, "site", "s", c + ".json"), "w"), separators=(",", ":"))
    items.sort(key=lambda x: -(x[5] * x[8]))
    json.dump({"date": last_all, "f": ["code", "name", "market", "kind", "cls", "close", "chg", "pc", "vol", "date"], "list": items}, open(os.path.join(ROOT, "site", "etf.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("etf.json", len(items), "檔；資料日", last_all)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if cmd == "daily":
        daily()
    elif cmd == "backfill":
        backfill(*(sys.argv[2:3] or [8]))
    elif cmd == "yahoo":
        yahoo_backfill(*(sys.argv[2:3] or ["1y"]))
    elif cmd == "build":
        build()
