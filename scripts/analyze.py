"""讀取行情 + 族群表，算出每檔的四種型態與每個族群的統計，輸出 site/data.js。"""
import csv, json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E
import patterns as PT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART_BARS = 520
STATES = ["轉強", "弱轉強", "型態好", "盤整", "走弱"]


def load_prices(path):
    by = collections.defaultdict(dict)
    mk = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        try:
            o, h, l, c = (float(r[k]) for k in ("open", "high", "low", "close"))
        except (ValueError, TypeError):
            continue          # 無成交
        v = float(r["volume"]) if r["volume"] else 0.0
        f = float(r["f"]) if r.get("f") else 1.0
        by[r["code"]][r["date"]] = {"d": r["date"], "o": o, "h": h, "l": l, "c": c, "v": v, "f": f}
        mk[r["code"]] = r["market"]
    return by, mk


def r2(x):
    return None if x is None else round(x, 2)


def main():
    # 用法：analyze.py        → 你的 207 檔（舊資料）
    #       analyze.py all    → 全市場（prices_all.csv + groups_tw_all.csv），個股 K 線拆成 site/s/<代號>.json
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    us = mode == "us"                               # analyze.py us → 美股（prices_us.csv + groups_us.csv），輸出到 site/us/
    full = mode in ("all", "us")
    OUT = os.path.join(ROOT, "site", "us") if us else os.path.join(ROOT, "site")
    by, mk = load_prices(os.path.join(ROOT, "data", "prices_us.csv" if us else "prices_all.csv" if full else "prices_tw.csv"))
    all_dates = sorted({d for s in by.values() for d in s})
    asof = all_dates[-1]
    asof_m = {}                                   # 上市、上櫃各自的最新資料日（兩邊更新時間不同）
    for code_, s_ in by.items():
        m_ = mk.get(code_)
        asof_m[m_] = max(asof_m.get(m_, ""), max(s_))
    groups = list(csv.DictReader(open(os.path.join(ROOT, "data", "groups_us.csv" if us else "groups_tw_all.csv" if full else "groups_tw.csv"), encoding="utf-8")))
    if full:
        os.makedirs(os.path.join(OUT, "s"), exist_ok=True)

    di = {d: i for i, d in enumerate(all_dates)}
    stocks, missing = {}, []
    for g in groups:
        code = g["代號"]
        raw = [by[code][d] for d in sorted(by.get(code, {}))] if code in by else []
        if len(raw) < 40 or di.get(raw[-1]["d"], -1) < len(all_dates) - 5:        # 近 5 個交易日內沒有任何成交的才略過（停牌、全額交割等）
            missing.append(code)
            continue
        # 分析一律用還原價（避免除權息缺口造成誤判）；顯示時再換回原始價
        bars = [{"d": b["d"], "o": b["o"] * b["f"], "h": b["h"] * b["f"], "l": b["l"] * b["f"], "c": b["c"] * b["f"], "v": b["v"]} for b in raw]
        fm = {b["d"]: b["f"] for b in raw}
        R = lambda price, d: price / fm.get(d, 1.0)        # 還原價 → 原始價
        T = len(bars) - 1
        closes = [b["c"] for b in bars]
        ma = {n: E.sma(closes, n) for n in (5, 10, 20, 60)}
        box, ev = E.current_box(bars, T)
        state, tags, sub = E.classify(bars, ma[5], ma[10], ma[20], ma[60], T, box, ev)
        geo = [g for g in PT.detect_geometry(bars, T) if g["status"] in ("confirmed", "near", "forming")]
        state, tags, sub = E.apply_patterns(state, tags, sub, geo)
        if state == "轉強":                         # 均線還沒排列向上（5>10>20 且三條都往上）之前的轉強＝弱轉強
            m5, m10, m20 = ma[5], ma[10], ma[20]
            j = max(T - 3, 0)
            aligned = all(x[T] is not None and x[j] is not None for x in (m5, m10, m20)) and \
                m5[T] > m10[T] > m20[T] and m10[T] > m10[j] and m20[T] > m20[j]
            if not aligned and "多頭回檔後站回5日線" not in tags:     # 多頭回檔後站回：原本就是多頭結構，不算弱轉強
                state, sub = "弱轉強", None                            # 單獨一種型態，不和轉強算在一起
        candle = PT.candle_patterns(bars, T)
        rb = PT.rebound(bars, T)
        if rb and rb["score"] >= 2:
            rb["tier"] = "強" if rb["score"] >= 3 else "一般"
            tags.append("強勢止跌反彈" if rb["tier"] == "強" else "止跌反彈")
        else:
            rb = None
        for n, d in candle:
            tags.append(n)
        # KD(9,3,3) 高低檔鈍化：K 值連續 ≥3 日在 80 以上／20 以下（以還原價計算）
        k_, d_ = 50.0, 50.0
        run_hi = run_lo = 0
        for i in range(len(bars)):
            lo9 = min(b["l"] for b in bars[max(0, i - 8): i + 1])
            hi9 = max(b["h"] for b in bars[max(0, i - 8): i + 1])
            rsv = 50.0 if hi9 == lo9 else (bars[i]["c"] - lo9) / (hi9 - lo9) * 100
            k_ = 2 / 3 * k_ + rsv / 3
            d_ = 2 / 3 * d_ + k_ / 3
            run_hi = run_hi + 1 if k_ >= 80 else 0
            run_lo = run_lo + 1 if k_ <= 20 else 0
        if run_hi >= 3:
            tags.append("KD高檔鈍化")
        if run_lo >= 3:
            tags.append("KD低檔鈍化")
        st = {
            "code": code, "name": g["名稱"], "industry": g.get("產業別") or g.get("官方產業別"), "group": g["主族群"], "groups": [g["主族群"]] + ([g["副族群"]] if g.get("副族群") and g["副族群"] != g["主族群"] else []),
            "conf": g.get("把握度", "U"),
            "market": mk.get(code), "state": state, "sub": sub, "tags": tags,
            "close": raw[T]["c"],
            "chg": r2((raw[T]["c"] / raw[T - 1]["c"] - 1) * 100) if T else 0,
            "vol": round(raw[T]["v"] / 1000),
        }
        d_T = bars[T]["d"]
        st["geo"] = [{"kind": g["kind"], "dir": g["dir"], "status": g["status"], "day": g["day"],
                      "neck": r2(R(g["neck"], d_T)) if g["neck"] else None, "neckA": r2(g["neck"]) if g["neck"] else None,
                      "pts": [[bars[i]["d"], r2(R(p, bars[i]["d"])), r2(p)] for i, p in g["pts"]],
                      "lines": [[bars[a]["d"], r2(R(pa, bars[a]["d"])), bars[b]["d"], r2(R(pb, bars[b]["d"])), r2(pa), r2(pb)]
                                for a, pa, b, pb in g.get("lines", [])],
                      "volup": bool(g.get("volup")),
                      "stop": (r2(R(g["stop"], bars[g["rect"][0]]["d"])) if g.get("stop") else None), "stopA": (r2(g["stop"]) if g.get("stop") else None),
                      "rect": ([bars[g["rect"][0]]["d"], bars[g["rect"][1]]["d"], r2(R(g["rect"][2], bars[g["rect"][0]]["d"])), r2(R(g["rect"][3], bars[g["rect"][0]]["d"])), r2(g["rect"][2]), r2(g["rect"][3])] if g.get("rect") else None)} for g in geo]
        st["candle"] = [{"n": n, "d": d} for n, d in candle]
        if rb:
            rb["low"] = r2(R(rb["low"], bars[rb["low_idx"]]["d"]))
        st["rebound"] = rb
        if box:
            d_e = bars[box["e"]]["d"]
            st["box"] = {"s": bars[box["s"]]["d"], "e": d_e,
                         "hi": r2(R(box["hi"], d_e)), "lo": r2(R(box["lo"], d_e)),
                         "hiA": r2(box["hi"]), "loA": r2(box["lo"]), "live": ev is None}
        if ev:
            st["ev"] = {"date": bars[ev["b"]]["d"], "dir": ev["dir"], "state": ev["state"],
                        "signal": ev["signal"], "day": ev["day"], "expired": bool(ev.get("expired"))}
        n0 = max(0, len(bars) - CHART_BARS)
        rows = [[di[b["d"]], b["o"], b["h"], b["l"], b["c"], round(b["v"] / 1000), round(b["f"], 5)] for b in raw[n0:]]
        if full:
            with open(os.path.join(OUT, "s", code + ".json"), "w") as f:
                json.dump({"bars": rows}, f, separators=(",", ":"))
        else:
            st["bars"] = rows
        stocks[code] = st

    gl = collections.OrderedDict()
    for st in stocks.values():
        for gname in st["groups"]:                       # 雙族群的股票，兩個族群都會計入
            g = gl.setdefault(gname, {"name": gname, "n": 0,
                                      "counts": {s: 0 for s in STATES}, "stocks": [], "first": [],
                                      "weak_pull": 0, "weak_break": 0, "weak_strong": 0})
            g["n"] += 1
            g["counts"][st["state"]] += 1
            if st["sub"] == "回檔走弱":
                g["weak_pull"] += 1
            elif st["sub"] == "破底走弱":
                g["weak_break"] += 1
            g["stocks"].append(st["code"])
            if "突破第1根" in st["tags"]:
                g["first"].append(st["code"])
    glist = sorted(gl.values(), key=lambda g: (g["n"] < 5, -(g["counts"]["轉強"] + g["counts"]["型態好"]) / g["n"], -g["n"]))

    total = {s: sum(1 for st in stocks.values() if st["state"] == s) for s in STATES}      # 雙族群不重複計算
    index = {}
    for key, name, defind in (() if us else (("TX", "台指期", {}), ("TXD", "台指期（日盤）", {}), ("TXN", "台指期（夜盤）", {}), ("TWII", "加權指數", {}), ("OTC", "櫃買指數", {"macd": 1}))):
        fp = os.path.join(ROOT, "data", {"TXD": "index_TX_day.json", "TXN": "index_TX_night.json"}.get(key, f"index_{key}.json"))
        if os.path.exists(fp):
            index[key] = {"name": name, "bars": json.load(open(fp)), "defInd": defind}
    live = None
    mp = os.path.join(ROOT, "data", "intraday_meta.json")
    if full and not us and os.path.exists(mp):
        live = json.load(open(mp))
    out = {"live": live, "asof": asof, "asofM": asof_m, "dates": all_dates, "total": total, "groups": glist, "stocks": stocks, "missing": missing, "index": index}
    if us:
        out["market"] = "US"
    with open(os.path.join(OUT, "data.js"), "w", encoding="utf-8") as f:
        f.write("window.DATA=" + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";")
    print("asof", asof, "stocks", len(stocks), "missing", len(missing), missing[:20])
    print("total", total)
    if not full:
        for g in glist:
            print(f'{g["name"]:<10} n={g["n"]:<3}', g["counts"], "突破第1根:", g["first"])


if __name__ == "__main__":
    main()
