"""重大訊息（11/16 使用者＋Fable 建議）：
  當天：鉅亨網「公告」分類（轉載公開資訊觀測站公告，api.cnyes.com，網站本來就在用的新聞 API），標題格式「公司:主旨」才算重訊
        （鉅亨自動產生的「某某 10 月營收…」稿不算）。
  隔天：證交所／櫃買開放資料 t187ap04_L、mopsfin_t187ap04_O（官方授權的開放資料，每天清晨更新、只給前一天）補齊並校正。
  不碰 mops.twse.com.tw（觀測站明確擋程式讀取，證交所條款也只允許開放資料管道）。
由 news.py 每輪呼叫（news.yml 每天都跑、週末每小時），存 news-data 分支的 mops.json：
  [{"c": 代號, "t": 發言時間 epoch, "s": 主旨, "src": "鉅亨網"|"公開資訊觀測站", "link": 鉅亨原文（官方沒有）}]，近 30 天，
  同一檔、同一天、主旨前 20 字相同＝同一則（連續重複公告只算第一次）。
meta["mops"]：鉅亨最後讀到的時間、官方今天抓過沒、每天官方 vs 鉅亨比對（觀察鉅亨漏幾則）。
"""
import json, os, re, time, urllib.request
from datetime import datetime, timedelta, timezone

TW = timezone(timedelta(hours=8))
KEEP = 30 * 86400
CNYES = "https://api.cnyes.com/media/api/v1/newslist/category/announcement?limit=30&page={}"
OFFICIAL = [("https://openapi.twse.com.tw/v1/opendata/t187ap04_L", "公司代號"),
            ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O", "SecuritiesCompanyCode")]
TITLE = re.compile(r"^\s*([^:：]{1,16})[:：]\s*(.+)$")


def norm(s):
    return re.sub(r"[^一-鿿A-Za-z0-9]", "", s or "")[:20]


def key(r):
    """同一檔、主旨前 20 字相同＝同一則（更名公告之類天天重發的，只算第一次；紀錄留 120 天）。"""
    return r["c"] + norm(r["s"])


def _get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())


def from_cnyes(codes, since, pages=6):
    """讀到比 since 舊就停（最多 6 頁 180 則，平日一輪通常 1 頁）。"""
    out = []
    for p in range(1, pages + 1):
        d = _get(CNYES.format(p))["items"]["data"]
        for x in d:
            m = TITLE.match(x.get("title") or "")
            cs = [str(k.get("code")) for k in x.get("market") or [] if str(k.get("code")) in codes]
            if m and len(cs) == 1:
                out.append({"c": cs[0], "t": int(x.get("publishAt") or 0), "s": m.group(2).strip()[:120],
                            "src": "鉅亨網", "link": f"https://news.cnyes.com/news/id/{x['newsId']}"})
        if not d or min(int(x.get("publishAt") or 0) for x in d) < since:
            break
        time.sleep(1)
    return out


def parse_official(r, ck):
    try:
        c = str(r[ck]).strip()
        d, t = str(r["發言日期"]).strip(), str(r["發言時間"]).strip().zfill(6)
        dt = datetime(int(d[:-4]) + 1911, int(d[-4:-2]), int(d[-2:]), int(t[:2]), int(t[2:4]), int(t[4:6]), tzinfo=TW)
        s = re.sub(r"\s+", "", str(r.get("主旨") or r.get("主旨 ") or ""))
        return {"c": c, "t": int(dt.timestamp()), "s": s[:120], "src": "公開資訊觀測站"} if c and s else None
    except Exception:
        return None


def from_official(codes):
    out, ok = [], 0
    for u, ck in OFFICIAL:
        try:
            for r in _get(u):
                x = parse_official(r, ck)
                if x and x["c"] in codes:
                    out.append(x)
            ok += 1
        except Exception as e:
            print("官方重訊抓取失敗：", u.rsplit("/", 1)[-1], repr(e)[:80])
    return out, ok == len(OFFICIAL)


def merge(rows, new, seen):
    """新的併進去：同一則（key 相同）官方蓋過鉅亨的來源，但保留鉅亨連結；連續重複公告只留第一次（seen＝{key: 第一次時間}）。"""
    idx = {key(r): r for r in rows}
    added = 0
    for x in sorted(new, key=lambda r: r["t"]):
        k = key(x)
        if k in idx:
            r = idx[k]
            if x["src"] == "公開資訊觀測站" and r["src"] != x["src"] and abs(x["t"] - r["t"]) < 86400:
                r.update(src=x["src"], t=x["t"])               # 同一天的同一則：官方時間較準
        elif k in seen and x["t"] - seen[k] > 3600:
            continue                                           # 之前已經出現過（天天重發的公告）
        else:
            idx[k] = x; added += 1
        seen.setdefault(k, x["t"])
    return sorted(idx.values(), key=lambda r: -r["t"]), added


def run(out, codes, meta):
    P = os.path.join(out, "mops.json")
    rows = json.load(open(P, encoding="utf-8")) if os.path.exists(P) else []
    now = int(time.time())
    m = meta.setdefault("mops", {})
    seen = {k: t for k, t in m.get("seen", {}).items() if t > now - 120 * 86400}
    try:
        new = from_cnyes(codes, m.get("cnyes_t", now - 86400) - 1800)
        if new:
            m["cnyes_t"] = max(x["t"] for x in new)
        rows, a = merge(rows, new, seen)
        print("重訊（鉅亨）新增", a, "則")
    except Exception as e:
        print("重訊（鉅亨）抓取失敗：", repr(e)[:80])
    today = datetime.now(TW)
    if today.hour >= 6 and m.get("official") != today.strftime("%Y-%m-%d"):
        off, ok = from_official(codes)
        if ok:
            m["official"] = today.strftime("%Y-%m-%d")
            ks = {key(r) for r in rows} | set(seen)
            miss = [x for x in off if key(x) not in ks]
            day = max((datetime.fromtimestamp(x["t"], TW).strftime("%Y-%m-%d") for x in off), default="")
            m.setdefault("check", {})[day or today.strftime("%Y-%m-%d")] = {"官方": len(off), "鉅亨沒有": len(miss)}   # 觀察 2～3 天
            m["check"] = dict(sorted(m["check"].items())[-14:])
            rows, a = merge(rows, off, seen)
            print("重訊（官方）", len(off), "則，鉅亨沒有", len(miss), "則，新增", a)
    m["seen"] = seen
    rows = [r for r in rows if r["t"] > now - KEEP]
    json.dump(rows, open(P, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return rows
