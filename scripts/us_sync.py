"""美股資料與 Cloudflare KV 同步（資料不進公開的 GitHub）。
  us_sync.py pull  → 下載 state/hist.csv.gz、state/groups_us.csv 到 data/
  us_sync.py push  → 上傳 site/admin/ 的頁面檔案、歷史資料與狀態
身分：GitHub Actions 用 OIDC（不需要金鑰）；本機用環境變數 INGEST_KEY。"""
import base64, csv, datetime, glob, gzip, hashlib, json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.environ.get("SITE_URL", "https://news-findstockpattern-swing-breakout.news-stockpatten.workers.dev").rstrip("/")
API = SITE + "/api/us-ingest"

def headers():
    h = {"User-Agent": "Mozilla/5.0"}
    if os.environ.get("INGEST_KEY"):
        h["X-Ingest-Key"] = os.environ["INGEST_KEY"]
    elif os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"):
        req = urllib.request.Request(os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=tw-stock-us",
                                     headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
        h["Authorization"] = "Bearer " + json.loads(urllib.request.urlopen(req, timeout=30).read())["value"]
    else:
        sys.exit("沒有上傳身分（INGEST_KEY 或 GitHub OIDC）")
    return h

def get(key):
    try:
        return urllib.request.urlopen(urllib.request.Request(API + "?key=" + key, headers=headers()), timeout=60).read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def put(key, data):
    import time
    for i in range(4):
        try:
            urllib.request.urlopen(urllib.request.Request(API + "?key=" + key, data=data, method="PUT",
                                   headers={**headers(), "Content-Type": "application/octet-stream"}), timeout=120).read()
            return
        except urllib.error.HTTPError as e:
            if e.code < 500 or i == 3: raise
            time.sleep(3 * (i + 1))

def post(files, meta=None):
    body = json.dumps({"files": {k: base64.b64encode(v).decode() for k, v in files.items()}, **({"meta": meta} if meta else {})}).encode()
    r = urllib.request.urlopen(urllib.request.Request(API, data=body, method="POST", headers={**headers(), "Content-Type": "application/json"}), timeout=120)
    return json.loads(r.read())

NSH, NST = 256, 8                      # 個股 K 線分成 256 包、歷史資料分成 8 包（KV 每筆上限 25MB、每天寫入 1000 次）
def shard(code, n):
    h = 0
    for ch in code:
        h = (h * 31 + ord(ch)) % 1000003
    return h % n

if sys.argv[1:] == ["pull"]:
    os.makedirs(os.path.join(ROOT, "data", "us"), exist_ok=True)
    for name in ("groups_us.csv", "groups_us_all.csv"):
        g = get("state/" + name)
        if g: open(os.path.join(ROOT, "data", name), "wb").write(g)
    parts = [get(f"state/hist_{k}.csv.gz") for k in range(NST)]
    if all(parts):
        with open(os.path.join(ROOT, "data", "us", "hist.csv"), "wb") as f:
            for k, b in enumerate(parts):
                t = gzip.decompress(b)
                f.write(t if k == 0 else t.split(b"\n", 1)[1])
    print("下載：歷史", all(parts))
elif sys.argv[1:] == ["push"]:
    old = json.loads(get("state/manifest.json") or b"{}")
    files, man = {}, {}
    def add(k, b):
        man[k] = hashlib.md5(b).hexdigest()
        if old.get(k) != man[k]:
            files[k] = b                              # 只上傳有變動的
    for name in ("index.html", "data.js"):
        add("site/" + name, open(os.path.join(ROOT, "site", "us", name), "rb").read())
    # 個股 K 線：方案 B（底包＋近期包，見 us_store.py），只寫有變動的
    import us_store
    D0 = json.loads(open(os.path.join(ROOT, "site", "us", "data.js"), encoding="utf-8").read()[len("window.DATA="):-1])
    stocks = {os.path.basename(p)[:-5]: us_store.to_rows(json.load(open(p))["bars"], D0["dates"])
              for p in glob.glob(os.path.join(ROOT, "site", "us", "s", "*.json"))}
    tw_wd = (datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))).weekday()
    kw, kman = us_store.plan(D0["dates"], stocks, old.get("kline", {}), tw_wd)
    files.update(kw)
    lines = open(os.path.join(ROOT, "data", "us", "hist.csv"), "rb").read().split(b"\n")
    head, parts = lines[0], [[] for _ in range(NST)]
    for ln in lines[1:]:
        if ln:
            parts[shard(ln.split(b",", 2)[1].decode(), NST)].append(ln)
    for k in range(NST):
        files[f"state/hist_{k}.csv.gz"] = gzip.compress(b"\n".join([head] + parts[k]) + b"\n")
    for name in ("groups_us.csv", "groups_us_all.csv"):
        pth = os.path.join(ROOT, "data", name)
        if os.path.exists(pth): add("state/" + name, open(pth, "rb").read())
    man["kline"] = kman
    files["state/manifest.json"] = json.dumps(man).encode()
    us_store.check_cap(files)                       # 超過上限就停，一筆都不寫
    print("本次寫入", len(files), "筆：底包", sum(k.startswith("site/sh/") for k in files), "、近期包", sum(k.startswith("site/rc/") for k in files),
          "、K 線底包截止", kman["base"]["cutoff"])
    D = json.loads(open(os.path.join(ROOT, "site", "us", "data.js"), encoding="utf-8").read()[len("window.DATA="):-1])
    meta = {"asof": D["asof"], "stocks": len(D["stocks"]), "missing": D.get("missing", [])[:50], "missingN": len(D.get("missing", [])),
            "updated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M（台灣時間）")}
    H = headers()                                    # 取一次身分（GitHub OIDC 有效期約 5 分鐘以上，足夠）
    headers = lambda: H
    keys = sorted(files, key=lambda k: k == "state/manifest.json")   # manifest 最後寫，中途失敗下次會重傳
    for k in keys:
        put(k, files[k])
    put("meta", json.dumps(meta, ensure_ascii=False).encode())
    n = len(keys)
    print("上傳", n, "個檔案；資料日期", meta["asof"], "；股票", meta["stocks"])
else:
    sys.exit("用法：us_sync.py pull|push")
