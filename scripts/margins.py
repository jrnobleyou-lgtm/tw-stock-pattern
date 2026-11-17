"""台股單季三率（毛利率、營業利益率、稅後淨利率）與季營收（11/17 使用者規格：消息分頁近 3 季）。

資料：FinMind TaiwanStockFinancialStatements 本來就是「單季」損益（Revenue、GrossProfit、OperatingIncome、IncomeAfterTaxes），
回補寫 data/margin_fm.json：{代號: {"2025Q3": [營收, 毛利, 營業利益, 稅後淨利]}}（單位：千元）。
季營收另由月營收加總（data/rev，revenue.py），兩邊都有時以月營收加總為準（官方、較新）。

官方最新季（累計值）另存 data/margin_cum.json（證交所 t187ap06_L_ci、櫃買 mopsfin_t187ap06_O_ci，一般業才有毛利；金融業沒有三率），
顯示時才算單季：Q1＝Q1 累計；其他季＝本季累計−前季累計（兩個都有時），否則用 FinMind 單季（和 EPS 同一套做法）。
標籤「三率三升」＝最新一季毛利率、營業利益率、稅後淨利率都比上一季高。

用法：
  python3 scripts/margins.py update       官方最新季，update.yml 每輪跑
  python3 scripts/margins.py backfill     FinMind 回補（台灣晚上 6 點以後；環境變數 MARGIN_FM 可指定暫存檔）
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import revenue as RV

ROOT = RV.ROOT
FM = os.environ.get("MARGIN_FM") or os.path.join(ROOT, "data", "margin_fm.json")
CUM = os.path.join(ROOT, "data", "margin_cum.json")
OFFICIAL = ["https://openapi.twse.com.tw/v1/opendata/t187ap06_L_ci", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci"]
TYPES = ("Revenue", "GrossProfit", "OperatingIncome", "IncomeAfterTaxes")


def _load(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def _save(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump({c: dict(sorted(v.items())) for c, v in sorted(d.items()) if v}, f, ensure_ascii=False, separators=(",", ":"))


def parse(rows):
    """FinMind 的列 → {"2025Q3": [營收, 毛利, 營業利益, 稅後淨利]}（千元，缺的是 None）。"""
    q = {}
    for r in rows:
        if r.get("type") not in TYPES:
            continue
        try:
            y, m = int(r["date"][:4]), int(r["date"][5:7])
            v = int(round(float(r["value"]) / 1000))
        except Exception:
            continue
        q.setdefault(f"{y}Q{(m - 1) // 3 + 1}", [None] * 4)[TYPES.index(r["type"])] = v
    return q


def _num(x):
    try:
        return int(round(float(str(x).replace(",", ""))))
    except Exception:
        return None


def _pick(r, *keys):
    for k in keys:
        if r.get(k) not in (None, ""):
            return r[k]
    return None


def parse_row(r):
    """官方一列 → (代號, "2026Q3", [營收, 毛利, 營業利益, 稅後淨利] 累計千元) 或 None。"""
    try:
        c = str(_pick(r, "公司代號", "SecuritiesCompanyCode")).strip()
        y, q = _pick(r, "年度", "Year"), _pick(r, "季別", "Season")
        if not c or c == "None" or y is None or q is None:
            return None
        v = [_num(_pick(r, "營業收入")), _num(_pick(r, "營業毛利（毛損）淨額", "營業毛利（毛損）")),
             _num(_pick(r, "營業利益（損失）", "營業利益（損）")), _num(_pick(r, "本期淨利（淨損）", "本期稅後淨利（淨損）"))]
        if v[0] is None:
            return None
        return c, f"{int(y) + 1911}Q{int(q)}", v
    except Exception:
        return None


def single(q, cum, fm):
    """某季單季 [營收, 毛利, 營業利益, 稅後淨利]：Q1 用累計；其他季有本季與前季累計就相減；否則 FinMind。"""
    n = int(q[-1])
    if q in cum:
        if n == 1:
            return cum[q]
        p = f"{q[:4]}Q{n - 1}"
        if p in cum:
            a, b = cum[q], cum[p]
            return [None if x is None or y is None else x - y for x, y in zip(a, b)]
    return fm.get(q)


def update():
    ok, why = RV.due("margin", r"財務報告|財報|每股盈餘|自結|損益")
    print("三率：", why)
    if not ok and "force" not in sys.argv:
        return
    d = _load(CUM)
    got = n = 0
    for url in OFFICIAL:
        rows = None
        for k in range(3):
            try:
                rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
                break
            except Exception as e:
                print("三率抓取失敗，重試", url.rsplit("/", 1)[-1], k + 1, repr(e)[:80]); time.sleep(5)
        got += rows is not None
        for r in rows or []:
            p = parse_row(r)
            if p and d.setdefault(p[0], {}).get(p[1]) != p[2]:
                d[p[0]][p[1]] = p[2]; n += 1
    _save(CUM, d)
    if got == len(OFFICIAL):
        RV.mark("margin")
    print("三率官方累計更新", n, "筆，共", len(d), "檔")


def qrev(v, q):
    """某曆季（"2026Q3"）營收＝三個月營收加總（千元）；缺任何一個月就 None。v＝{YYYY-MM: 千元}。"""
    y, n = int(q[:4]), int(q[-1])
    ms = [v.get(f"{y}-{(n - 1) * 3 + k:02d}") for k in (1, 2, 3)]
    return None if any(m is None for m in ms) else sum(ms)


def q_add(q, k):
    t = int(q[:4]) * 4 + int(q[-1]) - 1 + k
    return f"{t // 4}Q{t % 4 + 1}"


def _pct(a, b):
    return round((a / b - 1) * 100, 1) if a is not None and b and b > 0 else None


def _rate(x, rev):
    return round(x / rev * 100, 1) if x is not None and rev and rev > 0 else None


def summary(cum=None, fm=None, months=None):
    """{代號: {"q": [[季別(民國), 營收千元, 季增%, 年增%, 毛利率, 營益率, 淨利率, Δ毛利率, Δ營益率, Δ淨利率] 最新在前 3 季], "m3": bool(三率三升)}}；最新一季那列最後多一個 bool＝當季營收創歷史新高
    營收（含季增、年增）用月營收加總；三率用財報單季（兩邊最新季不一定同步，所以各自找最新 3 季）。"""
    cum = cum if cum is not None else _load(CUM)
    fm = fm if fm is not None else _load(FM)
    months = months if months is not None else RV.load_all()
    out = {}
    for c in set(cum) | set(fm) | set(months):
        cc, ff, mm = cum.get(c, {}), fm.get(c, {}), months.get(c, {})
        qs = sorted({q for q in set(cc) | set(ff) if single(q, cc, ff)}, reverse=True)
        rm = sorted({f"{k[:4]}Q{(int(k[5:7]) - 1) // 3 + 1}" for k in mm}, reverse=True)
        rm = [q for q in rm if qrev(mm, q) is not None]
        latest = max(qs[:1] + rm[:1] + [""]) if (qs or rm) else ""
        if not latest:
            continue
        rows = []
        for k in range(3):
            q = q_add(latest, -k)
            rv = qrev(mm, q)
            s = single(q, cc, ff)
            if rv is None and s:
                rv = s[0]
            if rv is None and not s:
                continue
            pq = single(q_add(q, -1), cc, ff)
            row = [f"{int(q[:4]) - 1911}Q{q[-1]}", rv, _pct(rv, qrev(mm, q_add(q, -1))), _pct(rv, qrev(mm, q_add(q, -4)))]
            cur = [_rate(s[i], s[0]) if s else None for i in (1, 2, 3)]
            prv = [_rate(pq[i], pq[0]) if pq else None for i in (1, 2, 3)]
            row += cur + [None if a is None or b is None else round(a - b, 1) for a, b in zip(cur, prv)]
            rows.append(row)
        if not rows:
            continue
        d = rows[0][7:10]
        # 11/17 使用者：當季營收創歷史新高打 🌟（只看最新一季；要有 12 個完整季度以上）
        allq = [qrev(mm, q) for q in rm]
        top = rows[0][1]
        rows[0].append(bool(len(allq) >= 12 and rm and f"{int(rows[0][0][:3]) + 1911}Q{rows[0][0][-1]}" == rm[0] and top and all(x is None or top > x for x in allq[1:])))
        out[c] = {"q": rows, "m3": all(x is not None and x > 0 for x in d)}
    return out


def backfill(start="2024-07-01"):
    d = _load(FM)
    codes = RV.tw_codes()
    todo = [c for c in codes if c not in d]
    print(f"三率回補 {len(todo)} 檔（全部 {len(codes)}）", flush=True)

    def handle(c, rows):
        d[c] = parse(rows) or {}
        _save(FM, d)                                   # 每檔都存，中斷後可續跑（沒資料的存空物件，不重抓）
    n = RV.fm_loop(todo, lambda c: f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id={c}&start_date={start}", handle)
    _save(FM, d)
    print("三率回補完成", n, "檔", flush=True)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "update":
        update()
    elif cmd == "backfill":
        backfill(*(sys.argv[2:3]))
