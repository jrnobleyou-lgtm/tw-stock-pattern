"""個股新聞：抓 7 家財經媒體的免費文章 → 讀全文 → Gemini 判斷對個股是上修／持平／下修。

用法：news.py <資料夾>
  資料夾＝news-data 分支的工作目錄，裡面放：
    seen.json          看過的文章（網址雜湊 → 時間），每篇只判斷一次
    items.json         近 30 天有判斷結果的文章
    s/<0-63>.json      依股票代號分包（Worker 的 /api/news 讀這個）
規則（使用者定）：付費、要登入會員的文章不抓（抓不到全文就整篇跳過）；Yahoo 不用。
金鑰：環境變數 GEMINI_API_KEY（GitHub Secrets）；雲端測試環境由網路代理自動帶入。"""
import concurrent.futures as cf, csv, email.utils, hashlib, html, json, os, re, subprocess, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
KEEP_DAYS, NSHARD, BATCH = 30, 64, 10
MODELS = ("gemini-3.5-flash", "gemini-3.5-flash-lite")
GEMINI = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"


def get(u, t=20):
    r = subprocess.run(["curl", "-sS", "-m", str(t), "-L", "-A", UA, u], capture_output=True, text=True)
    return r.stdout


def strip(s):
    return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", s or "")).strip()


def rss(u):
    out = []
    for it in re.findall(r"<item>(.*?)</item>", get(u), re.S):
        f = lambda t: (lambda m: strip(m.group(1)) if m else "")(re.search(rf"<{t}[^>]*>(.*?)</{t}>", it, re.S))
        try:
            ts = int(email.utils.parsedate_to_datetime(f("pubDate")).timestamp())
        except (TypeError, ValueError):
            ts = 0
        out.append({"title": f("title"), "link": f("link") or f("guid"), "t": ts})
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
        try:
            d = json.loads(get(f"https://api.cnyes.com/media/api/v1/newslist/category/{cat}?limit=30"))["items"]["data"]
        except Exception:
            continue
        for x in d:
            if str(x.get("payment")) != "0":
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
    x = get("https://uanalyze.com.tw/")
    seen, out = set(), []
    for u, t in re.findall(r'href="(https://uanalyze\.com\.tw/articles/\d+)"[^>]*>(.*?)</a>', x, re.S):
        t = re.sub(r"<[^>]+>|\s+", " ", t).strip()
        if t and u not in seen:
            seen.add(u)
            out.append({"src": "優分析", "title": html.unescape(t), "link": u, "t": 0})
    return out


def src_technews():
    return [dict(a, src="科技新報") for a in rss("https://finance.technews.tw/feed/")]


SOURCES = (src_udn, src_ctee, src_cnyes, src_moneydj, src_cna, src_uanalyze, src_technews)


# ───────── 內文（抓不到全文＝付費／會員文章，跳過） ─────────
def fulltext(a):
    if a.get("text"):
        return a["text"]
    import trafilatura
    raw = get(a["link"])
    meta = trafilatura.extract_metadata(raw) if raw else None
    txt = (trafilatura.extract(raw) or "") if raw else ""
    if not a["title"] and meta and meta.title:
        a["title"] = re.sub(r"\s*[|｜-]\s*(中央社|CNA).*$", "", meta.title).strip()
    if not a["t"] and meta and meta.date:
        try:
            a["t"] = int(time.mktime(time.strptime(meta.date[:10], "%Y-%m-%d")))
        except ValueError:
            pass
    m = re.search(r"本文共\s*(\d+)\s*字", raw or "")
    if m and len(txt) < int(m.group(1)) * 0.6:      # 經濟日報：只看得到部分＝付費／會員
        return ""
    if "登入" in txt[:200] and "繁體版" in txt[:200]:  # 抓到的是選單不是內文
        return ""
    return txt


def good(txt):
    return len(re.findall(r"[一-鿿]", txt)) >= 150


# ───────── Gemini 判斷 ─────────
PROMPT = """你是台股新聞分析助理。下面每篇是台灣財經新聞（標題＋內文）。對每篇，找出文章「主要在談」的台灣上市櫃公司（只是順便列名、或只出現在選股清單裡一筆帶過的不算，最多 5 家），判斷這篇對該公司是：
上修＝利多（營收／獲利／訂單／目標價上調、需求轉強、擴產等）
持平＝中性、已知數字、好壞參半
下修＝利空（獲利衰退、目標價下調、砍單、風險升高等）
請以內文為準，不要被標題的聳動語氣誤導。code 填台股代號（4～6 碼，不確定就空字串）。理由用繁體中文 25 字內。
只輸出 JSON：{"r":[{"i":篇號,"stocks":[{"name":"公司簡稱","code":"代號","dir":"上修|持平|下修","why":"理由"}]}]}，沒有主要公司就 stocks 給空陣列。
"""


