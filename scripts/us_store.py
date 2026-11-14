"""美股 K 線存放規劃（方案 B）：底包＋近期包，讓每天寫入 KV 的筆數從約 270 降到約 30。

KV 結構：
  site/sh/<0-255>.json  底包：{代號: [[日期, 開, 高, 低, 收, 量, 還原因子], ...]}，日期在 [start, cutoff)
  site/rc/<0-15>.json   近期包：同格式，日期 ≥ cutoff
K 線存「日期字串」而不是總表的第幾天（總表每天往後移一天，編號每天都會變）。
底包平日內容不變就不重寫（只有除權息、分割改到舊價格時才會變）；每週六、或近期包太長時整理一次。"""
import hashlib, json, sys

NSH, NRC = 256, 16
CAP = 400                     # 一次上傳最多寫幾筆（免費方案每天 1000 次）


def shard(code, n):
    h = 0
    for ch in code:
        h = (h * 31 + ord(ch)) % 1000003
    return h % n


def md5(b):
    return hashlib.md5(b).hexdigest()


def to_rows(bars, dates):
    """analyze.py 輸出的 [第幾天, 開, 高, 低, 收, 量, 因子] → [日期, …]"""
    return [[dates[b[0]]] + list(b[1:]) for b in bars]


def plan(dates, stocks, man, weekday):
    """dates：總表日期；stocks：{代號: [[日期, …], …]}；man：上次的 manifest；weekday：台灣時間星期（0=一…5=六）。
    回傳 (要寫的 {key: bytes}, 新 manifest)。只回傳內容有變的 key。"""
    old_md5 = man.get("md5", {})
    base = man.get("base") or {}
    cut, start = base.get("cutoff"), base.get("start")
    rebuild = (not cut or not start or weekday == 5 or cut not in dates or dates[0] > start
               or len(dates) - 1 - dates.index(cut) > 12)
    if rebuild:
        cut, start = dates[-5], dates[min(7, len(dates) - 1)]
    sh, rc = {}, {}
    for code, rows in stocks.items():
        b = [r for r in rows if start <= r[0] < cut]
        r = [x for x in rows if x[0] >= cut]
        if b:
            sh.setdefault(shard(code, NSH), {})[code] = b
        if r:
            rc.setdefault(shard(code, NRC), {})[code] = r
    files = {}
    for prefix, packs in (("site/sh/", sh), ("site/rc/", rc)):
        for n, d in packs.items():
            files[f"{prefix}{n}.json"] = json.dumps(d, separators=(",", ":"), sort_keys=True).encode()
    new_md5 = {k: md5(v) for k, v in files.items()}
    writes = {k: v for k, v in files.items() if old_md5.get(k) != new_md5[k]}
    return writes, {"base": {"cutoff": cut, "start": start}, "md5": new_md5}


def check_cap(writes):
    if len(writes) > CAP:
        sys.exit(f"這次要寫入 {len(writes)} 筆，超過上限 {CAP}（免費方案每天 1000 次），停止上傳以免用完額度")
