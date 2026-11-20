"""專業資金期貨部位（11/20 使用者要求「追蹤美國對沖基金多空」，Opus 顧問建議改叫這個名字）。
資料：美國期貨交易委員會（CFTC）金融期貨持倉週報（TFF）的「槓桿基金」＝主要是對沖基金與趨勢型基金。
  標普 500、那斯達克 100 用「合併」版（大小合約加總）；VIX 期貨單獨一個。免費、不用金鑰、每週五公布（資料日是週二）。
輸出 data/funds.json、site/funds.json、site/us/funds.json（內容相同）：{"asof":"YYYY-MM-DD","fetched":"…","series":{key:{"name","rows":[[日期,多單,空單,未平倉],…]}}}
失敗（連不上、格式變了）就不覆蓋舊檔（舊檔仍會複製到 site／site/us，避免盤中循環把它弄丟）、結束代碼 0（不影響美股主流程）。"""
import json, os, subprocess, sys, time, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTS = [os.path.join(ROOT, "data", "funds.json"), os.path.join(ROOT, "site", "funds.json"), os.path.join(ROOT, "site", "us", "funds.json")]   # data＝進版控（台股頁與盤中循環用）、site＝台股頁、site/us＝美股管理者專區（上傳 KV）
API = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
SERIES = (("sp", "標普 500 期貨", "13874+"), ("nq", "那斯達克 100 期貨", "20974+"), ("vix", "VIX 波動率期貨", "1170E1"))
START = "2020-01-01"


def fetch(code):
    q = {"$select": "report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all",
         "$where": f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd>='{START}'",
         "$order": "report_date_as_yyyy_mm_dd", "$limit": "2000"}
    url = API + "?" + urllib.parse.urlencode(q)
    r = subprocess.run(["curl", "-sS", "-m", "40", "-A", "Mozilla/5.0", url], capture_output=True, check=True)
    return json.loads(r.stdout)


def rows_of(d):
    out = []
    for x in d:
        try:
            out.append([x["report_date_as_yyyy_mm_dd"][:10], int(float(x["lev_money_positions_long"])), int(float(x["lev_money_positions_short"])), int(float(x["open_interest_all"]))])
        except (KeyError, ValueError):
            continue
    return out


def write(obj):
    for p in OUTS:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main():
    today = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 8 * 3600))
    try:                                              # 今天已經抓過就不重抓，只把檔案複製到各處（一天跑很多輪也只打一次 CFTC）
        old = json.load(open(OUTS[0], encoding="utf-8"))
        if old.get("fetched") == today:
            write(old)
            print("專業資金期貨部位：今天已抓過，沿用")
            return
    except (OSError, ValueError):
        pass
    series = {}
    for key, name, code in SERIES:
        rows = rows_of(fetch(code))
        if len(rows) < 100:
            raise ValueError(f"{key} 只有 {len(rows)} 週，格式可能改了")
        series[key] = {"name": name, "rows": rows}
    asof = max(s["rows"][-1][0] for s in series.values())
    write({"asof": asof, "fetched": today, "series": series})
    print("專業資金期貨部位：資料日", asof, {k: len(v["rows"]) for k, v in series.items()})


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("專業資金期貨部位抓取失敗（保留舊檔）：", repr(e)[:200], file=sys.stderr)
        try:
            write(json.load(open(OUTS[0], encoding="utf-8")))
        except (OSError, ValueError):
            pass
