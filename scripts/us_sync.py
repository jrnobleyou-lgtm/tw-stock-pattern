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

def post(files, meta=None):
    body = json.dumps({"files": {k: base64.b64encode(v).decode() for k, v in files.items()}, **({"meta": meta} if meta else {})}).encode()
    r = urllib.request.urlopen(urllib.request.Request(API, data=body, method="POST", headers={**headers(), "Content-Type": "application/json"}), timeout=120)
    return json.loads(r.read())

if sys.argv[1:] == ["pull"]:
    os.makedirs(os.path.join(ROOT, "data", "us"), exist_ok=True)
    g = get("state/groups_us.csv")
    if g: open(os.path.join(ROOT, "data", "groups_us.csv"), "wb").write(g)
    h = get("state/hist.csv.gz")
    if h: open(os.path.join(ROOT, "data", "us", "hist.csv"), "wb").write(gzip.decompress(h))
    print("下載：族群", bool(g), "；歷史", bool(h))
elif sys.argv[1:] == ["push"]:
    old = json.loads(get("state/manifest.json") or b"{}")
    files, man = {}, {}
    for p in [os.path.join(ROOT, "site", "us", "index.html"), os.path.join(ROOT, "site", "us", "data.js")] + sorted(glob.glob(os.path.join(ROOT, "site", "us", "s", "*.json"))):
        k = "site/" + os.path.relpath(p, os.path.join(ROOT, "site", "us")).replace(os.sep, "/")
        b = open(p, "rb").read(); man[k] = hashlib.md5(b).hexdigest()
        if old.get(k) != man[k]:
            files[k] = b                              # 只上傳有變動的檔案（KV 免費額度每天 1000 次寫入）
    files["state/hist.csv.gz"] = gzip.compress(open(os.path.join(ROOT, "data", "us", "hist.csv"), "rb").read())
    files["state/groups_us.csv"] = open(os.path.join(ROOT, "data", "groups_us.csv"), "rb").read()
    files["state/manifest.json"] = json.dumps(man).encode()
    D = json.loads(open(os.path.join(ROOT, "site", "us", "data.js"), encoding="utf-8").read()[len("window.DATA="):-1])
    meta = {"asof": D["asof"], "stocks": len(D["stocks"]), "missing": D.get("missing", []),
            "updated": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M（台灣時間）")}
    keys, n = list(files), 0
    for i in range(0, len(keys), 40):
        part = {k: files[k] for k in keys[i:i + 40]}
        n += post(part, meta if i + 40 >= len(keys) else None)["n"]
    print("上傳", n, "個檔案；資料日期", meta["asof"])
else:
    sys.exit("用法：us_sync.py pull|push")
