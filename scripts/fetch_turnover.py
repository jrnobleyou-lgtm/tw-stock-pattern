"""把大盤的「成交值（億元）」寫進 data/index_TWII.json / index_OTC.json 的第 6 欄（原本是 0）。
  加權：證交所「每日市場成交資訊」FMTQIK（逐月查詢，官方值）。
  櫃買：櫃買中心 OpenAPI tpex_daily_trading_index（只有當月，官方值）；更早的月份沒有官方歷史來源，
        用 data/hist 各股「收盤價×成交股數」加總再乘 1.033（與官方比對的平均比例）估算，圖上只當趨勢參考。
用法：fetch_turnover.py          （近 2 個月，每日更新用）
      fetch_turnover.py --full   （近 26 個月，第一次補齊用）"""
import csv, collections, datetime, glob, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FULL = "--full" in sys.argv
UA = {"User-Agent": "Mozilla/5.0"}

def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("  失敗", url[-40:], repr(e)[:60]); time.sleep(4 * (i + 1))
    return None

today = datetime.date.today()
months, m = [], today.replace(day=1)
for _ in range(26 if FULL else 2):
    months.append(m); m = (m - datetime.timedelta(days=1)).replace(day=1)

twse = {}
for m in sorted(months):
    j = get("https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=%s&response=json" % m.strftime("%Y%m01"))
    for r in (j or {}).get("data", []):
        y, mo, d = r[0].split("/")
        twse[f"{int(y)+1911}-{mo}-{d}"] = round(float(r[2].replace(",", "")) / 1e8, 1)
    time.sleep(3)
print("加權成交值", len(twse), "天")

otc_official = {}
for r in get("https://www.tpex.org.tw/openapi/v1/tpex_daily_trading_index") or []:
    d = r["Date"]; otc_official[f"{int(d[:3])+1911}-{d[3:5]}-{d[5:]}"] = round(float(r["TradeAmount"]) / 1e8, 1)
print("櫃買官方成交值", len(otc_official), "天")

est = collections.defaultdict(float)
for f in glob.glob(os.path.join(ROOT, "data", "hist", "*.csv")):
    for r in csv.DictReader(open(f, encoding="utf-8")):
        if r["market"] == "TPEX":
            est[r["date"]] += float(r["close"]) * float(r["volume"])

def apply(name, official, estimate=None):
    p = os.path.join(ROOT, "data", name)
    rows = json.load(open(p)); n = 0
    for r in rows:
        v = official.get(r[0])
        if v is None and estimate and r[0] in estimate and not r[5]:
            v = round(estimate[r[0]] * 1.033 / 1e8, 1)           # 只補還沒有數字的舊資料
        if v is not None and r[5] != v:
            r[5] = v; n += 1
    json.dump(rows, open(p, "w")); print(name, "更新", n, "列；最後", rows[-1])

apply("index_TWII.json", twse)
apply("index_OTC.json", otc_official, est)
