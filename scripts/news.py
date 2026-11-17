"""個股新聞：抓 8 家財經媒體（含 Yahoo股市，11/16 使用者要求加回）的免費文章 → 讀全文 → AI 判斷對個股是上修（利多）／持平／下修（利空）。

用法：news.py <資料夾>
  資料夾＝news-data 分支的工作目錄，裡面放：
    seen.json          看過的文章（網址雜湊 → 時間），每篇只判斷一次
    tries.json         暫時抓不到的文章重試次數（最多 3 次）
    items.json         近 30 天有判斷結果的文章
    s/<0-63>.json      依股票代號分包（Worker 的 /api/news 讀這個）
    meta.json          本輪時間、各家篇數、額度用完到幾點
規則（使用者定）：不花錢；付費、要登入會員的文章不抓（抓不到全文就整篇跳過）；Yahoo 不用；AI 要讀全文。
AI：Gemini 免費 API（GEMINI_API_KEY），每輪向 Google 取型號清單，自動挑最新正式版 flash-lite、再 flash（新型號第一次用前先跑 8 篇自我檢查；抓不到清單退回寫死預設；全部被停用就寄信）；先 flash-lite、再 flash（11/16 實測：flash 偏樂觀；GitHub Models 已被 GitHub 停掉，Groq／Cloudflare 免費模型品質也不夠，都不用）。兩個都用完就當輪不判，等額度回來再補。
2026-11-16 依 Fable 審查修正：編碼錯誤、AI 回傳格式防呆、股票比對（名稱／代號須出現在文中、撞名清單）、
篇號用 A1…、限流等待、全文上限 6000 字、文章時間、先濾掉沒提到上市櫃的文章、每批存檔、同標題去重。"""
import concurrent.futures as cf, csv, email.utils, hashlib, html, json, os, re, subprocess, sys, time
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
KEEP_DAYS, NSHARD = 30, 64
BATCH_N, BATCH_CHARS, TEXT_MAX, RUN_MAX = 10, 30000, 6000, 80      # 每批最多 10 篇或 3 萬字；每篇最多 6000 字；每輪最多判 80 篇
GAP, WAIT_429 = 7, 50                                               # 批與批之間等 7 秒；被限流先等 50 秒再試
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
TW = timezone(timedelta(hours=8))
AMBIG = {"三星", "世界", "統一", "大同", "國產", "聯合", "中華", "精華", "台灣", "全球", "亞洲", "大成", "中興", "國泰", "富邦", "新光",
         "遠東", "長榮", "華南", "第一", "台新", "永豐", "元大", "開發", "宏達", "光寶", "東元", "聲寶", "中鋼", "台塑", "南亞"}
SRC_N = {}


def get(u, t=20):
    r = subprocess.run(["curl", "-sS", "-m", str(t), "-L", "-A", UA, u], capture_output=True)
    return r.stdout.decode("utf-8", "replace")


def strip(s):
    return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", s or "")).strip()


def parse_time(s):
    """RSS 的 pubDate 或 ISO 時間；沒時區的當台灣時間。"""
    s = (s or "").strip()
    if not s:
        return 0
    try:
        return int(email.utils.parsedate_to_datetime(s).timestamp())
    except (TypeError, ValueError, IndexError):
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int((d if d.tzinfo else d.replace(tzinfo=TW)).timestamp())
    except ValueError:
        return 0


def rss(u):
    out = []
    for it in re.findall(r"<item>(.*?)</item>", get(u), re.S):
        f = lambda t: (lambda m: strip(m.group(1)) if m else "")(re.search(rf"<{t}[^>]*>(.*?)</{t}>", it, re.S))
        out.append({"title": f("title"), "link": f("link") or f("guid"), "t": parse_time(f("pubDate"))})
    return out


# ───────── 各家媒體的文章列表 ─────────
def src_udn():
    out = []
    for c in (5590, 5591, 5588):                      # 股市、產業、要聞
        out += [dict(a, src="經濟日報") for a in rss(f"https://money.udn.com/rssfeed/news/1001/{c}?ch=money") if "/vipstory/" not in a["link"]]
    return out


def src_ctee():
    return [dict(a, src="工商時報") for a in rss("https://www.ctee.com.tw/rss_web/livenews/stock")]


