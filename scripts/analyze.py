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


def news_bias():
    """11/16 使用者：近 7 天新聞 AI 判斷（scripts/news.py → news-data 分支）彙總成「近期消息偏多／偏空」。
    只算「事件」「法人」（投顧點名、盤勢文不算）；同一檔同一天同方向只算一次（多家轉載不灌票）；利多比利空多 2 則以上＝偏多，反之偏空。"""
    import urllib.request
    try:
        with urllib.request.urlopen("https://raw.githubusercontent.com/jrnobleyou-lgtm/tw-stock-pattern/news-data/items.json", timeout=20) as r:
            items = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("新聞資料讀不到，略過消息標籤：", e)
        return {}
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
    today = datetime.date.today()
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
            got = pick(rows(b.decode("utf-8-sig")))
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
    nbias = news_bias() if full and not us else {}
    revs, epss = {}, {}                           # 11/16 使用者：月營收創新高／年增新高、消息分頁的月營收（scripts/revenue.py）
    if full and not us:
        try:
            import revenue, eps as EPS
            revs = revenue.summary()
            epss = EPS.summary()
            os.makedirs(os.path.join(OUT, "f"), exist_ok=True)
        except Exception as e:
            print("月營收讀取失敗（略過）", repr(e)[:80])
    # 管理者自己畫的型態（台股）：有畫的股票，以管理者的判斷取代系統的幾何形態
    adm = {}
    if full and not us:
        try:
            import urllib.request
            site = os.environ.get("SITE_URL", "https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev").rstrip("/")
            adm = json.loads(urllib.request.urlopen(urllib.request.Request(site + "/api/draw-list?span=1", headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
        except Exception as e:
            print("讀不到管理者畫線（略過）", repr(e)[:80])
    if us:
        try:
            adm = json.load(open(os.path.join(ROOT, "data", "us", "draw.json"), encoding="utf-8"))
        except Exception:
            pass
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
        geo = [g for g in PT.detect_geometry(bars, T) if g["status"] in ("confirmed", "near", "forming", "hist")]   # hist＝島型反轉第 11～30 天，只畫在圖上
        draw_upd = []
        if code in adm:                                # 管理者畫過：比對時間範圍
            geo, draw_upd = filter_by_drawings(geo, bars, adm[code])
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
        rv = revs.get(code)
        if rv:
            if rv["revHi"]:
                tags.append("月營收創新高")
            if rv["yoyHi"]:
                tags.append("年增新高")
        st = {
            "code": code, "name": g["名稱"], "industry": g.get("產業別") or g.get("官方產業別"), "group": gl_of(g)[0], "groups": gl_of(g),
            "conf": g.get("把握度", "U"),
            "market": mk.get(code), "state": state, "sub": sub, "tags": tags,
            "close": raw[T]["c"], "pc": raw[T - 1]["c"] if T else None,     # 前一日收盤（前端算漲跌金額、漲跌停）
            "r5": [r2((raw[i]["c"] / raw[i - 1]["c"] - 1) * 100) for i in range(max(1, T - 4), T + 1)],   # 近 5 日每日漲跌幅（相對抗跌族群的「近 5 日也抗跌」）
            "chg": r2((raw[T]["c"] / raw[T - 1]["c"] - 1) * 100) if T else 0,
            "vol": round(raw[T]["v"] / 1000),
        }
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
            fin = dict(rv or {})                         # 消息分頁左欄：月營收近 6 個月＋單季 EPS 近 3 季
            if code in epss:
                fin["eps"] = epss[code]
            if fin:
                with open(os.path.join(OUT, "f", code + ".json"), "w") as f:
                    json.dump(fin, f, ensure_ascii=False, separators=(",", ":"))
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
    if mode == "all":
        inst = fetch_inst()
        if inst:
            out["inst"] = inst
        fut = fetch_fut_foreign()
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
