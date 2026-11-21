"""讀取行情 + 族群表，算出每檔的四種型態與每個族群的統計，輸出 site/data.js。"""
import time, csv, json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E
import patterns as PT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHART_BARS = 520
STATES = ["轉強", "弱轉強", "型態好", "盤整", "走弱"]




def filter_by_drawings(geo, bars, drawings):
    """管理者畫線 vs 系統形態（時間範圍比對）：
       沒有重疊 → 兩個都留；重疊但系統的沒有比畫線更往後 → 以管理者為準，系統的拿掉；
       重疊且系統的延伸到畫線之後（例如畫了 V，系統認出完整的 W）→ 系統的留著，並回報「型態已更新」。"""
    spans = [(d.get("d0"), d.get("d1"), d.get("name") or "") for d in drawings
             if isinstance(d, dict) and d.get("kind") != "hline" and d.get("d0")]
    if any(not isinstance(d, dict) for d in drawings):
        return [], []                                # 舊格式（只有名稱）：維持全部以管理者為準
    import bisect
    ds = [b["d"] for b in bars]
    back10 = lambda d: ds[max(0, bisect.bisect_left(ds, d) - 10)]        # 畫線起點往前 10 根
    keep, upd = [], []
    for g in geo:
        idx = [i for i, _ in g["pts"]] + (list(g["rect"][:2]) if g.get("rect") else [])
        if not idx:
            keep.append(g); continue
        s0, s1 = bars[min(idx)]["d"], bars[max(idx)]["d"]
        hit = [(a, b, n) for a, b, n in spans if s0 <= b and s1 >= a]
        if not hit:
            keep.append(g)                           # 沒有蓋到：兩個都顯示
        elif all(back10(a) <= s0 < b and s1 >= b for a, b, n in hit):
            keep.append(g)                           # 系統從畫線範圍內開始、畫到跟畫線一樣遠或更遠（系統認得了／往後補完，例：畫 V，系統認出 W）
            upd += [n for a, b, n in hit if n not in upd]
        # 其他重疊：以管理者的畫線為準，系統的不顯示
    return keep, upd

def gl_of(g):
    """族群清單：主族群、副族群都可以用「+」或「、」列多個（例如 汽車+電池/能源+機器人/自動化），第一個是主族群。"""
    out = []
    for x in ((g.get("主族群") or "") + "+" + (g.get("副族群") or "")).replace("、", "+").split("+"):
        x = x.strip()
        if x and x not in out:
            out.append(x)
    return out or ["其他"]

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


def dmi_series(bars, n=14):
    """DMI(14) Wilder，與網頁 K 線圖 calcDMI 同一套算法（還原價）。回傳 (+DI, -DI, ADX) 三個清單（沒有值是 None）。"""
    N = len(bars)
    pdi, mdi, adx = [None] * N, [None] * N, [None] * N
    if N <= n * 2:
        return pdi, mdi, adx
    P, M, T = [0.0] * N, [0.0] * N, [0.0] * N
    for i in range(1, N):
        up = bars[i]["h"] - bars[i - 1]["h"]
        dn = bars[i - 1]["l"] - bars[i]["l"]
        P[i] = up if up > dn and up > 0 else 0.0
        M[i] = dn if dn > up and dn > 0 else 0.0
        T[i] = max(bars[i]["h"] - bars[i]["l"], abs(bars[i]["h"] - bars[i - 1]["c"]), abs(bars[i]["l"] - bars[i - 1]["c"]))
    sp, sm, st = sum(P[1:n + 1]), sum(M[1:n + 1]), sum(T[1:n + 1])
    dx = [0.0] * N
    for i in range(n, N):
        if i > n:
            sp = sp - sp / n + P[i]; sm = sm - sm / n + M[i]; st = st - st / n + T[i]
        pdi[i] = 100 * sp / st if st else 0.0
        mdi[i] = 100 * sm / st if st else 0.0
        dx[i] = 100 * abs(pdi[i] - mdi[i]) / (pdi[i] + mdi[i]) if (pdi[i] + mdi[i]) else 0.0
    a = sum(dx[n:2 * n]) / n
    adx[2 * n - 1] = a
    for i in range(2 * n, N):
        a = (a * (n - 1) + dx[i]) / n
        adx[i] = a
    return pdi, mdi, adx


def prev_swing(bars, T, hi=True, w=5, look=60):
    """前段高點／低點：最近一個「前後各 w 根都沒有更高（低）」的波段高（低）點，限 look 根內、而且已經確認（離今天至少 w 根）。
    找不到（一路漲／跌沒有波段）就用最近 look 根（不含最近 w 根）的最高／最低價。"""
    k = "h" if hi else "l"
    for j in range(T - w, max(T - look, w) - 1, -1):
        seg = [b[k] for b in bars[j - w:j + w + 1]]
        if bars[j][k] == (max(seg) if hi else min(seg)):
            return bars[j][k]
    seg = [b[k] for b in bars[max(0, T - look):T - w + 1]]
    return (max(seg) if hi else min(seg)) if seg else None