def src_cnyes():
    out = []
    for cat in ("tw_stock", "tw_quo"):
        d = json.loads(get(f"https://api.cnyes.com/media/api/v1/newslist/category/{cat}?limit=30"))["items"]["data"]
        for x in d:
            if str(x.get("payment")) != "0":          # 鉅亨付費文章
                continue
            txt = re.sub(r"<[^>]+>", "", html.unescape(x.get("content") or ""))
            out.append({"src": "鉅亨網", "title": x["title"], "link": f"https://news.cnyes.com/news/id/{x['newsId']}", "t": int(x.get("publishAt") or 0), "text": txt})
    return out


def src_moneydj():
    return [dict(a, src="MoneyDJ") for a in rss("https://www.moneydj.com/KMDJ/RssCenter.aspx?svc=NR&fno=1&arg=MB010000") if "5850web" not in a["link"]]


def src_cna():
    out = []
    for cat in ("afe", "asc"):                        # 產經、證券
        for i in list(dict.fromkeys(re.findall(rf'href="/news/{cat}/(\d+)\.aspx"', get(f"https://www.cna.com.tw/list/{cat}.aspx"))))[:20]:
            out.append({"src": "中央社", "title": "", "link": f"https://www.cna.com.tw/news/{cat}/{i}.aspx", "t": 0})
    return out


def src_uanalyze():
    seen, out = set(), []
    for u, t in re.findall(r'href="(https://uanalyze\.com\.tw/articles/\d+)"[^>]*>(.*?)</a>', get("https://uanalyze.com.tw/"), re.S):
        t = re.sub(r"<[^>]+>|\s+", " ", t).strip()
        if t and u not in seen:
            seen.add(u)
            out.append({"src": "優分析", "title": html.unescape(t), "link": u, "t": 0})
    return out


def src_technews():
    return [dict(a, src="科技新報") for a in rss("https://finance.technews.tw/feed/")]


def src_yahoo():
    return [dict(a, src="Yahoo股市") for a in rss("https://tw.stock.yahoo.com/rss?category=tw-market")]


SOURCES = (src_udn, src_ctee, src_cnyes, src_moneydj, src_cna, src_uanalyze, src_technews, src_yahoo)


# ───────── 內文（抓不到全文＝付費／會員文章，跳過） ─────────
def fulltext(a):
    """回傳 (內文, 狀態)：ok／paid（有網頁但沒全文＝付費、會員、選單）／err（暫時抓不到，下輪重試）。"""
    try:
        raw = "" if a.get("text") else get(a["link"])
        if a.get("text"):
            return a["text"], "ok"
        if len(raw) < 500:
            return "", "err"
        import trafilatura
        meta = trafilatura.extract_metadata(raw)
        txt = trafilatura.extract(raw) or ""
        if not a["title"] and meta and meta.title:
            a["title"] = re.sub(r"\s*[|｜-]\s*(中央社|CNA).*$", "", meta.title).strip()
        if not a["t"]:                                 # 網頁裡的完整發布時間
            m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', raw) or re.search(r'property="article:published_time"\s+content="([^"]+)"', raw)
            a["t"] = parse_time(m.group(1)) if m else 0
            if not a["t"] and meta and meta.date:
                a["t"], a["day"] = parse_time(meta.date[:10] + "T12:00:00"), 1   # 只有日期：前端不顯示時分
        m = re.search(r"本文共\s*(\d+)\s*字", raw)
        if m and len(txt) < int(m.group(1)) * 0.6:    # 經濟日報：只看得到部分＝付費／會員
            return "", "paid"
        if "登入" in txt[:200] and "繁體版" in txt[:200]:
            return "", "paid"
        return txt, "ok"
    except Exception as e:
        print(f"內文失敗 {a['link']}：{e}", file=sys.stderr)
        return "", "err"


def good(txt):
    return len(re.findall(r"[一-鿿]", txt)) >= 150


# ───────── 股票清單與比對 ─────────
def norm(n):
    return re.sub(r"\*|-KY|-創|\s", "", n or "")


def stocks_map():
    names, codes = {}, {}
    for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8")):
        n = norm(r["名稱"])
        codes[r["代號"]] = n
        names.setdefault(n, r["代號"])
    return names, codes


def priority_codes():
    """優先判斷的股票：使用者的關注清單（data/watchlist_tw.txt）＋成交值前 100 名（讀線上 data.js）。11/17 使用者：全部都判，但排隊先判這些。"""
    pri = set()
    try:
        for ln in open(os.path.join(ROOT, "data", "watchlist_tw.txt"), encoding="utf-8"):
            c = ln.split("#")[0].split(",")[0].strip()
            if c:
                pri.add(c)
    except Exception as e:
        print("關注清單讀不到（略過）：", repr(e)[:80], file=sys.stderr)
    try:
        r = subprocess.run(["curl", "-sS", "-m", "60", os.environ.get("SITE_URL", "https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev") + "/data.js"], capture_output=True, text=True)
        d = json.loads(r.stdout[r.stdout.index("{"):r.stdout.rindex("}") + 1])
        top = sorted(d["stocks"].values(), key=lambda s: -((s.get("close") or 0) * (s.get("vol") or 0)))[:100]
        pri |= {s["code"] for s in top}
    except Exception as e:
        print("成交值前 100 名讀不到（略過）：", repr(e)[:80], file=sys.stderr)
    return pri


