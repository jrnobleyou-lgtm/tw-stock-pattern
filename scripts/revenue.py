"""台股月營收（11/16 使用者規格）。
資料存 data/rev/<YYYY-MM>.json：{代號: 營收（千元）}，一個月一個檔（公開資料，進版控）。

用法：
  python3 scripts/revenue.py update      抓官方最新月（證交所 t187ap05_L、櫃買 mopsfin_t187ap05_O），update.yml 每輪跑
  python3 scripts/revenue.py backfill    用 FinMind 回補 10 年（每檔一次請求，台灣 18:00 後才跑：使用者白天自己的程式要用 FinMind）
analyze.py 用 summary() 產生標籤與 site/f/<代號>.json。

標籤（使用者選定）：
  月營收創新高＝最新月營收比前 11 個月都高（要有 13 個月以上資料）
  年增新高    ＝最新月營收創歷史新高（比資料裡之前每個月都高）且年增 > 0（要有 36 個月以上資料）
只標「這檔最新公布的那個月」，而且那個月必須是全市場最新月或前一個月（還沒公布新月份的公司保留上個月的標籤）。
"""
import json, os, sys, time, glob, collections, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "data", "rev")
OFFICIAL = ["https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
            "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"]


def ym_add(ym, k):
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def roc_ym(s):                                     # "11510" → "2026-10"
    s = str(s).strip()
    return f"{int(s[:-2]) + 1911:04d}-{int(s[-2:]):02d}"


def load_all():
    """{代號: {YYYY-MM: 千元}}"""
    out = collections.defaultdict(dict)
    for p in sorted(glob.glob(os.path.join(DIR, "*.json"))):
        ym = os.path.basename(p)[:7]
        for c, v in json.load(open(p, encoding="utf-8")).items():
            out[c][ym] = v
    return out


def save_month(ym, upd, overwrite=True):
    """把 {代號: 千元} 併進該月檔；overwrite=False 時只補沒有的（官方「上月／去年同月」欄位只拿來補洞）。"""
    os.makedirs(DIR, exist_ok=True)
    p = os.path.join(DIR, ym + ".json")
    cur = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}
    n = 0
    for c, v in upd.items():
        if v is None or v < 0:
            continue
        if overwrite or c not in cur:
            if cur.get(c) != v:
                cur[c] = v; n += 1
    if n:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dict(sorted(cur.items())), f, ensure_ascii=False, separators=(",", ":"))
    return n


def _num(x):
    try:
        return int(round(float(str(x).replace(",", ""))))
    except Exception:
        return None


META = os.path.join(ROOT, "data", "fin_meta.json")
MOPS_URL = "https://raw.githubusercontent.com/jrnobleyou-lgtm/tw-stock-pattern/news-data/mops.json"


def _now_tw():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) + datetime.timedelta(hours=8)


def mops_hit(pattern, since):
    """近期重訊主旨有沒有符合 pattern（發言時間 ≥ since，epoch）；讀 news-data 分支的 mops.json，讀不到當沒有。"""
    import re
    try:
        rows = json.loads(urllib.request.urlopen(MOPS_URL, timeout=20).read())
        return any(r.get("t", 0) >= since and re.search(pattern, r.get("s", "")) for r in rows)
    except Exception:
        return False


def due(kind, pattern):
    """11/16 使用者：月營收 每月 1～12 號每天下午（13:00 後）抓一次；其他時間每週一次（週日那輪，或距上次 ≥7 天）；
    EPS 每週一次；兩者另外在有相關重訊（主旨符合 pattern）時立刻抓。回傳 (要不要抓, 原因)。"""
    now = _now_tw()
    today = now.strftime("%Y-%m-%d")
    meta = json.load(open(META)) if os.path.exists(META) else {}
    last = meta.get(kind, "")
    if last == today:
        return False, "今天抓過"
    if kind == "rev" and now.day <= 12 and now.hour >= 13:
        return True, "每月 1～12 號下午"
    if now.weekday() == 6:
        return True, "每週日"
    if not last or (now - __import__("datetime").datetime.strptime(last, "%Y-%m-%d")).days >= 7:
        return True, "距上次 ≥7 天"
    if mops_hit(pattern, int(time.mktime(time.strptime(last, "%Y-%m-%d"))) - 8 * 3600):
        return True, "有相關重訊"
    return False, "還不用抓"


def mark(kind):
    meta = json.load(open(META)) if os.path.exists(META) else {}
    meta[kind] = _now_tw().strftime("%Y-%m-%d")
    with open(META, "w") as f:
        json.dump(meta, f)


def update():
    ok, why = due("rev", r"營收|營業收入")
    print("月營收：", why)
    if not ok and "force" not in sys.argv:
        return
    got = 0
    """官方最新月（含上月、去年同月補洞）。失敗就沿用舊資料。"""
    for u in OFFICIAL:
        rows = None
        for k in range(3):
            try:
                rows = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
                break
            except Exception as e:
                print("月營收抓取失敗，重試", k + 1, repr(e)[:80]); time.sleep(5)
        if not rows:
            continue
        cur, prev, ly = collections.defaultdict(dict), collections.defaultdict(dict), collections.defaultdict(dict)
        for r in rows:
            c = str(r.get("公司代號", "")).strip()
            try:
                ym = roc_ym(r["資料年月"])
            except Exception:
                continue
            cur[ym][c] = _num(r.get("營業收入-當月營收"))
            prev[ym_add(ym, -1)][c] = _num(r.get("營業收入-上月營收"))
            ly[ym_add(ym, -12)][c] = _num(r.get("營業收入-去年當月營收"))
        got += 1
        for ym, d in cur.items():
            print(u.rsplit("/", 1)[-1], ym, len(d), "檔，更新", save_month(ym, d))
        for ym, d in prev.items():                 # 上月營收：官方更正要蓋過去（Fable 11/16）
            save_month(ym, d)
        for ym, d in ly.items():                   # 去年同月只補洞
            save_month(ym, d, overwrite=False)
    if got == len(OFFICIAL):
        mark("rev")