def dmi_tags(bars, Ks, Ds):
    """DMI 標籤（11/15 晚使用者定案，目的是找「可以先進去蹲」的股票；回測與門檻由 Fable 顧問提供）。
    多方（篩選頁）：
      即將翻多：+DI 仍在 -DI 下面且相距 ≤5、+DI 比 3 天前高、-DI 比 3 天前低、ADX ≥15、KD 條件，且近 10 日低點到收盤漲幅 <10%。
                （不再要求 ADX 不低於 3 天前：兩線靠近時 ADX 本來就多半往下，那條把 156 檔濾到 16 檔。）
      DMI翻多前已轉強：同上，但漲幅 10%～20%（20% 以上已不是蹲點位置，不列；30% 以上另有「近日反彈強勁」）。
      剛翻多：近 2 日 +DI 上穿 -DI，+DI ≥20 且比 -DI 大 ≥2，+DI 比 3 天前高、-DI 比 3 天前低，ADX ≥15，KD 條件（漲幅不限）。
      多頭趨勢：+DI 比 -DI 大 ≥5，ADX ≥25 且比 3 天前高 0.5 以上，收盤站上前段高點（電視節目的多方定義）。
    只標在個股（不放篩選頁）：剛翻空、空頭趨勢（對稱）、DMI過熱（+DI 在上、ADX ≥45 且比 3 天前低 0.5 以上：趨勢走很久、力道開始退）。
    KD 條件 kd_up／kd_dn 維持 11/15 中午版本，等使用者另訂。K 棒不足 60 根不標。"""
    out = []
    if len(bars) < 60:
        return out
    pdi, mdi, adx = dmi_series(bars)
    T = len(bars) - 1
    if None in (pdi[T], mdi[T], adx[T], adx[T - 3], pdi[T - 3], mdi[T - 3]):
        return out
    p, m, a = pdi[T], mdi[T], adx[T]
    c = bars[T]["c"]
    a_up, a_dn = a - adx[T - 3] > 0.5, a - adx[T - 3] < -0.5
    if a >= 25 and a_up:
        if p - m >= 5:
            ph = prev_swing(bars, T, True)
            if ph is not None and c > ph:
                out.append("DMI多頭趨勢")
        elif m - p >= 5:
            pl = prev_swing(bars, T, False)
            if pl is not None and c < pl:
                out.append("DMI空頭趨勢")
    if p > m and a >= 45 and a_dn:
        out.append("DMI過熱")
    k, d = Ks[T], Ds[T]
    k3 = Ks[T - 2:T + 1]
    kd_up = (k >= d or d - k <= 5) and k < 80 and max(k3) < 80          # KD 條件維持 11/15 中午的版本（使用者之後自己訂）
    kd_dn = (k <= d or k - d <= 5) and k > 20 and min(k3) > 20
    di_up = p > pdi[T - 3] and m < mdi[T - 3]                              # 買方變強、賣方變弱
    di_dn = m > mdi[T - 3] and p < pdi[T - 3]
    if a >= 15:
        crossed_up = p > m and any(pdi[T - j] <= mdi[T - j] for j in (1, 2))
        if crossed_up and p >= 20 and p - m >= 2 and di_up and kd_up:
            out.append("DMI剛翻多")
        crossed_dn = m > p and any(mdi[T - j] <= pdi[T - j] for j in (1, 2))
        if crossed_dn and m >= 20 and m - p >= 2 and di_dn and kd_dn:
            out.append("DMI剛翻空")
        if p < m and m - p <= 5 and di_up and kd_up:
            lo10 = min(b["l"] for b in bars[-10:])
            gain = c / lo10 - 1 if lo10 > 0 else 0
            if gain < 0.10:
                out.append("DMI即將翻多")
            elif gain < 0.20:
                out.append("DMI翻多前已轉強")
    return out


def dmi_now(bars):
    """列表用的 DMI 數字：[差值（+DI − -DI）, ADX, ADX 方向（1 上升／0 持平／-1 下降，和 3 天前比、差 0.5 以內算持平）]。"""
    if len(bars) < 60:
        return None
    pdi, mdi, adx = dmi_series(bars)
    T = len(bars) - 1
    if None in (pdi[T], mdi[T], adx[T], adx[T - 3]):
        return None
    ch = adx[T] - adx[T - 3]
    return [round(pdi[T] - mdi[T], 1), round(adx[T], 1), 1 if ch > 0.5 else -1 if ch < -0.5 else 0]


def site_site():
    return os.environ.get("SITE_URL", "https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev").rstrip("/")