def is_priority(a, pri, codes):
    txt = a["title"] + "\n" + a["text"]
    for c in pri:
        n = codes.get(c)
        if (n and (len(n) >= 3 or n not in AMBIG) and n in txt) or re.search(r"[（(]" + c + r"[）)\-]", txt):
            return True
    return False


def mentions_any(txt, names):
    """內文有沒有出現任何上市櫃公司（名稱或「(代號」）——都沒有就不送 AI（省額度）。"""
    if re.search(r"[（(]\d{4,6}[A-Z]?[）)\-]", txt):
        return True
    return any(n in txt for n in names if len(n) >= 3 or n not in AMBIG)


def resolve(s, a, names, codes):
    """AI 給的公司 → 代號。名稱、代號互相矛盾就丟掉；名稱或代號必須真的出現在標題或內文。"""
    if not isinstance(s, dict):
        return None
    raw_c = str(s.get("code") or "").strip().upper()
    n = norm(str(s.get("name") or ""))
    byname = names.get(n)
    if raw_c in codes and byname and byname != raw_c:
        return None
    c = raw_c if raw_c in codes else byname
    if not c:
        return None
    body = a["title"] + "\n" + a["text"]
    nm = codes[c]
    if c not in body and nm not in body:
        return None
    if nm in AMBIG and c not in body and raw_c != c:   # 撞名（三星、世界、統一…）要有代號佐證
        return None
    return c


# ───────── AI 判斷 ─────────
PROMPT = """你是台股新聞分析助理。下面每篇是台灣財經新聞（標題＋內文），每篇有編號（例如 A3）。
對每篇，找出文章「主要在談」的台灣上市櫃公司（只是順便列名、只出現在選股清單或盤勢評論裡一筆帶過的不算；外國公司如三星電子、輝達不要列；最多 5 家），判斷這篇對該公司是：
上修＝利多（營收／獲利／訂單／目標價上調、需求轉強、擴產等）
持平＝中性、已公布的數字、好壞參半；只報導股價漲跌、沒有基本面原因的也算持平
下修＝利空（獲利衰退、目標價下調、砍單、風險升高等）
kind 填：事件（公司營運、財報、訂單、法說）／法人（外資、券商或投顧的研究報告有給明確目標價或調整評等、EPS 預估）／點名（節目或專欄的投顧、分析師推薦、題材，沒有給目標價）／盤面（股價漲跌、資金流向）。
請以內文為準，不要被標題的聳動語氣誤導。
以下情況一律判持平：公司宣布投資、取得資產、簽約、試車或測試達標這類里程碑，內文沒有營收、獲利、訂單金額等財務結果；多空意見並陳；法人只是預估數字、沒有調高或調低評等或目標價。
只有內文明確寫出營收／獲利成長、訂單增加、調升目標價或評等，才判上修；明確寫出衰退、砍單、調降目標價，才判下修。
公司明確表示訂單能見度延長、上調財測或出貨目標，即使沒有金額也算上修。外資報告只點名受惠股、沒給目標價或評等，kind 填點名。獲利主要來自處分資產、業外一次性收益，判持平。kind 是盤面的一律判持平。
盤勢綜述、選股清單、整理很多檔股票的文章，只列文章真正主要在談的公司，沒有就給空陣列。code 填台股代號（4～6 碼，不確定就空字串）。理由用繁體中文 25 字內。
只輸出 JSON：{"r":[{"id":"原樣的編號","stocks":[{"name":"公司簡稱","code":"代號","dir":"上修|持平|下修","kind":"事件|法人|點名|盤面","why":"理由"}]}]}，沒有主要公司就 stocks 給空陣列，每篇都要回。
"""


class Quota(Exception):
    pass


class BadBatch(Exception):
    pass


class Busy(Exception):
    pass


class Gone(Exception):                    # Google 回報這個型號不存在（已停用）
    pass


