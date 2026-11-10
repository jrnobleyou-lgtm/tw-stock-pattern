"""用 Yahoo 財經 chart 接口一次補齊全市場 2 年日 K + 除權息紀錄 + 還原價（一次性歷史回補）。
每檔一次請求。非官方接口 → 放慢、遇到限制就停、不暴力重試：
  - 每次請求間隔 2.0 秒（≈ 每分鐘 30 次）。
  - 429（請求太多）→ 停 10 分鐘，第二次再遇到就中止。
  - 其他 4xx → 不重試，記錄後略過；連續 5 次失敗就中止。
  - 5xx／逾時 → 指數退避最多 3 次。
輸出：data/yh/<代號>.json = {"d":[日期],"o":[],"h":[],"l":[],"c":[],"v":[],"adj":[],"div":[[日期,金額]],"split":[[日期,分子,分母]]}
當天若台灣時間尚未收盤（14:00 前）會略過當天那根未完成的 K 棒。
用法：python3 fetch_yahoo.py
"""
import csv, json, os, sys, time, datetime, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "yh")
os.makedirs(OUT, exist_ok=True)
GAP = float(os.environ.get("YH_GAP", "2.0"))
TW = datetime.timezone(datetime.timedelta(hours=8))
now_tw = datetime.datetime.now(TW)
skip_today = now_tw.hour < 14

rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8")))
mk = {r["代號"]: r["市場"] for r in rows}
order = []
if os.path.exists(os.path.join(ROOT, "data", "fm_todo.txt")):            # 沒有歷史的上市股優先
    order = [c.strip() for c in open(os.path.join(ROOT, "data", "fm_todo.txt")) if c.strip()]
order += [c for c in mk if c not in set(order)]
todo = [c for c in order if not os.path.exists(os.path.join(OUT, c + ".json"))]
print("待抓", len(todo), "/", len(order), "略過當天未收盤:", skip_today, flush=True)

def fetch(code):
    sym = code + (".TW" if mk[code] == "TWSE" else ".TWO")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d&events=div%2Csplits&includeAdjustedClose=true"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return ("ok", json.loads(r.read().decode("utf-8")))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                return ("rate",)
            if e.code == 404:
                return ("none", "404")
            if 400 <= e.code < 500:
                return ("skip", str(e.code))
        except Exception as e:
            pass
        time.sleep(10 * 3 ** attempt)
    return ("skip", "5xx/逾時")

def parse(j):
    res = (j.get("chart") or {}).get("result")
    if not res:
        return None
    r = res[0]
    ts = r.get("timestamp") or []
    q = (r.get("indicators", {}).get("quote") or [{}])[0]
    adj = (r.get("indicators", {}).get("adjclose") or [{}])[0].get("adjclose") or q.get("close")
    out = {"d": [], "o": [], "h": [], "l": [], "c": [], "v": [], "adj": []}
    today = now_tw.date().isoformat()
    for i, t in enumerate(ts):
        d = datetime.datetime.fromtimestamp(t, TW).date().isoformat()
        if skip_today and d == today:
            continue
        o, h, l, c, v = (q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i])
        if None in (o, h, l, c):
            continue
        out["d"].append(d)
        for k, x in (("o", o), ("h", h), ("l", l), ("c", c)):
            out[k].append(round(x, 2))
        out["v"].append(int(v or 0))
        out["adj"].append(round(adj[i], 4) if adj and adj[i] else round(c, 4))
    ev = r.get("events") or {}
    out["div"] = sorted([[datetime.datetime.fromtimestamp(v["date"], TW).date().isoformat(), v["amount"]] for v in (ev.get("dividends") or {}).values()])
    out["split"] = sorted([[datetime.datetime.fromtimestamp(v["date"], TW).date().isoformat(), v["numerator"], v["denominator"]] for v in (ev.get("splits") or {}).values()])
    return out

done = fails = consec = 0
rate_hit = False
for code in todo:
    time.sleep(GAP)
    res = fetch(code)
    if res[0] == "rate":
        if rate_hit:
            print("再次遇到 429，中止。", flush=True); break
        rate_hit = True
        print("  429 請求太多：停 10 分鐘", flush=True)
        time.sleep(600)
        res = fetch(code)
        if res[0] == "rate":
            print("仍是 429，中止。", flush=True); break
    if res[0] == "ok":
        p = parse(res[1])
        if p and p["d"]:
            json.dump(p, open(os.path.join(OUT, code + ".json"), "w"), separators=(",", ":"))
            done += 1; consec = 0
        else:
            json.dump({"d": []}, open(os.path.join(OUT, code + ".json"), "w"))   # 無資料（例如新上市）
            consec = 0
    elif res[0] == "none":
        json.dump({"d": []}, open(os.path.join(OUT, code + ".json"), "w")); consec = 0
    else:
        fails += 1; consec += 1
        print("  略過", code, res[1], flush=True)
        if consec >= 5:
            print("連續 5 次失敗，中止。", flush=True); break
    if (done + fails) % 50 == 0:
        print(f"進度 成功{done} 失敗{fails}（{code}）", flush=True)
print("結束：成功", done, "失敗", fails, flush=True)
