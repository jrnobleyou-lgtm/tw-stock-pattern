"""台股單季 EPS（11/16 使用者規格：消息分頁顯示近 3 季）。
資料存 data/eps.json：{代號: {"2026Q3": 0.24, ...}}（單季，公開資料，進版控）。

官方開放資料給的是「累計」EPS（證交所 t187ap14_L、櫃買 mopsfin_t187ap06_O_ci），
單季＝本季累計 −（同年前幾季單季加總）；前幾季不齊就不算。
固定檢查：台泥 1101 115 年 Q3 累計 0.63 ＝ 0.10 + 0.29 + 0.24 → 單季 0.24（scripts/tests/test_fin.py）。

用法：
  python3 scripts/eps.py update      官方最新季，update.yml 每輪跑
  python3 scripts/eps.py backfill    FinMind（TaiwanStockFinancialStatements 的 EPS，本來就是單季）回補約 3 年，台灣 18:00 後才跑
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import revenue as RV

ROOT = RV.ROOT
PATH = os.path.join(ROOT, "data", "eps.json")
OFFICIAL = [("https://openapi.twse.com.tw/v1/opendata/t187ap14_L", "公司代號", "年度", "季別", "基本每股盈餘(元)"),
            ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap06_O_ci", "SecuritiesCompanyCode", "Year", "Season", "基本每股盈餘（元）")]


def load():
    return json.load(open(PATH, encoding="utf-8")) if os.path.exists(PATH) else {}


def save(d):
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump({c: dict(sorted(v.items())) for c, v in sorted(d.items())}, f, ensure_ascii=False, separators=(",", ":"))


def single_from_cum(q, cum, have):
    """q＝'2026Q3'，cum＝本季累計；have＝{季: 單季}。回傳單季或 None（前幾季不齊）。"""
    y, n = q[:4], int(q[-1])
    prev = [have.get(f"{y}Q{k}") for k in range(1, n)]
    if any(p is None for p in prev):
        return None
    return round(cum - sum(prev), 2)


def update():
    d = load()
    n = 0
    for url, kc, ky, ks, ke in OFFICIAL:
        rows = None
        for k in range(3):
            try:
                rows = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read())
                break
            except Exception as e:
                print("EPS 抓取失敗，重試", k + 1, repr(e)[:80]); time.sleep(5)
        for r in rows or []:
            try:
                c = str(r[kc]).strip()
                q = f"{int(r[ky]) + 1911}Q{int(r[ks])}"
                cum = float(str(r[ke]).replace(",", ""))
            except Exception:
                continue
            have = d.setdefault(c, {})
            v = single_from_cum(q, cum, have)
            if v is not None and have.get(q) != v:
                have[q] = v; n += 1
    save(d)
    print("EPS 官方更新", n, "筆")


def backfill(start="2023-01-01"):
    d = load()
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
                q = f"{y}Q{(m - 1) // 3 + 1}"
                have.setdefault(q, round(float(r["value"]), 2))     # 官方資料優先，FinMind 只補洞
            except Exception:
                pass
        save(d)                                                     # 每檔都存，中斷後可續跑
    n = RV.fm_loop(todo, lambda c: f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id={c}&start_date={start}", handle)
    save(d)
    print("EPS 回補完成", n, "檔", flush=True)


def summary(d=None):
    """{代號: [["115Q3", 0.24], ...] 最新在前 3 季（季別用民國年）}"""
    d = d if d is not None else load()
    out = {}
    for c, v in d.items():
        qs = sorted(v, reverse=True)[:3]
        if qs:
            out[c] = [[f"{int(q[:4]) - 1911}Q{q[-1]}", v[q]] for q in qs]
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "update"
    if cmd == "update":
        update()
    elif cmd == "backfill":
        backfill(*(sys.argv[2:3]))