DEFAULT_MODELS = ("gemini-3.5-flash-lite", "gemini-3.5-flash")      # 抓不到型號清單時的預設；版本號低於這兩個的不用（避免清單出錯時退回舊一代）
MODEL_RE = re.compile(r"^models/gemini-(\d+(?:\.\d+)?)-flash(-lite)?$")   # 只收「正式版」：排除 preview／exp／-001／latest／tts／image／live／pro／embedding／gemma
GONE, MINFO = [], {}                                                # 本輪被 Google 回報不存在的型號；選型號過程的紀錄


def model_ver(name):
    m = re.match(r"^gemini-(\d+(?:\.\d+)?)-flash", name)
    return float(m.group(1)) if m else 0.0


def pick_models(listing, defaults=DEFAULT_MODELS):
    """由 Google 型號清單挑：最新 flash-lite → 最新 flash → 寫死預設（清單裡還在才加）。回傳 (型號串列, 沒辨識的 flash 型號)。"""
    floor = min(model_ver(m) for m in defaults)
    lite, full, odd = {}, {}, []
    for m in listing or []:
        n = m.get("name", "")
        if "generateContent" not in (m.get("supportedGenerationMethods") or ["generateContent"]):
            continue
        g = MODEL_RE.match(n)
        if not g:
            if re.search(r"flash", n) and not re.search(r"preview|exp|image|tts|live|audio|thinking|latest|-\d{3}$|gemma|embedding|omni", n):
                odd.append(n[7:])
            continue
        v = float(g.group(1))
        if v >= floor:
            (lite if g.group(2) else full)[v] = n[7:]
    out = [lite[max(lite)]] if lite else []
    out += [full[max(full)]] if full else []
    names = {m.get("name", "")[7:] for m in listing or []}
    out += [d for d in defaults if d in names and d not in out]
    return out, odd


def list_models(key):
    """向 Google 取型號清單（不佔生成額度）；失敗回 None。"""
    for u, h in (("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000", "x-goog-api-key: " + key),
                 ("https://generativelanguage.googleapis.com/v1beta/openai/models", "Authorization: Bearer " + key)):
        try:
            r = subprocess.run(["curl", "-sS", "-m", "30", u, "-H", h], capture_output=True)
            d = json.loads(r.stdout.decode("utf-8", "replace"))
            ms = d.get("models") or [{"name": "models/" + str(x.get("id", "")).replace("models/", "")} for x in d.get("data", [])]
            if ms:
                return ms
        except Exception as e:
            print("型號清單讀取失敗：", repr(e)[:100], file=sys.stderr)
    return None


def providers():
    """（名稱, 網址, 金鑰, 模型）依序嘗試：自動挑最新的 Gemini flash-lite → flash（11/17 使用者：Google 換型號要自動跟上）。"""
    out = []
    gk = os.environ.get("GEMINI_API_KEY") or ("" if os.environ.get("CI") else "proxy-injected")   # 雲端測試環境：網路代理會換成真的金鑰
    if gk:
        ms = list_models(gk)
        picked, odd = pick_models(ms) if ms else ([], [])
        MINFO.update({"listed": bool(ms), "odd": odd})
        if os.environ.get("NEWS_FORCE_MODELS"):                       # 測試用：強制指定型號（逗號分隔）
            picked = os.environ["NEWS_FORCE_MODELS"].split(",")
        if not picked:
            picked = list(DEFAULT_MODELS)
            MINFO["fallback"] = True
        out += [("Gemini", GEMINI, gk, m) for m in picked]
    return out


SELF_CHECK = [   # 自我檢查樣本（編造的短文，答案很明確）：新型號第一次上線前跑一次
    ("A1", "台積電上調全年營收展望", "台積電2330法說會宣布，受AI需求強勁帶動，上調全年營收成長預測至三成以上，並提高資本支出，下季毛利率預期優於市場預期。", 1),
    ("A2", "聯發科接獲大單訂單能見度延長", "聯發科2454表示，旗艦手機晶片獲多家客戶追加訂單，訂單能見度已延伸至明年第三季，法人預期明年獲利大幅成長。", 1),
    ("A3", "鴻海AI伺服器出貨倍增", "鴻海2317公布AI伺服器本季出貨量較上季倍增，單月營收創歷史新高，公司並調高全年展望。", 1),
    ("A4", "長榮股東會照常召開", "長榮2603今日召開例行股東會，通過去年度盈餘分配案，股利與去年相同，營運展望維持不變。", 0),
    ("A5", "友達公告董事改選結果", "友達2409公告完成董事改選，新任董事名單如公告，公司表示營運方針不變。", 0),
    ("A6", "華邦電下修全年展望", "華邦電2344法說會表示，客戶庫存調整延長，下修全年營收預測，本季毛利率將較上季明顯下滑，並調降資本支出。", -1),
    ("A7", "大立光訂單遭砍單", "大立光3008傳出主要客戶砍單，法人調降明年獲利預估，公司證實本季出貨量將較預期大幅減少。", -1),
    ("A8", "台泥因工安事件停產", "台泥1101因廠區工安事件遭主管機關勒令停工，預期本季出貨受影響，法人下修本季獲利預估。", -1),
]


