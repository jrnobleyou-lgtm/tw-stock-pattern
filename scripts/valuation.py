"""本益比／股價淨值比／殖利率（官方公開資料，收盤後每日更新）。
上市：證交所「個股日本益比、殖利率及股價淨值比」；上櫃：櫃買開放資料。
回傳 {"date": "YYYY-MM-DD", "m": {代號: [PE或None, PB或None, 殖利率或None, 財報年季]}}；全抓不到回傳 None（網頁就不顯示，不放舊數字）。
PE 為 None＝官方沒給（虧損或沒有近四季財報），顯示時再用 EPS 判斷是不是「虧損」。"""
import json, time, urllib.request, datetime

UA = {"User-Agent": "Mozilla/5.0"}


def _get(url, tries=4):
    for k in range(tries):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read())
        except Exception:
            time.sleep(2 + k * 2)
    return None


def _num(s):
    try:
        v = float(str(s).replace(",", ""))
        return v
    except Exception:
        return None


def fetch_twse(date_hint):
    """從 date_hint（YYYYMMDD）往前最多試 6 天，取第一個有資料的日期。"""
    d0 = datetime.datetime.strptime(date_hint, "%Y%m%d")
    for k in range(6):
        d = (d0 - datetime.timedelta(days=k)).strftime("%Y%m%d")
        j = _get(f"https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json&date={d}&selectType=ALL", 3)
        if j and j.get("stat") == "OK" and j.get("data"):
            m = {}
            for r in j["data"]:
                pe, pb, dy = _num(r[5]), _num(r[6]), _num(r[3])
                m[r[0]] = [pe if pe and pe > 0 else None, pb if pb and pb > 0 else None, dy if dy and dy > 0 else None, str(r[7])]
            return d, m
    return None, {}


def fetch_tpex():
    j = _get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis", 5)
    if not j:
        return None, {}
    m, d = {}, None
    for r in j:
        pe, pb, dy = _num(r.get("PriceEarningRatio")), _num(r.get("PriceBookRatio")), _num(r.get("YieldRatio"))
        d = d or r.get("Date")
        m[r["SecuritiesCompanyCode"]] = [pe if pe and pe > 0 else None, pb if pb and pb > 0 else None, dy if dy and dy > 0 else None, ""]
    if d and len(d) == 7:
        d = str(int(d[:3]) + 1911) + d[3:]
    return d, m


def fetch(date_hint):
    """date_hint＝本站最新資料日 YYYYMMDD。上市、上櫃日期不一致時，以上市為準（只收日期相同的上櫃）。"""
    d1, m1 = fetch_twse(date_hint)
    if not m1:
        return None
    d2, m2 = fetch_tpex()
    if m2 and d2 and d2 != d1:
        print(f"  上櫃 PE 日期 {d2} 與上市 {d1} 不同，上櫃略過")
        m2 = {}
    m1.update(m2)
    return {"date": f"{d1[:4]}-{d1[4:6]}-{d1[6:]}", "m": m1}
