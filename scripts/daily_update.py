"""每日更新（給 GitHub Actions 或手動執行）：
  1) 證交所 OpenAPI（隔天早上才有前一交易日）＋ 櫃買 OpenAPI（當天下午 3 點後）抓最新一天，附加到 data/hist/YYYY-MM.csv（已有的日期不重複）
  2) 櫃買資料含「次日參考價」→ 算出除權息調整係數 k，記到 data/pending_ex.csv，隔天寫入 data/adjust.csv
  3) 更新大盤指數（增量）
只用標準函式庫。任何一步失敗都只印出警告、不中斷，下一個排程時段會再試。
"""
import csv, glob, json, os, sys, datetime, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(ROOT, "data", "hist"); os.makedirs(H, exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0"}

def get(url, tries=3):
    import time
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("  取得失敗", url.split("/")[-1], repr(e)[:80]); time.sleep(5 * (i + 1))
    return None

def roc(s):                      # 1151110 -> 2026-11-10
    s = str(s).strip()
    return f"{int(s[:-4]) + 1911}-{s[-4:-2]}-{s[-2:]}"

def num(x):
    try:
        v = float(str(x).replace(",", "").strip())
        return v if v > 0 else None
    except ValueError:
        return None

# ── 現有歷史：每個市場最後一天、每檔最後收盤
last_date = {"TWSE": "", "TPEX": ""}
last_close = {}
files = sorted(glob.glob(os.path.join(H, "*.csv")))
for f in files[-2:]:
    for r in csv.DictReader(open(f, encoding="utf-8")):
        last_date[r["market"]] = max(last_date[r["market"]], r["date"])
        last_close[r["code"]] = (r["date"], float(r["close"]))
print("目前資料日：", last_date)

new_rows = []
# ── 上市（證交所 OpenAPI）
j = get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL")
if j:
    d = roc(j[0]["Date"])
    if d > last_date["TWSE"]:
        for r in j:
            c = r["Code"]
            o, h, l, cl = (num(r[k]) for k in ("OpeningPrice", "HighestPrice", "LowestPrice", "ClosingPrice"))
            if len(c) == 4 and c.isdigit() and None not in (o, h, l, cl):
                new_rows.append([d, c, "TWSE", o, h, l, cl, int(num(r["TradeVolume"]) or 0)])
        print("上市新資料日", d, sum(1 for r in new_rows if r[2] == "TWSE"), "檔")
    else:
        print("上市沒有更新的資料（OpenAPI 日期", d, "）")
# ── 上櫃（櫃買 OpenAPI）
pending_new = []
j = get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes")
if j:
    d = roc(j[0]["Date"])
    append = d > last_date["TPEX"]
    for r in j:
        c = r["SecuritiesCompanyCode"]
        o, h, l, cl = (num(r[k]) for k in ("Open", "High", "Low", "Close"))
        if len(c) == 4 and c.isdigit() and None not in (o, h, l, cl):
            if append:
                new_rows.append([d, c, "TPEX", o, h, l, cl, int(num(r["TradingShares"]) or 0)])
            nr = num(r.get("NextReferencePrice"))
            if d >= last_date["TPEX"] and nr and abs(nr / cl - 1) > 4e-4:   # 次日除權息：參考價 ≠ 今日收盤
                pending_new.append([c, d, round(nr / cl, 6)])
    print("上櫃資料日", d, "（新增）" if append else "（沒有更新）", "；次日除權息", len(pending_new), "檔")

# ── 寫入歷史月檔
by_month = {}
for r in new_rows:
    by_month.setdefault(r[0][:7], []).append(r)
for m, rows in by_month.items():
    p = os.path.join(H, m + ".csv"); exists = os.path.exists(p)
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["date", "code", "market", "open", "high", "low", "close", "volume"])
        w.writerows(sorted(rows, key=lambda x: (x[0], x[1])))

# ── 除權息調整：昨天登記的「次日除權息」→ 今天就是除權息日，正式寫入 adjust.csv
pp = os.path.join(ROOT, "data", "pending_ex.csv"); ap = os.path.join(ROOT, "data", "adjust.csv")
pend = [r for r in csv.reader(open(pp, encoding="utf-8"))][1:] if os.path.exists(pp) else []
new_dates = {r[0] for r in new_rows if r[2] == "TPEX"}
if new_dates:
    nd = min(new_dates)
    todo = [r for r in pend if r[1] < nd]
    if todo:
        with open(ap, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            for code, after, k in todo:
                w.writerow([code, nd, k])
        print("寫入除權息調整", len(todo), "筆（除權息日", nd, "）")
    pend = [r for r in pend if r[1] >= nd]
have = {(r[0], r[1]) for r in pend}
pend += [r for r in pending_new if (r[0], r[1]) not in have]
with open(pp, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["code", "after_date", "k"]); w.writerows(pend)

# ── 大盤指數（增量）
os.system(f'{sys.executable} {os.path.join(ROOT, "scripts", "fetch_index.py")}')
os.system(f'{sys.executable} {os.path.join(ROOT, "scripts", "fetch_turnover.py")}')
os.system(f'{sys.executable} {os.path.join(ROOT, "scripts", "fetch_tx.py")}')
print("完成：新增", len(new_rows), "列")
