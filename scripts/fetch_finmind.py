"""用 FinMind 補抓全市場歷史日 K（每檔一次請求，未還原價）。
嚴格遵守 FinMind「IP 封鎖政策」（https://finmindtrade.com/analysis/#/Sponsor/ban_ip_policy）與每小時 600 次上限：
  - 只用註冊會員可用的 TaiwanStockPrice（指定單一 data_id），不碰贊助會員資料集。
  - 短時間大量 4xx 會被封鎖 30 分鐘 → 任何 4xx 都「不重試」：該檔記錄後跳過；連續 3 次 4xx 就整個中止。
  - 402（超額）→ 停到下一個整點之後；403（ip banned）→ 停 35 分鐘，再遇到就中止。
  - 5xx / 連線逾時才做指數退避，最多 3 次。
  - 速度：每次請求間隔 ≥ 8 秒，且任何滾動 60 分鐘內 ≤ 480 次（上限 600 的 80%）。
Token 由系統代理自動帶上，程式裡不碰金鑰。
用法：python3 fetch_finmind.py [起始日 YYYY-MM-DD]
"""
import csv, json, os, sys, time, datetime, collections, urllib.request, urllib.error, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "fm")
os.makedirs(OUT, exist_ok=True)
START = sys.argv[1] if len(sys.argv) > 1 else "2025-09-01"
BASE = "https://api.finmindtrade.com/api/v4/data"
MIN_GAP, HOURLY_CAP = float(os.environ.get("MIN_GAP", "12")), int(os.environ.get("HOURLY_CAP", "300"))

codes = [r["代號"] for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8"))]
if os.environ.get("FM_TODO") and os.path.exists(os.environ["FM_TODO"]):      # 只補指定清單（依清單順序）
    codes = [c.strip() for c in open(os.environ["FM_TODO"]) if c.strip()]
stamps = collections.deque()
last = 0.0

def pace():
    global last
    now = time.time()
    while stamps and now - stamps[0] > 3600:
        stamps.popleft()
    if len(stamps) >= HOURLY_CAP:
        wait = 3600 - (now - stamps[0]) + 5
        print(f"  已達每小時 {HOURLY_CAP} 次，等 {wait/60:.1f} 分鐘", flush=True)
        time.sleep(max(wait, 1))
    gap = MIN_GAP - (time.time() - last)
    if gap > 0:
        time.sleep(gap)
    last = time.time()
    stamps.append(last)

def call(code):
    """回傳 ('ok', rows) / ('skip', 原因) / ('quota',) / ('banned',) / ('abort', 原因)"""
    q = urllib.parse.urlencode({"dataset": "TaiwanStockPrice", "data_id": code, "start_date": START})
    for attempt in range(3):
        pace()
        try:
            with urllib.request.urlopen(urllib.request.Request(BASE + "?" + q, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
            if d.get("status") == 200:
                return ("ok", d.get("data") or [])
            code_ = d.get("status")
            msg = d.get("msg")
        except urllib.error.HTTPError as e:
            code_ = e.code
            try:
                msg = json.loads(e.read().decode("utf-8")).get("msg")
            except Exception:
                msg = str(e)
        except Exception as e:                      # 連線逾時等：當 5xx 處理
            code_, msg = 599, str(e)
        if code_ == 402:
            return ("quota",)
        if code_ == 403:
            return ("banned",)
        if 400 <= code_ < 500:
            return ("skip", f"{code_} {msg}")       # 4xx：不重試
        time.sleep(10 * 3 ** attempt)               # 5xx：指數退避（10s, 30s, 90s）
    return ("skip", "5xx/逾時 3 次")

bad4xx = 0
failed = {}
todo = [c for c in codes if not os.path.exists(os.path.join(OUT, c + ".json"))]
print("待抓", len(todo), "/", len(codes), "起始", START, flush=True)
done = 0
banned_once = False
for code in todo:
    res = call(code)
    if res[0] == "quota":
        wait = 3600 - (time.time() % 3600) + 300
        print(f"  402 超額：停到下一個整點後（{wait/60:.0f} 分鐘）", flush=True)
        time.sleep(wait)
        stamps.clear()
        res = call(code)
    if res[0] == "banned":
        if banned_once:
            print("再次被封鎖，中止。", flush=True); break
        banned_once = True
        print("  403 ip banned：停 35 分鐘（政策：30 分鐘自動解除）", flush=True)
        time.sleep(35 * 60)
        stamps.clear()
        res = call(code)
        if res[0] == "banned":
            print("仍被封鎖，中止。", flush=True); break
    if res[0] == "ok":
        json.dump(res[1], open(os.path.join(OUT, code + ".json"), "w"), ensure_ascii=False)
        bad4xx = 0
        done += 1
        if done % 25 == 0:
            print(f"進度 {done}/{len(todo)}（{code}）", flush=True)
    elif res[0] == "skip":
        failed[code] = res[1]
        print("  略過", code, res[1], flush=True)
        if res[1][:1] == "4":
            bad4xx += 1
            if bad4xx >= 3:
                print("連續 3 次 4xx，為避免被封鎖而中止。", flush=True); break
    else:
        print("未預期結果", res, flush=True); break
json.dump(failed, open(os.path.join(ROOT, "data", "fm_failed.json"), "w"), ensure_ascii=False)
print("結束：成功", done, "略過", len(failed), flush=True)