def self_check(prov1):
    """拿 8 篇已知答案的樣本測一個型號：格式正確、至少回 7 篇、方向至少對 6 篇、不可把上修判成下修（或相反）。回傳 (通過, 對幾篇)。"""
    name, url, key, model = prov1
    body = PROMPT + "".join(f"\n=== {i}（自我檢查）\n標題：{ti}\n內文：{tx}\n" for i, ti, tx, _ in SELF_CHECK)
    try:
        res = call(url, key, model, body)
    except Exception as e:
        print(f"自我檢查 {model} 失敗：{repr(e)[:120]}", file=sys.stderr)
        return False, -1
    ans = {i: d for i, _, _, d in SELF_CHECK}
    got = ok = flip = 0
    for x in res:
        i = str(x.get("id")).strip()
        if i not in ans:
            continue
        got += 1
        ss = x.get("stocks") or []
        d = {"上修": 1, "持平": 0, "下修": -1}.get(ss[0].get("dir")) if ss and isinstance(ss[0], dict) else 0
        ok += d == ans[i]
        flip += d is not None and d * ans[i] == -1
    return (got >= 7 and ok >= 6 and flip == 0), ok


def call(url, key, model, body):
    req = {"model": model, "messages": [{"role": "user", "content": body}], "response_format": {"type": "json_object"}}
    r = subprocess.run(["curl", "-sS", "-m", "180", url, "-H", "Authorization: Bearer " + key, "-H", "Content-Type: application/json", "--data-binary", "@-",
                        "-w", "\n@@HTTP%{http_code}"], input=json.dumps(req).encode(), capture_output=True)
    out, _, code = r.stdout.decode("utf-8", "replace").rpartition("\n@@HTTP")
    if code[:1] == "5" or code == "000":
        raise Busy(f"HTTP {code}")
    if code == "404" or '"status": "NOT_FOUND"' in out or '"status":"NOT_FOUND"' in out:
        raise Gone(f"{model} 不存在")
    if "limit: 0" in out and ("429" in code or "RESOURCE_EXHAUSTED" in out):
        raise Gone(f"{model} 免費額度為 0")
    if '"code": 429' in out or '"code":429' in out or "RESOURCE_EXHAUSTED" in out or "RateLimitReached" in out or "rate limit" in out.lower():
        raise Quota(out[:300])
    try:
        d = json.loads(out)
        txt = d["choices"][0]["message"]["content"]
    except Exception:
        raise ValueError(f"回應不是預期格式（HTTP {code}）：" + out[:200].replace("\n", " "))
    txt = re.sub(r"^```(?:json)?|```$", "", txt.strip()).strip()
    res = json.loads(txt)
    res = res.get("r") if isinstance(res, dict) else res
    if not isinstance(res, list):
        raise ValueError("格式不對：" + txt[:100])
    return res


EV = {"busy": 0, "quota": 0}      # 本輪 AI 忙碌（503）、額度（429）次數，記到每日統計


def judge(batch, prov):
    """回傳 (結果, 用哪個 AI)。額度用完換下一個 AI；回傳格式壞掉丟 BadBatch（呼叫端拆小再送），不換 AI。"""
    body = PROMPT + "".join(f"\n=== {a['id']}（{a['src']}）\n標題：{a['title']}\n內文：{a['text'][:TEXT_MAX]}\n" for a in batch)
    while prov:
        name, url, key, model = prov[0]
        bad = 0
        for tryno in range(4):
            try:
                res = call(url, key, model, body)
                if len(res) >= len(batch) * 0.8 or tryno >= 2:   # 回來的篇數太少（可能被截斷）就重試
                    return res, f"{name} {model}"
            except Quota as e:
                EV["quota"] += 1
                if tryno == 0:
                    time.sleep(WAIT_429)               # 多半是每分鐘上限，等一下再試
                    continue
                print(f"{model} 額度用完：{e}", file=sys.stderr)
                break
            except Gone as e:                           # 型號已下架：直接換下一個並記錄
                GONE.append(model)
                print(f"{e}", file=sys.stderr)
                break
            except Busy as e:                           # AI 伺服器暫時忙：等一下再試
                EV["busy"] += 1
                print(f"{model} 暫時忙：{e}", file=sys.stderr)
                time.sleep(20)
                continue
            except Exception as e:
                bad += 1
                print(f"{model} 回傳有問題：{e}", file=sys.stderr)
                if "不是預期格式" in str(e) and bad >= 2:
                    break                               # 這個 AI 連線本身有問題：換下一個
                if bad >= 2:
                    raise BadBatch(str(e))
                time.sleep(5)
        prov.pop(0)                                    # 這個模型今天不能用了，換下一個
    if GONE:
        MINFO["fatal"] = True                          # 清單裡的型號全被 Google 回報不存在：要寄信
    raise Quota("所有 AI 都不能用")