def fm_loop(todo, url_of, handle):
    """FinMind 逐檔請求共用節流（同 fetch_finmind.py）：每次間隔 ≥ MIN_GAP 秒、滾動 60 分 ≤ HOURLY_CAP 次；
    任何 4xx 不重試、連續 3 次 4xx 整個中止；402 停到下個整點、403 停 35 分。Token 由系統代理自動帶上。"""
    gap, cap = float(os.environ.get("MIN_GAP", "8")), int(os.environ.get("HOURLY_CAP", "420"))
    stamps, last, bad, done = collections.deque(), 0.0, 0, 0
    for i, c in enumerate(todo):
        now = time.time()
        while stamps and now - stamps[0] > 3600:
            stamps.popleft()
        if len(stamps) >= cap:
            w = 3600 - (now - stamps[0]) + 5
            print(f"  已達每小時 {cap} 次，等 {w/60:.1f} 分", flush=True); time.sleep(max(w, 1))
        g = gap - (time.time() - last)
        if g > 0:
            time.sleep(g)
        last = time.time(); stamps.append(last)
        d = None
        for k in range(3):
            try:
                d = json.loads(urllib.request.urlopen(url_of(c), timeout=60).read()); break
            except urllib.error.HTTPError as e:
                print(" ", c, "HTTP", e.code, flush=True)
                if e.code == 402:
                    print("  超過額度，停到下個整點後", flush=True); time.sleep(3600 - time.time() % 3600 + 60)
                elif e.code == 403:
                    print("  被封鎖，停 35 分", flush=True); time.sleep(2100)
                bad += 1
                break
            except Exception as e:
                print(" ", c, "連線錯誤", repr(e)[:60], flush=True); time.sleep(10 * (k + 1))
        if bad >= 3:
            print("連續 3 次 4xx，中止", flush=True); break
        if not d or d.get("status") != 200:
            continue
        bad = 0
        handle(c, d.get("data", []))
        done += 1
        if i % 50 == 0:
            print(f"  {i+1}/{len(todo)} {c}", flush=True)
    return done


def tw_codes():
    import csv
    return [r["代號"] for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8"))]


def backfill(start="2015-01-01"):
    """FinMind 每檔一次（TaiwanStockMonthRevenue）。已經有 ≥ 120 個月資料的股票略過（可中斷後重跑）。"""
    have = load_all()
    codes = tw_codes()
    todo = [c for c in codes if len(have.get(c, {})) < 120]
    print(f"月營收回補 {len(todo)} 檔（全部 {len(codes)}）", flush=True)

    def handle(c, rows):
        bym = collections.defaultdict(dict)
        for r in rows:
            try:
                bym[f"{int(r['revenue_year']):04d}-{int(r['revenue_month']):02d}"][c] = int(round(r["revenue"] / 1000))
            except Exception:
                pass
        for ym, v in bym.items():
            save_month(ym, v, overwrite=False)       # 官方資料優先，FinMind 只補洞
    n = fm_loop(todo, lambda c: f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id={c}&start_date={start}", handle)
    print("月營收回補完成", n, "檔", flush=True)


def summary(data=None):
    """{代號: {"rev": [[YYYY-MM, 千元, 年增%|None] 最新在前 6 筆], "revHi": bool, "yoyHi": bool}}"""
    data = data if data is not None else load_all()
    if not data:
        return {}
    latest = collections.Counter(max(v) for v in data.values() if v)
    # 全市場最新月：至少 100 家公布的最新月份（月初只有少數公司先公布時，不會誤判）
    top = max([ym for ym, n in latest.items() if n >= 100] or [max(latest)])
    ok_from = ym_add(top, -1)                     # 這檔最新月 ≥ 全市場最新月的前一月就標（月初先公布新月份的公司也算）
    out = {}
    for c, v in data.items():
        if not v:
            continue
        last = max(v)
        rows = []
        for k in range(6):
            ym = ym_add(last, -k)
            if ym not in v:
                continue
            ly = v.get(ym_add(ym, -12))
            yoy = round((v[ym] / ly - 1) * 100, 1) if ly else None
            rows.append([ym, v[ym], yoy])
        r = {"rev": rows, "revHi": False, "yoyHi": False}
        if last >= ok_from:
            cur = v[last]
            prev11 = [v[m] for m in (ym_add(last, -k) for k in range(1, 12)) if m in v]
            if len(v) >= 13 and len(prev11) >= 11 and cur > 0 and cur > max(prev11):
                r["revHi"] = True
            before = [x for m, x in v.items() if m < last]
            ly = v.get(ym_add(last, -12))
            if len(v) >= 36 and cur > 0 and before and cur > max(before) and ly and cur > ly:
                r["yoyHi"] = True
        out[c] = r
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "update":
        update()
    elif cmd == "backfill":
        backfill(*(sys.argv[2:3]))
    elif cmd == "summary":
        s = summary()
        print(len(s), "檔；月營收創新高", sum(x["revHi"] for x in s.values()), "；年增新高", sum(x["yoyHi"] for x in s.values()))
