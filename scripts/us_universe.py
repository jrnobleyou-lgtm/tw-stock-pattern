"""美股股票池與族群：NASDAQ 公開篩選器（含 NYSE、AMEX）全部普通股 → 篩掉 1 美元以下、市值 5 千萬美元以下、
SPAC 空殼公司與基金信託，再依 NASDAQ 產業別自動對應到 34 個族群。
使用者自己的分類（data/groups_us.csv）一律優先。輸出 data/groups_us_all.csv。"""
import csv, json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = sys.argv[1] if len(sys.argv) > 1 else None
if SRC:
    rows = json.load(open(SRC))["data"]["rows"]
else:
    req = urllib.request.Request("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&download=true",
                                 headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "Accept": "application/json"})
    rows = json.loads(urllib.request.urlopen(req, timeout=120).read())["data"]["rows"]

# NASDAQ 產業別 → 族群（由上往下第一個符合的關鍵字）
RULES = [
    (r"Semiconductors", "IC設計"),
    (r"Computer Software|EDP Services|Retail: Computer Software|Advertising", "網路/軟體"),
    (r"Computer Manufacturing|Computer peripheral", "AI伺服器"),
    (r"Computer Communications|Radio And Television Broadcasting And Communications|^Telecommunications Equipment", "網通"),
    (r"Cable & Other Pay Television", "電信"),
    (r"Electronic Components|Electronics Distribution", "電子零組件"),
    (r"Aerospace|Military/Government|Ordnance", "航太國防"),
    (r"Marine Transportation", "航運/造船"),
    (r"Air Freight|Trucking|Railroads|Integrated Freight|Transportation Services|Other Transportation", "航空/運輸"),
    (r"Auto Manufacturing|Motor Vehicles|Auto Parts|Automotive Aftermarket|Retail-Auto Dealers|Auto & Home Supply", "汽車"),
    (r"Electric Utilities|Power Generation|Water Supply|Natural Gas Distribution|Electrical Products|Water Sewer Pipeline", "重電/電力"),
    (r"Oil|Gas Production|Coal|Mining|Precious Metals|Metal Mining|Other Metals|Steel|Aluminum|Chemicals|Forest Products|^Paper", "能源/原物料"),
    (r"Biotechnology|Pharmaceutical|Medical|Hospital|Health|Ophthalmic|Medicinal|Precision Instruments", "生技醫療"),
    (r"Banks|Insurance|Insurers|Finance|Investment|Savings Institutions|Diversified Financial", "金融"),
    (r"Real Estate|REIT|Building operators|Homebuilding|Engineering & Construction|Building Materials|Building Products|General Bldg", "營建/工程"),
    (r"Industrial Machinery", "機器人/自動化"),
    (r"Apparel|Clothing|Shoe|Restaurants|Hotels|Retail|Stores|Food|Beverages|Meat|Farming|Packaged|Cosmetics|Tobacco|Toys|Recreational|Amusement|Movies|Broadcasting|Publishing|Newspapers|Books|Home Furnishings|Consumer|Durable Goods|Textiles|Catalog|Garments", "消費/零售"),
]
def group_of(ind):
    for pat, g in RULES:
        if re.search(pat, ind or ""):
            return g
    return "傳產/其他"

def clean_name(n):
    n = re.sub(r"\s+(Common Stock|Ordinary Shares|Class [A-Z] (Common|Ordinary) (Stock|Shares)|American Depositary Shares?.*|Common Shares|Inc\.?\s*$)", "", n or "").strip(" ,")
    return re.sub(r"\s+(Common Stock|Ordinary Shares).*$", "", n).strip(" ,") or n

def num(x):
    try: return float(str(x).replace("$", "").replace(",", "") or 0)
    except ValueError: return 0.0

mine = {}
mp = os.path.join(ROOT, "data", "groups_us.csv")
if os.path.exists(mp):
    mine = {r["代號"]: r for r in csv.DictReader(open(mp, encoding="utf-8"))}
out, seen = [], set()
for r in rows:
    sym = r["symbol"].strip()
    if not sym or "^" in sym or "/" in sym or sym in seen:
        continue
    ind = (r.get("industry") or "").strip()
    keep = sym in mine or (num(r["lastsale"]) >= 1 and num(r["marketCap"]) >= 50e6 and ind and ind != "Blank Checks"
                           and not ind.startswith("Trusts Except"))
    if not keep:
        continue
    seen.add(sym)
    if sym in mine:
        m = mine[sym]; out.append([sym, m["名稱"], m.get("產業別") or ind, m["主族群"], "使用者"])
    else:
        out.append([sym, clean_name(r["name"]), ind, group_of(ind), "自動"])
for sym, m in mine.items():                       # 使用者清單裡 NASDAQ 沒列到的也保留
    if sym not in seen:
        out.append([sym, m["名稱"], m.get("產業別", ""), m["主族群"], "使用者"])
with open(os.path.join(ROOT, "data", "groups_us_all.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["代號", "名稱", "產業別", "主族群", "把握度"]); w.writerows(sorted(out))
import collections
print("美股股票池", len(out), "檔；其中你的分類", sum(1 for x in out if x[4] == "使用者"))
print(collections.Counter(x[3] for x in out).most_common())
