"""市場情緒（11/21 使用者要求：VIX 波動率情緒＋CNN 恐懼貪婪指數，放在「專業機構多空比」頁下面）。
資料：
  - VIX、VIX3M（三個月期）、SKEW：Yahoo 日資料近 3 年（跟網站其他 Yahoo 資料同一個來源）。
  - CNN 恐懼貪婪指數：production.dataviz.cnn.io 的非官方介面（總分＋ 7 項子指標）。這個介面隨時可能改版或擋人，
    抓不到或格式不對就沿用上次的、完全沒有就設 null，頁面只顯示 VIX，不能讓整頁壞掉。
輸出 data/sentiment.json、site/sentiment.json、site/us/sentiment.json（內容相同）：
  {"asof","fetched","t","vix":[[日期,收盤]…],"vix3m":[…],"skew":[…],"cnn":{"score","rating","prev":{…},"hist":[[日期,分數]…],"sub":{key:{"score","rating"}}}|null}
2 小時內抓過就只複製檔案（update.yml 一天跑很多輪）。失敗不覆蓋舊檔、結束代碼 0。"""
import datetime, json, os, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTS = [os.path.join(ROOT, "data", "sentiment.json"), os.path.join(ROOT, "site", "sentiment.json"), os.path.join(ROOT, "site", "us", "sentiment.json")]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
SUBS = ("market_momentum_sp500", "stock_price_strength", "stock_price_breadth", "put_call_options", "market_volatility_vix", "junk_bond_demand", "safe_haven_demand")


def curl(url, extra=()):
    r = subprocess.run(["curl", "-sS", "-m", "40", "-A", UA, *extra, url], capture_output=True, check=True)
    return json.loads(r.stdout)


def yahoo(sym):
    j = curl(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3y&interval=1d")["chart"]["result"][0]
    out = []
    for t, c in zip(j["timestamp"], j["indicators"]["quote"][0]["close"]):
        if c is not None:
            out.append([datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d"), round(c, 2)])
    return out


def cnn():
    start = (datetime.date.today() - datetime.timedelta(days=380)).isoformat()
    j = curl("https://production.dataviz.cnn.io/index/fearandgreed/graphdata/" + start, ("-H", "Referer: https://edition.cnn.com/", "-H", "Origin: https://edition.cnn.com"))
    fg = j["fear_and_greed"]
    hist = []
    for x in (j.get("fear_and_greed_historical") or {}).get("data", []):
        d = datetime.datetime.fromtimestamp(x["x"] / 1000, datetime.timezone.utc).strftime("%Y-%m-%d")
        hist.append([d, round(float(x["y"]), 1)])
    dedup = {}
    for d, v in hist:
        dedup[d] = v
    hist = sorted(dedup.items())
    sub = {}
    for k in SUBS:
        s = j.get(k)
        if isinstance(s, dict) and s.get("score") is not None:
            sub[k] = {"score": round(float(s["score"]), 1), "rating": s.get("rating")}
    return {"score": round(float(fg["score"]), 1), "rating": fg.get("rating"),
            "prev": {k: (round(float(fg[k]), 1) if fg.get(k) is not None else None) for k in ("previous_close", "previous_1_week", "previous_1_month", "previous_1_year")},
            "hist": [[d, v] for d, v in hist], "sub": sub}


def write(obj):
    for p in OUTS:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main():
    old = None
    try:
        old = json.load(open(OUTS[0], encoding="utf-8"))
        if time.time() - old.get("t", 0) < 2 * 3600:
            write(old)
            print("市場情緒：2 小時內抓過，沿用")
            return
    except (OSError, ValueError):
        pass
    out = {}
    try:
        for key, sym in (("vix", "%5EVIX"), ("vix3m", "%5EVIX3M"), ("skew", "%5ESKEW")):
            rows = yahoo(sym)
            if len(rows) < 100:
                raise ValueError(f"{key} 只有 {len(rows)} 筆")
            out[key] = rows
    except Exception as e:
        print("市場情緒：Yahoo 抓不到，沿用舊檔", repr(e)[:100])
        if old:
            write(old)
        return
    try:
        out["cnn"] = cnn()
        print("市場情緒：CNN 恐懼貪婪", out["cnn"]["score"], out["cnn"]["rating"])
    except Exception as e:
        print("市場情緒：CNN 抓不到（沿用上次的）", repr(e)[:100])
        out["cnn"] = (old or {}).get("cnn")
    out["asof"] = out["vix"][-1][0]
    out["fetched"] = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 8 * 3600))
    out["t"] = int(time.time())
    write(out)
    print("市場情緒：VIX", out["vix"][-1], "VIX3M", out["vix3m"][-1], "SKEW", out["skew"][-1])


if __name__ == "__main__":
    main()
