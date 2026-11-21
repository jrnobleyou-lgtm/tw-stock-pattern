"""補 2021～2024-11-10 的除權息還原事件（含配股）→ data/adjust_old.csv（code,exdate,k；k＝除權息參考價÷除權息前收盤價，跟 adjust.csv 同義）。
11/21 使用者要 2 年線，歷史要補到 5 年（Opus 顧問建議）：官方整年一次查，上市 TWT49U、上櫃 exDailyQ，各年只要 1 次請求；證交所連續請求會被擋，每次間隔 35 秒。
原始回應存 data/exdiv_old/<市場>_<年>.json（可續跑，已存在就不重抓）。
只留 4 位數股票代號、除權息日 < 2024-11-11（之後的事件由 adjust.csv 負責）。"""
import csv, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "exdiv_old")
os.makedirs(RAW, exist_ok=True)
CUT = "2024-11-11"
YEARS = range(2021, 2025)


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print("  失敗", repr(e)[:80], flush=True)
            time.sleep(60 * (i + 1))
    return None


def roc_date(s):                                    # 110年01月05日 或 110/01/05 → 2021-01-05
    s = s.replace("年", "/").replace("月", "/").replace("日", "").strip()
    y, m, d = s.split("/")
    return f"{int(y) + 1911}-{int(m):02d}-{int(d):02d}"


def fnum(x):
    try:
        return float(str(x).replace(",", ""))
    except ValueError:
        return None


def main():
    last = 0.0
    for mk, tmpl in (("TWSE", "https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate={y}0101&endDate={y}1231&response=json"),
                     ("TPEX", "https://www.tpex.org.tw/www/zh-tw/bulletin/exDailyQ?startDate={y}/01/01&endDate={y}/12/31&response=json")):
        for y in YEARS:
            p = os.path.join(RAW, f"{mk}_{y}.json")
            if os.path.exists(p):
                continue
            wait = 35 - (time.time() - last)
            if wait > 0:
                time.sleep(wait)
            j = get(tmpl.format(y=y))
            last = time.time()
            if not j:
                print("放棄", mk, y, flush=True)
                continue
            json.dump(j, open(p, "w", encoding="utf-8"), ensure_ascii=False)
            print("已抓", mk, y, flush=True)
    out = {}
    for mk in ("TWSE", "TPEX"):
        for y in YEARS:
            p = os.path.join(RAW, f"{mk}_{y}.json")
            if not os.path.exists(p):
                continue
            j = json.load(open(p, encoding="utf-8"))
            if mk == "TWSE":
                rows = [(r[0], r[1], r[3], r[4]) for r in j.get("data", [])]
            else:
                rows = [(r[0], r[1], r[3], r[4]) for r in (j.get("tables") or [{}])[0].get("data", [])]
            for d, code, prev, ref in rows:
                code = str(code).strip()
                if not (len(code) == 4 and code.isdigit()):
                    continue
                ex = roc_date(d)
                a, b = fnum(prev), fnum(ref)
                if ex >= CUT or not a or not b:
                    continue
                k = round(b / a, 6)
                if abs(k - 1) < 1e-6:
                    continue
                out[(code, ex)] = k
    with open(os.path.join(ROOT, "data", "adjust_old.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["code", "exdate", "k"])
        for (code, ex), k in sorted(out.items()):
            w.writerow([code, ex, k])
    print("adjust_old.csv：", len(out), "筆", flush=True)


if __name__ == "__main__":
    main()
