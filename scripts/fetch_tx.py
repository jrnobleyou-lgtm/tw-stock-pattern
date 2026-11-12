"""台指期（大台 TX）近月日 K：期交所「期貨每日交易行情」下載（逐月查詢）。
輸出 data/index_TX.json（全盤＝前一晚夜盤＋當天日盤）與 data/index_TX_day.json（只有日盤）：
  [[交易日, 開, 高, 低, 收, 成交量(口), 1.0], ...]
近月：每個交易日、每個時段取「到期月份最近」的月契約（不含週契約），所以結算日當天日盤還是舊月份，
      當天 15:00 開始的夜盤（算在下一個交易日）就自動換到下個月。
用法：fetch_tx.py（近 2 個月）／ fetch_tx.py --full（近 26 個月）"""
import csv, datetime, io, json, os, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P_ALL = os.path.join(ROOT, "data", "index_TX.json")
P_DAY = os.path.join(ROOT, "data", "index_TX_day.json")
FULL = "--full" in sys.argv or not os.path.exists(P_ALL)

def month_rows(start, end):
    body = urllib.parse.urlencode({"down_type": "1", "commodity_id": "TX", "commodity_id2": "",
                                   "queryStartDate": start.strftime("%Y/%m/%d"), "queryEndDate": end.strftime("%Y/%m/%d")}).encode()
    for i in range(3):
        try:
            req = urllib.request.Request("https://www.taifex.com.tw/cht/3/futDataDown", data=body, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                txt = r.read().decode("cp950", errors="replace")
            if txt.startswith("交易日期"):
                return list(csv.reader(io.StringIO(txt)))[1:]
            print("  非 CSV 回應", start, txt[:60].replace("\n", " "))
        except Exception as e:
            print("  失敗", start, repr(e)[:80])
        time.sleep(5 * (i + 1))
    return []

def num(x):
    try:
        return float(x)
    except ValueError:
        return None

today = datetime.date.today()
months, m = [], today.replace(day=1)
for _ in range(26 if FULL else 2):
    months.append(m); m = (m - datetime.timedelta(days=1)).replace(day=1)
best = {}                                           # (交易日, 時段) -> (到期月份, 開, 高, 低, 收, 量)
for m in sorted(months):
    nxt = (m.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    for r in month_rows(m, min(nxt - datetime.timedelta(days=1), today)):
        if len(r) < 18 or r[1].strip() != "TX":
            continue
        ym = r[2].strip()
        if not (len(ym) == 6 and ym.isdigit()):
            continue                                 # 週契約、價差單略過
        o, h, l, c, v = (num(r[k]) for k in (3, 4, 5, 6, 9))
        if None in (o, h, l, c):
            continue
        key = (r[0].strip().replace("/", "-"), "day" if r[17].strip() == "一般" else "night")
        if key not in best or ym < best[key][0]:
            best[key] = (ym, o, h, l, c, v or 0)
    time.sleep(2)

dates = sorted({d for d, _ in best})
day_rows, all_rows = [], []
for d in dates:
    dy, nt = best.get((d, "day")), best.get((d, "night"))
    if dy:
        day_rows.append([d, dy[1], dy[2], dy[3], dy[4], int(dy[5]), 1.0])
    if dy and nt and nt[0] == dy[0]:                # 夜盤和日盤是同一個契約才合併
        all_rows.append([d, nt[1], max(nt[2], dy[2]), min(nt[3], dy[3]), dy[4], int(nt[5] + dy[5]), 1.0])
    elif dy:
        all_rows.append([d, dy[1], dy[2], dy[3], dy[4], int(dy[5]), 1.0])

def merge(p, rows):
    old = json.load(open(p)) if os.path.exists(p) else []
    out = sorted({r[0]: r for r in old + rows}.values())
    json.dump(out, open(p, "w")); return out

a = merge(P_ALL, all_rows); b = merge(P_DAY, day_rows)
print("台指期 全盤", len(a), a[-1] if a else None, "；日盤", len(b))
