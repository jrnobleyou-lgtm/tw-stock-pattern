"""法人目標價參考清單（11/18 使用者要求；Opus 顧問設計）。
沒有可靠的免費「平均目標價」來源，所以只整理公開新聞裡「有具名」的目標價：
  1) 鉅亨速報「Factset 最新調查：○○(代號-TW) … 預估目標價為 X 元」＝多位分析師預估的中位數（標題格式固定，最可靠）
  2) 新聞句子裡「某券商（美銀、高盛、大摩…）… 目標價 X 元」，同一句要提到同一檔股票，且券商名稱要具名（只寫「外資」不收）
只存：股票、價格、券商、日期、標題、連結（不存內文）。到 analyze.py 再用現價驗證（0.3～3 倍）、算最近 60 天的清單與統計。"""
import re

FS_RE = re.compile(r"Factset[^：:]*[：:]\s*([^()（]+?)\s*[(（](\d{4,6})-TW[)）].*?預估目標價[^\d]{0,12}?([\d,]+(?:\.\d+)?)\s*元", re.I)
BROKERS = ["摩根士丹利", "摩根大通", "美國銀行", "美林", "美銀", "高盛", "小摩", "大摩", "花旗", "瑞銀", "瑞信", "瑞士信貸", "野村", "麥格理", "里昂", "法國巴黎", "巴克萊",
           "匯豐", "德意志", "星展", "大和", "SMBC", "日興", "杰富瑞", "Jefferies", "富瑞", "摩根", "凱基", "元大證券", "元大投顧", "富邦投顧", "富邦證券", "國泰證券",
           "群益", "永豐投顧", "永豐金證券", "兆豐證券", "統一證券", "統一投顧", "日盛", "中信證券", "康和", "第一金證券", "玉山證券", "新光證券", "台新證券", "華南永昌",
           "國票", "宏遠", "犇亞", "法人"]
NAMEOF = {"美國銀行": "美銀", "美林": "美銀", "摩根士丹利": "大摩", "摩根大通": "小摩", "瑞信": "瑞士信貸", "Jefferies": "杰富瑞", "富瑞": "杰富瑞", "元大證券": "元大", "元大投顧": "元大",
          "富邦投顧": "富邦", "富邦證券": "富邦", "國泰證券": "國泰", "永豐投顧": "永豐", "永豐金證券": "永豐", "兆豐證券": "兆豐", "統一證券": "統一", "統一投顧": "統一",
          "中信證券": "中信", "第一金證券": "第一金", "玉山證券": "玉山", "新光證券": "新光", "台新證券": "台新", "華南永昌": "華南永昌", "日興": "日興"}
UP = re.compile(r"上調|調升|調高|上修|提高|拉高|調漲|喊升")
DN = re.compile(r"下調|調降|下修|調低|砍|降至|降低")
NUM = re.compile(r"([\d,]+(?:\.\d+)?)\s*(萬)?\s*元")


def _price(m):
    v = float(m.group(1).replace(",", ""))
    return v * 10000 if m.group(2) else v


def fs_from_title(title):
    m = FS_RE.search(title or "")
    if not m:
        return None
    return {"c": m.group(2), "p": float(m.group(3).replace(",", "")), "who": "FactSet 分析師預估（中位數）", "fs": 1}


def _stock_in(s, names, codes):
    """句子裡恰好提到一檔股票（名稱或代號）才算，回傳代號。"""
    hit = set()
    for n, c in names.items():
        if len(n) >= 2 and n in s:
            hit.add(c)
    for c in re.findall(r"(?<!\d)(\d{4})(?!\d)", s):
        if c in codes:
            hit.add(c)
    if len(hit) > 1:                                   # 一個名稱包含另一個（例：聯電／聯電子）時取較長的那個
        keep = {c for c in hit if not any(c != d and codes[c] in codes[d] for d in hit)}
        hit = keep
    return hit.pop() if len(hit) == 1 else None


def p2n(seg):
    m = NUM.search(seg[seg.index("目標價") + 3:])
    return _price(m)


def _multi(s, names, codes):
    """一句多檔股票：每檔取「自己名稱到下一檔名稱之間」的片段，片段內要有「目標價」且後面 14 字內有價格。回傳 [(代號, 片段)]。"""
    pos = []
    for n, c in names.items():
        if len(n) >= 3 or (len(n) == 2 and n in ("台積", "聯電")):
            for m in re.finditer(re.escape(n), s):
                pos.append((m.start(), m.end(), c))
    pos.sort()
    pos = [x for i, x in enumerate(pos) if not any(y[0] <= x[0] and y[1] >= x[1] and y is not x and (y[1] - y[0]) > (x[1] - x[0]) for y in pos)]
    res = []
    for i, (a, b, c) in enumerate(pos):
        seg = s[a:pos[i + 1][0] if i + 1 < len(pos) else len(s)]
        j = seg.find("目標價")
        if j < 0 or not NUM.search(seg[j + 3:j + 17]):
            continue
        if not all(c != c2 for _, _, c2 in pos[:i]):
            continue
        if i and pos[i][0] - pos[i - 1][1] <= 2:            # 「台積電、聯發科目標價…」名稱並排，價格歸屬不明 → 不收
            continue
        if "分別" in seg or "各為" in seg:
            continue
        res.append((c, seg[:j + 17]))
    return res