def cached(name, val, default):
    """11/17 Fable 審查：外部資料（新聞、重訊、畫線）這輪抓失敗就沿用上次成功的結果，不要整塊空掉。
    成功時存 site/cache/<name>.json（跟網站一起發布，內容都是公開的衍生結果）；失敗時從線上網站讀上次那份。"""
    import urllib.request
    path = os.path.join(ROOT, "site", "cache", name + ".json")
    if val is not None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(sorted(val) if isinstance(val, set) else val, f, ensure_ascii=False, separators=(",", ":"))
        return val
    try:
        v = json.loads(urllib.request.urlopen(urllib.request.Request(site_site() + "/cache/" + name + ".json", headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
        print(f"  {name}：沿用線上上次的結果")
        return set(v) if isinstance(default, set) else v
    except Exception:
        try:
            v = json.load(open(path, encoding="utf-8"))
            return set(v) if isinstance(default, set) else v
        except Exception:
            return default


def mops_today(all_dates):
    """11/16 使用者：「今天有重訊」＝上一交易日收盤（13:30）之後到現在有重訊（news-data 分支 mops.json；連續重複公告只算第一次）。"""
    import urllib.request, datetime
    try:
        with urllib.request.urlopen("https://raw.githubusercontent.com/jrnobleyou-lgtm/tw-stock-pattern/news-data/mops.json", timeout=20) as r:
            rows = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("重訊資料讀不到，沿用上次：", e)
        return None
    td = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).strftime("%Y-%m-%d")
    p = all_dates[-2] if all_dates[-1] >= td and len(all_dates) > 1 else all_dates[-1]
    cut = datetime.datetime.fromisoformat(p + "T13:30:00+08:00").timestamp()
    return {r["c"] for r in rows if r.get("t", 0) >= cut}


def target_rows():
    """11/18 法人目標價：讀 news-data 分支的 targets.json（scripts/targets.py 整理的具名目標價列）。讀不到回傳 None。"""
    import urllib.request
    try:
        with urllib.request.urlopen("https://raw.githubusercontent.com/jrnobleyou-lgtm/tw-stock-pattern/news-data/targets.json", timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("目標價資料讀不到，沿用上次：", e)
        return None


def news_bias():
    """11/16 使用者：近 7 天新聞 AI 判斷（scripts/news.py → news-data 分支）彙總成「近期消息偏多／偏空」。
    只算「事件」「法人」（投顧點名、盤勢文不算）；同一檔同一天同方向只算一次（多家轉載不灌票）；利多比利空多 2 則以上＝偏多，反之偏空。"""
    import urllib.request
    try:
        with urllib.request.urlopen("https://raw.githubusercontent.com/jrnobleyou-lgtm/tw-stock-pattern/news-data/items.json", timeout=20) as r:
            items = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("新聞資料讀不到，沿用上次：", e)
        return None
    lim, votes = time.time() - 7 * 86400, collections.defaultdict(set)
    for x in items:
        if x.get("t", 0) < lim:
            continue
        day = time.strftime("%Y-%m-%d", time.gmtime(x["t"] + 8 * 3600))
        for s_ in x.get("ai", []):
            if s_.get("k") in ("事件", "法人") and s_.get("d") in (1, -1):
                votes[s_["c"]].add((day, s_["d"]))
    out = {}
    for c, v in votes.items():
        up, dn = sum(1 for _, d in v if d > 0), sum(1 for _, d in v if d < 0)
        if up - dn >= 2:
            out[c] = "近期消息偏多"
        elif dn - up >= 2:
            out[c] = "近期消息偏空"
    return out


def fetch_inst():
    """三大法人現貨買賣超（證交所 BFI82U，只含上市，單位換成億元）。抓不到回傳 None（網頁會顯示「稍後更新」，不放舊數字）。"""
    import urllib.request
    try:
        j = None
        for k in range(3):                       # 偶爾連線被重設，重試 3 次
            try:
                j = json.loads(urllib.request.urlopen(urllib.request.Request(
                    "https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&response=json", headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
                break
            except Exception:
                time.sleep(2)
        if not j or j.get("stat") != "OK":
            return None
        v = {r[0]: float(r[3].replace(",", "")) / 1e8 for r in j["data"]}
        d = j["date"]
        return {"date": f"{d[:4]}-{d[4:6]}-{d[6:]}",
                "foreign": round(v["外資及陸資(不含外資自營商)"] + v.get("外資自營商", 0), 1),
                "trust": round(v["投信"], 1),
                "dealer": round(v["自營商(自行買賣)"] + v["自營商(避險)"], 1),
                "total": round(v["合計"], 1)}
    except Exception as e:
        print("讀不到三大法人（略過）", repr(e)[:80])
        return None


def fetch_fut_foreign():
    """外資及陸資在臺股期貨（大台 TX）的未平倉淨口數（負數＝淨空），與前一交易日的增減。
    來源：期交所「三大法人－區分各期貨契約」。先抓網頁 CSV（可指定日期區間，才有前一日）；擋掉時改用開放資料（只有最新一日，沒有前日就不顯示增減）。
    抓不到回傳 None（網頁顯示「稍後更新」，不放舊數字）。"""
    import urllib.request, datetime, io
    def rows(text):
        return list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
    def pick(rs):
        out = {}
        for x in rs:
            if x.get("商品名稱") == "臺股期貨" and x.get("身份別") == "外資及陸資":
                d = x["日期"].replace("/", "")
                out[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = int(x["多空未平倉口數淨額"].replace(",", ""))
        return out
    hdr = {"User-Agent": "Mozilla/5.0"}
    got = {}
    today = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
    for back in range(0, 6):                     # 結束日不能晚於期交所最新資料日，從今天往前試
        end = today - datetime.timedelta(days=back)
        if end.weekday() >= 5:
            continue
        try:
            url = ("https://www.taifex.com.tw/cht/3/futContractsDateDown?queryStartDate=%s&queryEndDate=%s&commodityId=TXF"
                   % ((end - datetime.timedelta(days=12)).strftime("%Y%%2F%m%%2F%d"), end.strftime("%Y%%2F%m%%2F%d")))
            b = urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=30).read()
            if b[:1] == b"<":
                continue
            for enc in ("utf-8-sig", "big5", "cp950"):
                try:
                    got = pick(rows(b.decode(enc)))
                    if got:
                        break
                except Exception:
                    continue
            if got:
                break
        except Exception as e:
            print("期交所網頁抓不到（改用開放資料）", repr(e)[:80])
            break
    if not got:
        try:
            b = urllib.request.urlopen(urllib.request.Request("https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate", headers=hdr), timeout=30).read()
            txt = b.decode("utf-8-sig")
            if txt.lstrip()[:1] == "[":                      # 11/21：開放資料其實是 JSON（英文欄位），原本當 CSV 讀所以雲端抓不到
                for x in json.loads(txt):
                    if x.get("ContractCode") == "臺股期貨" and x.get("Item") == "外資及陸資":
                        d = x["Date"]
                        got[f"{d[:4]}-{d[4:6]}-{d[6:]}"] = int(str(x["OpenInterest(Net)"]).replace(",", ""))
            else:
                got = pick(rows(txt))
        except Exception as e:
            print("讀不到外資台指期未平倉（略過）", repr(e)[:80])
            return None
    if not got:
        return None
    ds = sorted(got)
    d = ds[-1]
    return {"date": d, "net": got[d], "chg": (got[d] - got[ds[-2]]) if len(ds) >= 2 else None}


def r2(x):
    return None if x is None else round(x, 2)


def at_limit_up(s):
    """今天收在漲停價（台股 10%、升降單位依價位；新股前 5 天不算）。用還原後的前一日收盤 pc 推算。"""
    pc, c = s.get("pc"), s.get("close")
    if not pc or not c or s.get("new"):
        return False
    raw = pc * 1.1                                       # 11/19 Opus 審查：升降單位要用「漲停價所在的價位」決定（昨收 93 → 漲停 102.0，不是 102.3）
    tick = 0.01 if raw < 10 else 0.05 if raw < 50 else 0.1 if raw < 100 else 0.5 if raw < 500 else 1 if raw < 1000 else 5
    lim = int(raw / tick + 1e-9) * tick
    return c >= lim - 1e-6


def strong_flags(stocks, live, us=False):
    """11/18 使用者＋Opus 顧問：本週強勢／今日強勢標籤（只加標籤與欄位 w5／vr／vd／a20，不改五種型態）。
    本週強勢＝近 5 日（含今日）累計漲幅 ≥10% 且比全市場中位數多 ≥5 點、近 5 日均量 ≥ 前 20 日均量 1.5 倍、近 5 日均成交值 ≥5 千萬。
    11/19 使用者選 B：成交值前 100 名的大型股另用「近 5 日漲 ≥5% 且贏大盤 3 點」（不設量能），標「本週強勢（大型）」，點本週強勢股鈕一起列出。
    今日強勢＝今日漲幅 ≥5% 且比全市場中位數多 ≥3 點、近 5 日均成交值 ≥5 千萬（11/18 使用者：今日強勢不設量能條件，等量出來就太晚）。
    「站上 20 日線」不是條件（使用者 11/18），改成篩選頁可勾選（欄位 a20）。
    盤中：今日量先按已開盤時間比例推估全日量；09:30 前不標今日強勢；盤中標過的，漲幅還在 3% 以上就保留（避免標籤來回跳）。"""
    import datetime
    tw = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    frac, partial = 1.0, False
    if live and str(live.get("date", "")) == tw.strftime("%Y-%m-%d") and tw.weekday() < 5 and tw.hour * 60 + tw.minute < 13 * 60 + 35:
        # 11/19 Opus 審查：凌晨 06:00 官方資料還沒出來時，盤中暫時價其實是前一天的，日期不等於台灣今天就不算盤中（否則今日強勢整批消失）
        try:
            hh, mm = [int(x) for x in str(live.get("hms", "13:30")).split(":")[:2]]
            m = max(hh * 60 + mm - 9 * 60, 1)
            frac, partial = min(max(m / 270, 0.1), 1.0), True
        except Exception:
            pass
    TV_LIQ, TV_MIN = (1e6, 5e6) if us else (1e7, 5e7)        # 美股用美元：成交值 ≥100 萬美元才算進市場中位數、近 5 日均成交值 ≥500 萬美元才標（台股 1 千萬／5 千萬台幣）
    liq = [s for s in stocks.values() if s.get("_s") and s["_s"]["tv"] >= TV_LIQ]
    def med(xs):
        xs = sorted(xs); n = len(xs)
        return 0 if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)
    m5 = med([s["_s"]["w5"] for s in liq]); m1 = med([s["chg"] for s in liq])
    big = {c for c, _ in sorted(((c, s["_s"]["tv5"]) for c, s in stocks.items() if s.get("_s")), key=lambda z: -z[1])[:100]}   # 11/19 使用者：大型股（近 5 日均成交值前 100 名）另用較低門檻，不然永遠看不到大型股
    prev = set()
    if partial:
        try:
            prev = set(cached("tdprev", None, set()) or [])
        except Exception:
            prev = set()
    tdnow = []
    for code, s in stocks.items():
        x = s.pop("_s", None)
        if not x:
            continue
        vt = x["vt"] / frac if partial else x["vt"]
        v5 = (x["v5"] * 5 - x["vt"] + vt) / 5 if partial else x["v5"]
        s["w5"] = round(x["w5"], 1)
        s["vr"] = round(v5 / x["v20"], 1) if x["v20"] > 0 else None
        s["vd"] = round(vt / x["vp5"], 1) if x["vp5"] > 0 else None
        s["a20"] = x["a20"]
        if x["tv5"] < TV_MIN:
            continue
        lu = (not us) and at_limit_up(s)                  # 11/18 使用者：一字鎖死／漲停的股票沒有量是正常的，量能條件放行
        if x["w5"] >= 10 and x["w5"] - m5 >= 5 and ((s["vr"] and s["vr"] >= 1.5) or lu):
            s["tags"].append("本週強勢")
        elif code in big and x["w5"] >= 5 and x["w5"] - m5 >= 3:
            s["tags"].append("本週強勢（大型）")
        up = s["chg"] >= 5 and s["chg"] - m1 >= 3
        keep = partial and code in prev and s["chg"] >= 3 and s["chg"] - m1 >= 1
        if (up or keep) and not (partial and tw.hour * 60 + tw.minute < 9 * 60 + 30):
            s["tags"].append("今日強勢（盤中）" if partial else "今日強勢")
            tdnow.append(code)
    if partial:
        cached("tdprev", tdnow, None)


def fetch_shares():
    """上市公司已發行普通股數（證交所開放資料 t187ap03_L）。排除 91 開頭的 TDR；抓不到回傳 None。"""
    import urllib.request
    for k in range(3):
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", headers={"User-Agent": "Mozilla/5.0"}), timeout=40).read().decode("utf-8"))
            out = {}
            for r in j:
                c = str(r.get("公司代號", "")).strip()
                try:
                    n = float(r.get("已發行普通股數或TDR原股發行股數", 0))
                except (ValueError, TypeError):
                    continue
                if len(c) == 4 and c.isdigit() and not c.startswith("91") and n > 0:
                    out[c] = n
            if len(out) > 500:
                return out
        except Exception:
            time.sleep(2)
    return None


def index_weights(stocks, shares, idx_prev, top=100):
    """11/19 使用者：權值股（上市，對應加權指數）。比重＝前一日未還原收盤×已發行股數÷同一份清單的市值合計；
    貢獻點數＝比重×今日漲跌幅（未還原，和指數一致）×前一日指數。漲跌幅超過 10.5%（分割、減資等，指數會調整除數）改用還原後的漲跌幅。
    只把前 top 名寫進個股（wt 比重%、wc 貢獻點數），回傳摘要（全部上市股的貢獻合計＝大盤約變動點數）。"""
    rows = []
    for code, s in stocks.items():
        w = s.pop("_w", None)
        if not w or not shares or not idx_prev or code not in shares or s.get("new"):
            continue
        pc, c = w
        if pc <= 0 or c <= 0:
            continue
        chg = 0.0 if s.get("stale") else (c / pc - 1)
        if abs(chg) > 0.105:
            chg = (s.get("chg") or 0) / 100
        rows.append((pc * shares[code], chg, code))
    tot = sum(r[0] for r in rows)
    if not rows or tot <= 0:
        return None
    rows.sort(reverse=True)
    allc = 0.0
    for i, (cap, chg, code) in enumerate(rows):
        con = cap / tot * chg * idx_prev
        allc += con
        if i < top:
            stocks[code]["wt"] = round(cap / tot * 100, 3)
            stocks[code]["wc"] = round(con, 1)
    return {"n": len(rows), "cap": round(tot / 1e12, 2), "all": round(allc, 1), "idx": idx_prev}


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
    groups = list(csv.DictReader(open(os.path.join(ROOT, "data", ("groups_us_all.csv" if os.path.exists(os.path.join(ROOT, "data", "groups_us_all.csv")) else "groups_us.csv") if us else "groups_tw_all.csv" if full else "groups_tw.csv"), encoding="utf-8")))
    if full:
        os.makedirs(os.path.join(OUT, "s"), exist_ok=True)

    di = {d: i for i, d in enumerate(all_dates)}
    nbias = cached("nbias", news_bias(), {}) if full and not us else {}
    mtoday = cached("mtoday", mops_today(all_dates), set()) if full and not us else set()
    trows = {}                                            # 11/18 法人目標價（代號 → 該檔所有具名目標價列）
    if full and not us and os.environ.get("SHOW_TARGETS") == "1":     # 11/18 使用者：目標價先不上線（預設關閉，設環境變數才開）
        for r_ in (cached("targets", target_rows(), []) or []):
            trows.setdefault(r_["c"], []).append(r_)
    usfin = {}
    if us:                                                  # 11/18 美股季財報（SEC，scripts/us_fin.py）：K 線視窗「消息」分頁、「三率三升」標籤
        try:
            import us_fin
            usfin = {c: us_fin.view(r) for c, r in json.load(open(os.path.join(ROOT, "data", "us", "fin.json"))).items()}
        except Exception as e:
            print("美股財報資料讀不到（略過）", repr(e)[:80])
    revs, epss, mgs, epsy = {}, {}, {}, {}                           # 11/16 使用者：月營收創新高／年增新高、消息分頁的月營收（scripts/revenue.py）
    if full and not us:
        try:
            import revenue, eps as EPS
            revs = revenue.summary()
            epss = EPS.summary()
            epsy = EPS.ytd()                          # 11/18 使用者：今年累計 EPS vs 去年同期、去年全年
            import margins
            mgs = margins.summary()                   # 11/17 使用者：季營收（近三季）、三率、「三率三升」標籤
            os.makedirs(os.path.join(OUT, "f"), exist_ok=True)
        except Exception as e:
            print("月營收讀取失敗（略過）", repr(e)[:80])
    # 管理者自己畫的型態（台股）：有畫的股票，以管理者的判斷取代系統的幾何形態
    adm = {}
    if full and not us:
        try:
            import urllib.request
            site = os.environ.get("SITE_URL", "https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev").rstrip("/")
            adm = cached("adm", json.loads(urllib.request.urlopen(urllib.request.Request(site + "/api/draw-list?span=1", headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()), {})
        except Exception as e:
            print("讀不到管理者畫線（沿用上次）", repr(e)[:80])
            adm = cached("adm", None, {})
    if us:
        try:
            adm = json.load(open(os.path.join(ROOT, "data", "us", "draw.json"), encoding="utf-8"))
        except Exception:
            pass
    stocks, missing = {}, []
    for g in groups:
        code = g["代號"]
        raw = [by[code][d] for d in sorted(by.get(code, {}))] if code in by else []
        if raw and len(raw) < 40 and di.get(raw[-1]["d"], -1) >= len(all_dates) - 5 and di.get(raw[0]["d"], 0) >= len(all_dates) - 60:
            # 11/16 使用者選 B：剛上市櫃（不到 40 根）也顯示——價格、漲跌、成交值、K 線，型態標「新股」，不算進五種型態統計；滿 40 根自動改正常分析
            T = len(raw) - 1
            stocks[code] = {
                "code": code, "name": g["名稱"], "industry": g.get("產業別") or g.get("官方產業別"), "group": gl_of(g)[0], "groups": gl_of(g),
                "conf": g.get("把握度", "U"), "market": mk.get(code), "state": "新股", "sub": None, "tags": [f"上市櫃第{T + 1}天"], "geo": [], "candle": [],
                "close": raw[T]["c"], "pc": raw[T - 1]["c"] if T else None,
                "r5": [r2((raw[i]["c"] / raw[i - 1]["c"] - 1) * 100) for i in range(max(1, T - 4), T + 1)],
                "chg": r2((raw[T]["c"] / raw[T - 1]["c"] - 1) * 100) if T else 0, "vol": round(raw[T]["v"] / 1000), "new": 1}
            rows = [[di[b["d"]], b["o"], b["h"], b["l"], b["c"], round(b["v"] / 1000), round(b.get("f", 1), 5)] for b in raw]
            if full:
                with open(os.path.join(OUT, "s", code + ".json"), "w") as f:
                    json.dump({"bars": rows}, f, separators=(",", ":"))
            else:
                stocks[code]["bars"] = rows
            continue
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
        geo = [g for g in PT.detect_geometry(bars, T) if g["status"] in ("confirmed", "near", "forming", "hist")]   # hist＝島型反轉第 11～30 天，只畫在圖上
        draw_upd = []
        if code in adm:                                # 管理者畫過：比對時間範圍
            geo, draw_upd = filter_by_drawings(geo, bars, adm[code])
        chans = PT.detect_channels(bars, T)             # 趨勢通道（長、短各一）：獨立欄位，不進形態打架；和楔形／三角形同時成立只留最後碰線日期較近的（相同留通道）
        chan = chans[0] if chans else None
        if chan:
            for w in [g for g in geo if "楔形" in g["kind"] or "三角形" in g["kind"]]:
                wl = max([i for i, _ in w["pts"] if i != T] or [-1])
                if wl > chan["last_touch"]:
                    chan, chans = None, []
                    break
            if chan:
                geo = [g for g in geo if not ("楔形" in g["kind"] or "三角形" in g["kind"])]
        state, tags, sub = E.apply_patterns(state, tags, sub, geo)
        if chan:                                       # 標記（個股視窗上方的小標籤）：上升趨勢通道／（突破上緣）
            tags = list(tags) + [chan["kind"] + ("" if chan["status"] == "inchan" else "（突破上緣）" if chan["side"] > 0 else "（跌破下緣）")]
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
        for dw in adm.get(code, []):
            tags.append("✏️" + (dw["name"] if isinstance(dw, dict) else dw))   # 管理者標註
        # KD(9,3,3) 高低檔鈍化：K 值連續 ≥3 日在 80 以上／20 以下（以還原價計算）
        k_, d_ = 50.0, 50.0
        run_hi = run_lo = 0
        Ks, Ds = [], []
        for i in range(len(bars)):
            lo9 = min(b["l"] for b in bars[max(0, i - 8): i + 1])
            hi9 = max(b["h"] for b in bars[max(0, i - 8): i + 1])
            rsv = 50.0 if hi9 == lo9 else (bars[i]["c"] - lo9) / (hi9 - lo9) * 100
            k_ = 2 / 3 * k_ + rsv / 3
            d_ = 2 / 3 * d_ + k_ / 3
            Ks.append(k_); Ds.append(d_)
            run_hi = run_hi + 1 if k_ >= 80 else 0
            run_lo = run_lo + 1 if k_ <= 20 else 0
        if run_hi >= 1:                              # 11/14 使用者：K 一碰到 80 以上就算高檔鈍化（不用連 3 天）
            tags.append("KD高檔鈍化")
        if run_lo >= 1:                              # K 一跌到 20 以下就算低檔鈍化
            tags.append("KD低檔鈍化")
        tags += dmi_tags(bars, Ks, Ds)
        # 11/15 使用者：短線急漲又 KD 高檔＝過熱、不要追（只標在個股，不放篩選頁）：有「3日急漲」（≥20%）且 KD高檔鈍化
        if "KD高檔鈍化" in tags and any(t.startswith("3日急漲") for t in tags):
            tags.append("短線過熱勿追")               # DMI 標籤（11/15 使用者＋Opus 顧問定的公式，見 dmi_tags）
        if len(bars) >= 10:                          # 11/14 使用者：近 10 個交易日最低點到現價漲 ≥30%＝近日反彈強勁（額外標籤，不改變原有型態／標籤）
            lo10 = min(b["l"] for b in bars[-10:])
            if lo10 > 0 and bars[-1]["c"] / lo10 - 1 >= 0.30:
                tags.append("近日反彈強勁")
        if code in nbias:                            # 11/16 使用者：近 7 天新聞 AI 判斷偏多／偏空（見 news_bias）
            tags.append(nbias[code])
        if code in mtoday:
            tags.append("今天有重訊")
        rv = revs.get(code)
        if rv:
            if rv["revHi"]:
                tags.append("月營收創新高")
            if rv["yoyHi"]:
                tags.append("年增新高")
        if mgs.get(code, {}).get("m3"):
            tags.append("三率三升")
        if us and usfin.get(code, {}).get("m3"):
            tags.append("三率三升")
        st = {
            "code": code, "name": g["名稱"], "industry": g.get("產業別") or g.get("官方產業別"), "group": gl_of(g)[0], "groups": gl_of(g),
            "conf": g.get("把握度", "U"),
            "market": mk.get(code), "state": state, "sub": sub, "tags": tags,
            "close": raw[T]["c"],
            # 11/17 Fable 審查：除權息當天要用「還原後的參考價」算漲跌（原本用沒還原的昨收，除息日會顯示假下跌、誤判跌停）
            "pc": r2(raw[T - 1]["c"] * raw[T - 1]["f"] / raw[T]["f"]) if T else None,     # 前一日收盤（前端算漲跌金額、漲跌停；已換成今天的除權息基準）
            "r5": [r2((bars[i]["c"] / bars[i - 1]["c"] - 1) * 100) for i in range(max(1, T - 4), T + 1)],   # 近 5 日每日漲跌幅（相對抗跌族群的「近 5 日也抗跌」，用還原價）
            "chg": r2((bars[T]["c"] / bars[T - 1]["c"] - 1) * 100) if T else 0,
            "vol": round(raw[T]["v"] / 1000),
        }
        if us and code in usfin:
            st["fn"] = 1                                 # 有季財報資料：前端打開「消息」分頁
        if full and not us and T >= 1 and mk.get(code) == "TWSE":
            st["_w"] = (raw[T - 1]["c"], raw[T]["c"])        # 11/19 權值股：加權指數不還原除息，所以用「沒還原」的前一日與今日收盤
        am_ = asof_m.get(mk.get(code))
        if am_ and raw[T]["d"] < am_:                    # 11/17 Fable 審查：停牌股（資料日比市場最新日舊）標資料日期，不把舊漲跌當今天的
            st["stale"] = raw[T]["d"][5:]
            st["chg"], st["pc"], st["r5"] = 0, raw[T]["c"], [0]
            tags.append(f"停牌（資料至{raw[T]['d'][5:]}）")
        if full and T >= 25 and "stale" not in st:          # 11/18 本週／今日強勢（Opus 顧問定案）：先記每檔的原始數字，全部跑完再用市場中位數判斷
            try:
                vs = [b["v"] for b in raw]
                tv5 = sum(raw[i]["v"] * raw[i]["c"] for i in range(T - 4, T + 1)) / 5
                st["_s"] = {"w5": (bars[T]["c"] / bars[T - 5]["c"] - 1) * 100, "v5": sum(vs[T - 4:T + 1]) / 5, "v20": sum(vs[T - 24:T - 4]) / 20,
                            "vp5": sum(vs[T - 5:T]) / 5, "vt": vs[T], "tv5": tv5, "a20": 1 if bars[T]["c"] >= ma[20][T] else 0, "tv": raw[T]["v"] * raw[T]["c"]}
            except Exception:
                pass
        dn_ = dmi_now(bars)
        if dn_:
            st["dmi"] = dn_                              # DMI 篩選頁的「DMI差值」「ADX」欄
        if draw_upd:
            st["drawUpd"] = draw_upd                     # 系統的形態已經把管理者的線往後補完（「我的畫線」顯示「型態已更新！」）
        d_T = bars[T]["d"]
        st["geo"] = [{"kind": g["kind"], "dir": g["dir"], "status": g["status"], "day": g["day"],
                      "neck": r2(R(g["neck"], d_T)) if g["neck"] else None, "neckA": r2(g["neck"]) if g["neck"] else None,
                      "pts": [[bars[i]["d"], r2(R(p, bars[i]["d"])), r2(p)] for i, p in g["pts"]],
                      "lines": [[bars[a]["d"], r2(R(pa, bars[a]["d"])), bars[b]["d"], r2(R(pb, bars[b]["d"])), r2(pa), r2(pb)]
                                for a, pa, b, pb in g.get("lines", [])],
                      "volup": bool(g.get("volup")),
                      "stop": (r2(R(g["stop"], bars[g["rect"][0]]["d"])) if g.get("stop") else None), "stopA": (r2(g["stop"]) if g.get("stop") else None),
                      "rect": ([bars[g["rect"][0]]["d"], bars[g["rect"][1]]["d"], r2(R(g["rect"][2], bars[g["rect"][0]]["d"])), r2(R(g["rect"][3], bars[g["rect"][0]]["d"])), r2(g["rect"][2]), r2(g["rect"][3])] if g.get("rect") else None)} for g in geo]
        for chan in chans:
            st["geo"].append({"kind": chan["kind"], "dir": chan["dir"], "status": chan["status"], "day": chan["day"], "neck": None, "neckA": None,
                              "pts": [[bars[i]["d"], r2(R(p, bars[i]["d"])), r2(p)] for i, p in chan["pts"]],
                              "lines": [[bars[a]["d"], r2(R(pa, bars[a]["d"])), bars[b]["d"], r2(R(pb, bars[b]["d"])), r2(pa), r2(pb)] for a, pa, b, pb in chan["lines"]],
                              "volup": False, "stop": None, "stopA": None, "rect": None,
                              "L": chan["L"], "width": chan["width"], "move": chan["move"], "r2": chan["r2"], "pos": chan["pos"], "acc": chan["acc"], "side": chan["side"], "which": chan["which"]})
        gfull = st["geo"]
        if not us:                                       # 台股：data.js 只留篩選要用的欄位，畫圖座標放進個股檔 s/<代號>.json（點開才下載）
            st["geo"] = [{k: g[k] for k in ("kind", "dir", "status", "day", "pos", "acc", "side", "which") if k in g} for g in gfull]
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
                json.dump({"bars": rows, **({"geo": gfull} if not us else {})}, f, separators=(",", ":"))
            fin = dict(rv or {})                         # 消息分頁左欄：月營收近 6 個月＋單季 EPS 近 3 季
            if code in epss:
                fin["eps"] = epss[code]
                if code in epsy:
                    fin["ey"] = epsy[code]
            if code in mgs:
                fin["q"] = mgs[code]["q"]
            if trows.get(code):
                try:
                    import targets as TG
                    tp = TG.summarize(trows[code], st["close"], time.time())
                    if tp:
                        fin["tp"] = tp
                except Exception as e:
                    print("目標價彙總失敗", code, repr(e)[:60])
            if fin:
                with open(os.path.join(OUT, "f", code + ".json"), "w") as f:
                    json.dump(fin, f, ensure_ascii=False, separators=(",", ":"))
        else:
            st["bars"] = rows
        stocks[code] = st

    val = None                                           # 11/18 使用者：本益比／股價淨值比／殖利率（官方收盤後資料，固定收盤值，不隨盤中跳動）
    if full and not us:
        try:
            import valuation, datetime
            val = cached("val", valuation.fetch((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).strftime("%Y%m%d")), None)   # 抓不到就沿用線上上次那份（日期會照實顯示）
            if val:
                try:
                    import eps as EPS4
                    e4 = EPS4.summary(n=4)
                except Exception:
                    e4 = {}
                nv = 0
                for code, st in stocks.items():
                    r = val["m"].get(code)
                    if not r:
                        continue
                    pe, pb, dy, fq = r
                    st["pe"], st["pb"], st["dy"] = pe, pb, dy
                    if fq:
                        st["pq"] = fq
                    if pe is None:
                        q4 = e4.get(code, [])
                        if len(q4) == 4 and sum(x[1] for x in q4) <= 0:
                            st["pl"] = 1              # 近四季合計虧損
                    nv += 1
                print("本益比資料", val["date"], "檔數", nv)
        except Exception as e:
            print("本益比讀取失敗（略過）", repr(e)[:80])
    gl = collections.OrderedDict()
    for st in stocks.values():
        for gname in st["groups"]:                       # 雙族群的股票，兩個族群都會計入
            g = gl.setdefault(gname, {"name": gname, "n": 0,
                                      "counts": {s: 0 for s in STATES}, "stocks": [], "first": [],
                                      "weak_pull": 0, "weak_break": 0, "weak_strong": 0})
            if st["state"] in STATES:                    # 新股不算進族群檔數與五種型態百分比，但會出現在族群的股票列表
                g["n"] += 1
                g["counts"][st["state"]] += 1
            if st["sub"] == "回檔走弱":
                g["weak_pull"] += 1
            elif st["sub"] == "破底走弱":
                g["weak_break"] += 1
            g["stocks"].append(st["code"])
            if "突破第1根" in st["tags"]:
                g["first"].append(st["code"])
    glist = sorted(gl.values(), key=lambda g: (g["n"] < 5, -(g["counts"]["轉強"] + g["counts"]["型態好"]) / max(g["n"], 1), -g["n"]))

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
    if full:
        strong_flags(stocks, live, us)
    wtm = None
    if full and not us:
        try:
            sh_ = fetch_shares()
            sh_ = cached("shares", sh_, None) if sh_ else cached("shares", None, None)
            tw_ = (index.get("TWII") or {}).get("bars") or []
            ip_ = next((b[4] for b in reversed(tw_) if b[0] < asof), None)
            wtm = index_weights(stocks, sh_, ip_)
            ia_ = next((b[4] for b in tw_ if b[0] == asof), None)
            if wtm and not live and ia_ is not None and ip_ and abs(wtm["all"] - (ia_ - ip_)) > 5:     # 11/19 Opus：官方資料日，全部上市股的貢獻加總要貼近實際指數漲跌（實測差 1 點內）；差太多代表股數或價格有問題，寧可不顯示
                print(f"  權值股比重驗證失敗：加總 {wtm['all']} 點、實際 {round(ia_ - ip_, 1)} 點，不顯示")
                for s_ in stocks.values():
                    s_.pop("wt", None); s_.pop("wc", None)
                wtm = None
        except Exception as e:
            print("權值股比重略過", repr(e)[:80])
            for s_ in stocks.values():
                s_.pop("_w", None)
    out = {"wtm": wtm, "valDate": (val or {}).get("date"), "live": live, "asof": asof, "asofM": asof_m, "dates": all_dates, "total": total, "groups": glist, "stocks": stocks, "missing": missing, "index": index}
    if mode == "all":
        # 11/17 Fable 審查：盤中（15:00 前，這兩項資料要收盤後才公布）不重抓，沿用上次發布的；抓到新的才更新
        import datetime
        tw = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
        hold = bool(live) and str(live.get("date", "")) == tw.strftime("%Y-%m-%d") and tw.weekday() < 5 and tw.hour < 15
        inst = (cached("inst", None, None) if hold else None) or (lambda v: cached("inst", v, None) if v else None)(fetch_inst())
        if inst:
            out["inst"] = inst
        fut = (cached("fut", None, None) if hold else None) or (lambda v: cached("fut", v, None) if v else None)(fetch_fut_foreign())
        if fut:
            out["fut"] = fut
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
