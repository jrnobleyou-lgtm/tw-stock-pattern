"""把 FinMind 補抓的長歷史（data/fm/<代號>.json，未還原價，2021-06 起）整理成 data/hist_old/<年>.csv.gz（只放 2024-11-11 以前的列）。
11/21 使用者要 2 年線，歷史補到 5 年（Opus 顧問建議）。
接縫處理：現有 data/hist 的前段是 Yahoo 時期來的，配股事件前的價格已被除過；FinMind 是真原始價。
  所以逐檔取「接縫日（2024-11-11 起第一個兩邊都有的日子）」：比例 r ＝ hist 收盤 ÷ FinMind 收盤，
  差超過 0.2% 就把這檔更早的 FinMind 價格全部乘 r（量不動），讓兩段接得起來。除權息還原（含配股）由 adjust_old.csv 負責。
用法：python3 scripts/merge_old.py   （可重複執行；輸出整批重寫）"""
import csv, glob, gzip, json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CUT = "2024-11-11"
FM = os.path.join(ROOT, "data", "fm")
OUT = os.path.join(ROOT, "data", "hist_old")


def main():
    os.makedirs(OUT, exist_ok=True)
    # 現有 hist：每檔市場、接縫日的收盤（只看 CUT 起前 10 個交易日內第一個兩邊都有的日子）
    mk, first = {}, collections.defaultdict(dict)
    for f in sorted(glob.glob(os.path.join(ROOT, "data", "hist", "*.csv")))[:2]:
        for r in csv.DictReader(open(f, encoding="utf-8")):
            mk[r["code"]] = r["market"]
            if len(first[r["code"]]) < 10:
                first[r["code"]][r["date"]] = float(r["close"])
    by_year = collections.defaultdict(list)
    ratios, nofm, noseam = {}, 0, 0
    for code, market in sorted(mk.items()):
        p = os.path.join(FM, code + ".json")
        if not os.path.exists(p):
            nofm += 1
            continue
        rows = json.load(open(p, encoding="utf-8"))
        fmc = {x["date"]: x for x in rows}
        r = 1.0
        for d in sorted(first[code]):
            if d in fmc and fmc[d]["close"]:
                r = first[code][d] / fmc[d]["close"]
                break
        else:
            noseam += 1
        if abs(r - 1) <= 0.002:
            r = 1.0
        else:
            ratios[code] = round(r, 5)
        for x in rows:
            if x["date"] >= CUT:
                continue
            o, h, l, c = x["open"], x["max"], x["min"], x["close"]
            if not (o and h and l and c) or not x.get("Trading_Volume"):       # 開高低收是 0（無成交）或成交量 0 的日子不收
                continue
            by_year[x["date"][:4]].append([x["date"], code, market, round(o * r, 4), round(h * r, 4), round(l * r, 4), round(c * r, 4), x["Trading_Volume"]])
    for y, rows in sorted(by_year.items()):
        rows.sort(key=lambda t: (t[0], t[1]))
        with gzip.open(os.path.join(OUT, y + ".csv.gz"), "wt", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", "code", "market", "open", "high", "low", "close", "volume"])
            w.writerows(rows)
        print(y, len(rows), "列")
    json.dump(ratios, open(os.path.join(OUT, "seam_ratios.json"), "w"), ensure_ascii=False, indent=0)
    print("沒有 FinMind 檔", nofm, "檔；找不到接縫日", noseam, "檔；需要調接縫比例", len(ratios), "檔")


if __name__ == "__main__":
    main()