def sentence_targets(text, names, codes):
    out = []
    for s in re.split(r"[。！？\n]", text or ""):
        if "目標價" not in s or len(s) > 160:
            continue
        who = next((b for b in BROKERS if b in s), None)
        if not who or who == "法人":                   # 「法人」太籠統，不當作具名券商
            continue
        c = _stock_in(s, names, codes)
        if not c:
            for c2, p2 in _multi(s, names, codes):         # 11/20：一句提到多檔時，「股票名稱＋目標價＋價格」緊貼在一起的才算那一檔
                d = 1 if UP.search(p2) and not DN.search(p2) else -1 if DN.search(p2) and not UP.search(p2) else 0
                out.append({"c": c2, "p": p2n(p2), "who": NAMEOF.get(who, who), "d": d, "fs": 0, "_": p2})
            continue
        i = s.index("目標價")
        seg = re.split(r"[，；。、]", s[i + 3:i + 40])[0]
        nums = [_price(m) for m in NUM.finditer(seg)]
        if not nums:
            back = s[max(0, i - 14):i]
            nums = [_price(m) for m in NUM.finditer(back)][-1:]
        if not nums:
            continue
        d = 1 if UP.search(s) and not DN.search(s) else -1 if DN.search(s) and not UP.search(s) else 0
        out.append({"c": c, "p": nums[-1], "who": NAMEOF.get(who, who), "d": d, "fs": 0})
    return out


def from_article(a, names, codes, with_text=True):
    """a：{title, link, t, text?}；回傳目標價列。"""
    rows = []
    fs = fs_from_title(a.get("title"))
    if fs:
        rows.append(fs)
    else:
        parts = [a.get("title") or ""] + ([a.get("text") or ""] if with_text else [])
        seen = set()
        for r in sentence_targets("。".join(parts), names, codes):
            if (r["c"], r["who"]) not in seen:
                seen.add((r["c"], r["who"]))
                rows.append(r)
    for r in rows:
        r.update({"t": a.get("t") or 0, "title": (a.get("title") or "")[:100], "link": a.get("link", "")})
    return rows


def merge(old, rows, now, keep_days=70):
    """依連結＋股票＋券商去重；只留 keep_days 天。"""
    have = {(r["link"], r["c"], r["who"]) for r in old}
    out = [r for r in old if r["t"] > now - keep_days * 86400]
    for r in rows:
        k = (r["link"], r["c"], r["who"])
        if k not in have and r["t"] > now - keep_days * 86400:
            out.append(r)
            have.add(k)
    return sorted(out, key=lambda r: -r["t"])


def summarize(rows, close, now, days=60):
    """單一股票：rows＝這檔所有目標價列，close＝最新收盤。
    驗證（0.3～3 倍現價）→ 最近 days 天 → 每家券商只留最新一筆 → 標上調／下調（跟同一家上一筆比）。
    回傳 {"list": [...], "fs": {...}|None, "n": 家數（不含 FactSet）, "hi","lo","med"（≥3 家才有）}"""
    ok = [r for r in rows if r["t"] > now - days * 86400 and close and 0.3 * close <= r["p"] <= 3 * close]
    ok.sort(key=lambda r: r["t"])
    last, prev = {}, {}
    for r in ok:
        if r["who"] in last:
            prev[r["who"]] = last[r["who"]]
        last[r["who"]] = r
    lst = []
    for who, r in sorted(last.items(), key=lambda kv: -kv[1]["t"]):
        dr = r.get("d", 0)
        if who in prev and prev[who]["p"] != r["p"]:
            dr = 1 if r["p"] > prev[who]["p"] else -1
        lst.append({"who": who, "p": round(r["p"], 1) if r["p"] % 1 else int(r["p"]), "t": r["t"], "d": dr, "title": r["title"], "link": r["link"], "fs": r.get("fs", 0)})
    fs = next((x for x in lst if x["fs"]), None)
    brokers = [x for x in lst if not x["fs"]]
    out = {"list": lst[:12], "fs": fs, "n": len(brokers)}
    if len(brokers) >= 3:
        ps = sorted(x["p"] for x in brokers)
        out.update({"hi": ps[-1], "lo": ps[0], "med": ps[len(ps) // 2] if len(ps) % 2 else round((ps[len(ps) // 2 - 1] + ps[len(ps) // 2]) / 2, 1)})
    return out if lst else None