def gemini(batch):
    body = PROMPT + "".join(f"\n=== 第{i}篇（{a['src']}）\n標題：{a['title']}\n內文：{a['text'][:2500]}\n" for i, a in enumerate(batch))
    key = os.environ.get("GEMINI_API_KEY", "proxy-injected")
    for model in MODELS:
        req = {"model": model, "messages": [{"role": "user", "content": body}], "response_format": {"type": "json_object"}}
        for _ in range(2):
            r = subprocess.run(["curl", "-sS", "-m", "180", GEMINI, "-H", "Authorization: Bearer " + key, "-H", "Content-Type: application/json", "--data-binary", "@-"],
                               input=json.dumps(req), capture_output=True, text=True)
            try:
                d = json.loads(r.stdout)
                res = json.loads(d["choices"][0]["message"]["content"])
                return res["r"] if isinstance(res, dict) else res
            except Exception:
                err = r.stdout[:200]
                if '"code": 429' in err or "RESOURCE_EXHAUSTED" in err:
                    break                                   # 這個模型額度用完，換下一個
                time.sleep(5)
        print("Gemini 失敗：", model, err, file=sys.stderr)
    return None


def stocks_map():
    names, codes = {}, set()
    for r in csv.DictReader(open(os.path.join(ROOT, "data", "groups_tw_all.csv"), encoding="utf-8")):
        codes.add(r["代號"])
        names[r["名稱"]] = r["代號"]
    return names, codes


def resolve(s, names, codes):
    c = (s.get("code") or "").strip().upper()
    if c in codes:
        return c
    n = (s.get("name") or "").strip()
    return names.get(n) or names.get(n.replace("-KY", "")) or names.get(n + "-KY")


# ───────── 主流程 ─────────
def safe(f):
    try:
        return f()
    except Exception as e:                          # 單一媒體壞掉不影響其他家
        print(f"{f.__name__} 失敗：{e}", file=sys.stderr)
        return []


def shard(c):
    h = 0
    for ch in c:
        h = (h * 31 + ord(ch)) % 1000003
    return h % NSHARD


def main(out):
    os.makedirs(os.path.join(out, "s"), exist_ok=True)
    now = int(time.time())
    load = lambda f, d: json.load(open(os.path.join(out, f), encoding="utf-8")) if os.path.exists(os.path.join(out, f)) else d
    seen, items = load("seen.json", {}), load("items.json", [])
    seen = {k: v for k, v in seen.items() if v > now - (KEEP_DAYS + 5) * 86400}

    arts = []
    with cf.ThreadPoolExecutor(7) as ex:
        for fn, res in zip(SOURCES, ex.map(safe, SOURCES)):
            print(f"{fn.__name__}: {len(res)} 篇")
            arts += res
    new = []
    for a in arts:
        k = hashlib.md5(a["link"].encode()).hexdigest()[:16]
        if a["link"] and k not in seen and all(k != x["k"] for x in new):
            a["k"] = k
            new.append(a)
    with cf.ThreadPoolExecutor(8) as ex:
        for a, txt in zip(new, ex.map(fulltext, new)):
            a["text"] = txt
    names, codes = stocks_map()
    ok = [a for a in new if good(a["text"]) and a["title"]]
    skip = [a for a in new if a not in ok]
    print(f"新文章 {len(new)} 篇：可讀全文 {len(ok)}、跳過（付費／會員／讀不到）{len(skip)}")
    for a in skip:
        seen[a["k"]] = now
    done = 0
    for i in range(0, len(ok), BATCH):
        batch = ok[i:i + BATCH]
        res = gemini(batch)
        if res is None:
            print("Gemini 今天額度用完或失敗，剩下的下一輪再判斷")
            break
        for x in res:
            try:
                a = batch[int(x["i"])]
            except (KeyError, ValueError, IndexError, TypeError):
                continue
            ss = []
            for s in x.get("stocks") or []:
                c = resolve(s, names, codes)
                d = {"上修": 1, "持平": 0, "下修": -1}.get(s.get("dir"))
                if c and d is not None and c not in [y["c"] for y in ss]:
                    ss.append({"c": c, "d": d, "w": (s.get("why") or "")[:40]})
            a["ai"] = ss
        for a in batch:
            seen[a["k"]] = now
            if a.get("ai"):
                items.append({"k": a["k"], "src": a["src"], "t": a["t"] or now, "title": a["title"][:120], "link": a["link"], "ai": a["ai"]})
            done += 1
    items = sorted([x for x in items if x["t"] > now - KEEP_DAYS * 86400], key=lambda x: -x["t"])
    print(f"本輪判斷 {done} 篇，近 {KEEP_DAYS} 天有個股的文章 {len(items)} 篇")

    shards = [dict() for _ in range(NSHARD)]
    for x in items:
        for s in x["ai"]:
            shards[shard(s["c"])].setdefault(s["c"], []).append({"t": x["t"], "src": x["src"], "title": x["title"], "link": x["link"], "d": s["d"], "w": s["w"]})
    for i, sh in enumerate(shards):
        json.dump(sh, open(os.path.join(out, "s", f"{i}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(items, open(os.path.join(out, "items.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(seen, open(os.path.join(out, "seen.json"), "w", encoding="utf-8"), separators=(",", ":"))
    json.dump({"t": now, "n": len(items)}, open(os.path.join(out, "meta.json"), "w"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "news-out"))
