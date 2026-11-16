"""台股單季 EPS（11/16 使用者規格：消息分頁顯示近 3 季）。

兩個檔分開存（Fable 審查 11/16：避免缺前季就永遠算不出、公司更正、和 Actions 每輪更新衝突）：
  data/eps_cum.json  官方「累計」EPS 原值 {代號: {"2026Q3": 0.63}}（證交所 t187ap14_L＋分業別 t187ap06_L_*、櫃買 mopsfin_t187ap06_O_*），每天覆蓋
  data/eps_fm.json   FinMind 單季 EPS（TaiwanStockFinancialStatements）回補，只在本機回補時寫
顯示時才算單季：Q1＝Q1 累計；其他季＝本季累計−前季累計（兩個都有時），否則用 FinMind 單季。
固定檢查：台泥 1101 115 年 Q3 累計 0.63、Q2 累計 0.39 → 單季 0.24（scripts/tests/test_fin.py）。

用法：
  python3 scripts/eps.py update      官方最新季，update.yml 每輪跑
  python3 scripts/eps.py backfill    FinMind 回補約 3 年
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import revenue as RV

ROOT = RV.ROOT
CUM = os.path.join(ROOT, "data", "eps_cum.json")
FM = os.path.join(ROOT, "data", "eps_fm.json")
_T = "https://openapi.twse.com.tw/v1/opendata/"
_O = "https://www.tpex.org.tw/openapi/v1/"
OFFICIAL = [_T + "t187ap14_L"] + [_T + "t187ap06_L_" + k for k in ("ci", "basi", "bd", "ins", "mim", "fh")] + \
           [_O + "mopsfin_t187ap06_O_" + k for k in ("ci", "basi", "bd", "ins", "mim", "fh")]


def _load(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def _save(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump({c: dict(sorted(v.items())) for c, v in sorted(d.items()) if v}, f, ensure_ascii=False, separators=(",", ":"))


def _pick(r, *keys):
    for k in keys:
        if r.get(k) not in (None, ""):
            return r[k]
    return None


def parse_row(r):
    """官方一列 → (代號, "2026Q3", 累計EPS) 或 None。上市／上櫃欄位名中英文都認。"""
    try:
        c = str(_pick(r, "公司代號", "SecuritiesCompanyCode")).strip()
        y, s = _pick(r, "年度", "Year"), _pick(r, "季別", "Season")
        e = _pick(r, "基本每股盈餘(元)", "基本每股盈餘（元）")
        if not c or c == "None" or y is None or s is None or e is None:
            return None
        return c, f"{int(y) + 1911}Q{int(s)}", float(str(e).replace(",", ""))
    except Exception:
        return None


def single(q, cum, fm):
    """某季單季：Q1 用累計；其他季有本季與前季累計就相減；否則 FinMind。"""
    n = int(q[-1])
    if q in cum:
        if n == 1:
            return round(cum[q], 2)
        p = f"{q[:4]}Q{n - 1}"
        if p in cum:
            return round(cum[q] - cum[p], 2)
    return fm.get(q)


def update():
    ok, why = RV.due("eps", r"財務報告|財報|每股盈餘|自結|損益")
    print("EPS：", why)
    if not ok and "force" not in sys.argv:
        return
    d = _load(CUM)
    got = 0
    n = 0
    for url in OFFICIAL:
        rows = None
        for k in range(3):
            try:
                rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
                break
            except Exception as e:
                print("EPS 抓取失敗，重試", url.rsplit("/", 1)[-1], k + 1, repr(e)[:80]); time.sleep(5)
        got += rows is not None
        for r in rows or []:
            p = parse_row(r)
            if not p:
                continue
            c, q, v = p
            if d.setdefault(c, {}).get(q) != v:
                d[c][q] = v; n += 1
    _save(CUM, d)
    if got == len(OFFICIAL):
        RV.mark("eps")
    print("EPS 官方累計更新", n, "筆，共", len(d), "檔")


def backfill(start="2023-01-01"):
    d = _load(FM)
    codes = RV.tw_codes()
    todo = [c for c in codes if len(d.get(c, {})) < 8]
    print(f"EPS 回補 {len(todo)} 檔（全部 {len(codes)}）", flush=True)

    def handle(c, rows):
        have = d.setdefault(c, {})
        for r in rows:
            if r.get("type") != "EPS":
                continue
            try:
                y, m = int(r["date"][:4]), int(r["date"][5:7])
                have[f"{y}Q{(m - 1) // 3 + 1}"] = round(float(r["value"]), 2)
            except Exception:
                pass
        _save(FM, d)                                   # 每檔都存，中斷後可續跑
    n = RV.fm_loop(todo, lambda c: f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id={c}&start_date={start}", handle)
    _save(FM, d)
    print("EPS 回補完成", n, "檔", flush=True)


def summary(cum=None, fm=None):
    """{代號: [["115Q3", 0.24], ...] 最新在前 3 季（季別用民國年）}"""
    cum = cum if cum is not None else _load(CUM)
    fm = fm if fm is not None else _load(FM)
    out = {}
    for c in set(cum) | set(fm):
        cc, ff = cum.get(c, {}), fm.get(c, {})
        rows = []
        for q in sorted(set(cc) | set(ff), reverse=True):
            v = single(q, cc, ff)
            if v is not None:
                rows.append([f"{int(q[:4]) - 1911}Q{q[-1]}", v])
            if len(rows) == 3:
                break
        if rows:
            out[c] = rows
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "update":
        update()
    elif cmd == "backfill":
        backfill(*(sys.argv[2:3]))