# ───────── 主流程 ─────────
def safe(f):
    try:
        r = f()
        SRC_N[f.__name__[4:]] = len(r)
        return r
    except Exception as e:                          # 單一媒體壞掉不影響其他家
        SRC_N[f.__name__[4:]] = f"失敗：{e}"[:120]
        print(f"{f.__name__} 失敗：{e}", file=sys.stderr)
        return []


def shard(c):
    h = 0
    for ch in c:
        h = (h * 31 + ord(ch)) % 1000003
    return h % NSHARD


def tkey(t):
    return re.sub(r"[^一-鿿A-Za-z0-9]", "", t)[:18]   # 前 18 字相同＝同一篇（各家會加「｜產經」之類的尾巴）


def main(out):
    os.makedirs(os.path.join(out, "s"), exist_ok=True)
    P = lambda f: os.path.join(out, f)
    load = lambda f, d: json.load(open(P(f), encoding="utf-8")) if os.path.exists(P(f)) else d
    now = int(time.time())
    seen, tries, items, meta = load("seen.json", {}), load("tries.json", {}), load("items.json", []), load("meta.json", {})
    seen = {k: v for k, v in seen.items() if v > now - (KEEP_DAYS + 5) * 86400}
    names, codes = stocks_map()
    try:                                                # 11/16 重訊（scripts/mops.py）：不用 AI，先做，AI 沒額度也照常更新
        import mops as MO
        mo_rows = MO.run(out, codes, meta)
    except Exception as e:
        print("重訊失敗（略過）：", repr(e)[:120], file=sys.stderr)
        mo_rows = load("mops.json", [])
    daily = load("daily.json", {})                       # 11/17 使用者：每日新聞判斷統計表（比對要不要改付費 Claude Haiku），設定頁顯示
    dkey = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    day_stat = daily.setdefault(dkey, {"runs": 0, "articles": 0, "chars": 0, "batches": 0, "withStock": 0, "up": 0, "flat": 0, "down": 0, "skipped": 0, "pri": 0, "non": 0, "by": {}, "busy": 0, "quota": 0})
    day_stat["runs"] += 1
    daily = {k: v for k, v in daily.items() if k >= (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=60)).strftime("%Y-%m-%d")}
    prov = providers()
    if not prov:
        sys.exit("缺 GEMINI_API_KEY（請到 GitHub Settings → Secrets 新增）")
    day_stat.setdefault("alert", "")
    okm = meta.setdefault("model_ok", list(DEFAULT_MODELS))      # 已通過自我檢查的型號（預設的兩個視為已通過）
    prev = meta.get("models") or []
    for pv in list(prov):                                        # 新出現、沒檢查過的型號：先自我檢查，沒過就先不用（舊型號還在時）
        if pv[3] not in okm:
            ok_, n_ = self_check(pv)
            if ok_:
                okm.append(pv[3])
                day_stat["alert"] = f"新聞 AI 換了型號：{'、'.join(prev) or '（無）'} → {pv[3]}（自我檢查 {n_}/8 通過）"
            else:
                day_stat["alert"] = (f"新聞 AI 出現新型號 {pv[3]}，自我檢查沒通過（{n_}/8），先不使用" if n_ >= 0 else f"新聞 AI 試用新型號 {pv[3]}（自我檢查暫時連不上，先直接判斷看看，額度或忙碌時自動退回舊型號）")
                if n_ >= 0 and any(q[3] in okm for q in prov):
                    prov.remove(pv)                                  # 品質沒過才排除；只是暫時連不上（503）就照常排進去試，不行會自動退回舊型號（11/17 使用者要求）
    meta["models"] = [q[3] for q in prov]
    if MINFO.get("fallback"):
        day_stat["alert"] = day_stat["alert"] or "新聞 AI：讀不到 Google 型號清單，先用預設型號"
    if MINFO.get("odd"):
        day_stat["alert"] = (day_stat["alert"] + "；" if day_stat["alert"] else "") + "Google 清單有沒辨識的 flash 型號：" + "、".join(MINFO["odd"][:3])
    day_stat["models"] = meta["models"]

    def save():
        nonlocal items
        items = sorted([x for x in items if x["t"] > now - KEEP_DAYS * 86400], key=lambda x: -x["t"])
        shards = [dict() for _ in range(NSHARD)]
        for x in items:
            for s in x["ai"]:
                if s.get("k") == "盤面" or (s.get("k") == "點名" and s["d"] == 0):      # 盤面（股價漲跌）一律不顯示；投顧點名又沒利多利空：不顯示（11/17 Fable：盤面不該有上修下修）
                    continue
                lst = shards[shard(s["c"])].setdefault(s["c"], [])
                if any(tkey(y["title"]) == tkey(x["title"]) for y in lst):   # 同一篇多家轉載只留一則
                    continue
                lst.append({"t": x["t"], "day": x.get("day", 0), "src": x["src"], "title": x["title"], "link": x["link"], "d": s["d"], "k": s.get("k", ""), "w": s["w"]})
        for r in mo_rows:                               # 重訊也放進個股分包（消息分頁每 30 分就看得到）
            lst = shards[shard(r["c"])].setdefault(r["c"], [])
            lst.append({"t": r["t"], "day": 0, "src": r["src"], "title": r["s"], "link": r.get("link", ""), "mo": 1})
        for i, sh in enumerate(shards):
            json.dump(sh, open(P(f"s/{i}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        json.dump(items, open(P("items.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
        json.dump(seen, open(P("seen.json"), "w"), separators=(",", ":"))
        json.dump(tries, open(P("tries.json"), "w"), separators=(",", ":"))
        meta["n"] = len(items)
        json.dump(meta, open(P("meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
        d = day_stat                                    # 預估改用 Claude Haiku 的費用：輸入約 1.3 token／字加每批提示詞 700，輸出每篇約 450（含思考）；每百萬 token 輸入 0.10、輸出 0.50 美元
        d["usd"] = round((d["chars"] * 1.3 + d["batches"] * 700) * 0.10 / 1e6 + d["articles"] * 450 * 0.50 / 1e6, 4)
        json.dump(daily, open(P("daily.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    arts = []
    with cf.ThreadPoolExecutor(8) as ex:
        for res in ex.map(safe, SOURCES):
            arts += res
    meta.update({"t": now, "src": dict(SRC_N)})
    z = meta.get("zero", {})                        # 11/16：各家連續幾輪 0 篇或失敗（設定頁 ≥3 輪標紅）
    for k_, v_ in SRC_N.items():
        z[k_] = 0 if isinstance(v_, int) and v_ > 0 else z.get(k_, 0) + 1
    meta["zero"] = z
    print("各家篇數：", SRC_N)

    new = []
    for a in arts:
        if not a["link"].startswith("https://"):
            continue
        k = hashlib.md5(a["link"].encode()).hexdigest()[:16]
        if k in seen:
            seen[k] = max(seen[k], now - KEEP_DAYS * 86400)   # 列表上還看得到的文章延長紀錄，避免到期後重判
            continue
        if all(k != x["k"] for x in new):
            a["k"] = k
            new.append(a)
    if meta.get("quota_until", 0) > now:
        print("AI 額度用完中，這輪不抓內文")
        save()
        return
    with cf.ThreadPoolExecutor(8) as ex:
        for a, (txt, st) in zip(new, ex.map(fulltext, new)):
            a["text"], a["st"] = txt, st
    todo, nskip = [], 0
    for a in new:
        if a["st"] == "err" and tries.get(a["k"], 0) < 2:
            tries[a["k"]] = tries.get(a["k"], 0) + 1          # 暫時抓不到：下輪再試，最多 3 次
            continue
        tries.pop(a["k"], None)
        old = a["t"] and a["t"] < now - KEEP_DAYS * 86400
        if a["st"] != "ok" or not good(a["text"]) or not a["title"] or old or not mentions_any(a["title"] + a["text"], names):
            seen[a["k"]] = now
            nskip += 1
            continue
        todo.append(a)
    print(f"新文章 {len(new)} 篇：送 AI {len(todo)}（本輪最多 {RUN_MAX}）、跳過 {nskip}（付費／會員／太舊／沒提到上市櫃）")
    pri = priority_codes()
    for a in todo:
        a["pri"] = is_priority(a, pri, codes)
    todo = sorted(todo, key=lambda a: (not a["pri"], -(a["t"] or now)))[:RUN_MAX]   # 11/17：優先名單（關注清單＋成交值前 100）先判，其次新的先；沒判到的留下一輪
    print(f"優先名單 {len(pri)} 檔；本輪待判 {len(todo)} 篇中優先 {sum(1 for a in todo if a['pri'])} 篇")

    batches, cur, size = [], [], 0
    for a in todo:
        n = min(len(a["text"]), TEXT_MAX)
        if cur and (len(cur) >= BATCH_N or size + n > BATCH_CHARS):
            batches.append(cur)
            cur, size = [], 0
        cur.append(a)
        size += n
    if cur:
        batches.append(cur)
    done, used, bi = 0, {}, 0
    while batches:
        batch = batches.pop(0)
        for i, a in enumerate(batch):
            a["id"] = f"A{i + 1}"
        if bi:
            time.sleep(GAP)
        bi += 1
        try:
            res, who = judge(batch, prov)
        except BadBatch:
            if len(batch) > 1:                          # 拆成兩半再送
                h = len(batch) // 2
                batches[:0] = [batch[:h], batch[h:]]
            else:
                seen[batch[0]["k"]] = now               # 單篇還是壞：跳過這篇
            continue
        except Quota:
            meta["quota_until"] = now + 3600                # 1 小時內不再抓內文，避免一直打媒體網站
            print("AI 額度都用完，剩下的之後再判斷")
            break
        used[who] = used.get(who, 0) + 1
        day_stat["batches"] += 1
        day_stat["chars"] += sum(min(len(a["text"]), TEXT_MAX) for a in batch)
        byid = {a["id"]: a for a in batch}
        got = set()
        for x in res:
            try:
                a = byid.get(str(x.get("id")).strip())
                if not a or a["id"] in got:
                    continue
                got.add(a["id"])
                day_stat["articles"] += 1
                day_stat["pri" if a.get("pri") else "non"] = day_stat.get("pri" if a.get("pri") else "non", 0) + 1
                day_stat["by"][who] = day_stat["by"].get(who, 0) + 1
                ss = []
                for s in x.get("stocks") or []:
                    c = resolve(s, a, names, codes)
                    d = {"上修": 1, "持平": 0, "下修": -1}.get(s.get("dir")) if isinstance(s, dict) else None
                    if c and d is not None and (str(s.get("kind")).startswith("盤面") or (str(s.get("kind")) == "點名" and d == 0)):
                        continue                        # 盤面（股價漲跌）一律不收；投顧點名又沒有利多利空：不收
                    if c and d is not None and c not in [y["c"] for y in ss]:
                        ss.append({"c": c, "d": d, "k": str(s.get("kind") or "")[:4], "w": str(s.get("why") or "")[:40]})
                seen[a["k"]] = now
                done += 1
                if ss:
                    day_stat["withStock"] += 1
                    for s_ in ss:
                        day_stat["up" if s_["d"] > 0 else "down" if s_["d"] < 0 else "flat"] += 1
                    items.append({"k": a["k"], "src": a["src"], "t": a["t"] or now, "day": a.get("day", 0) if a["t"] else 1,
                                  "title": a["title"][:120], "link": a["link"], "ai": ss})
            except Exception as e:                      # 單筆格式怪：跳過這筆，下輪再判
                print("解析失敗：", e, file=sys.stderr)
        save()                                          # 每批存一次，額度白費的機會降到最低
    meta["ai"] = used
    if used:
        meta["ai_ok_t"] = now                            # 最後一次 AI 判斷成功的時間（設定頁超過 3 小時標紅）
    if GONE:
        day_stat["gone"] = sorted(set(day_stat.get("gone", []) + GONE))
    if MINFO.get("fatal"):
        day_stat["alert"] = "新聞 AI 全部型號都被 Google 回報不存在，已停止判斷，請找 Claude 處理"
        day_stat["allfail"] = day_stat.get("allfail", 0) + 1
        open(os.path.join(os.path.dirname(os.path.abspath(out)), "news_fatal.flag"), "w").write(day_stat["alert"])
    day_stat["busy"] += EV["busy"]; day_stat["quota"] += EV["quota"]
    print(f"本輪判斷 {done} 篇（{used}），近 {KEEP_DAYS} 天有個股的文章 {len(items)} 篇")
    save()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "news-out"))
