"""把使用者的台股關注清單（試算表「關注股票_台股」分頁）寫進 Cloudflare KV（state/watchlist_tw），不進公開的 GitHub。
用法：apply_watchlist.py <試算表內容.json>      （內容＝get_values 的二維陣列，欄位：代號、備註）
印出新增／移除的代號。新聞排程（news.py）用 GitHub 身分從 Worker 讀這份清單。少於 20 檔就不寫（避免讀壞清單把它清空）。"""
import json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import apply_groups as AG


def parse(rows):
    out = []
    for r in rows:
        c = str(r[0]).strip() if r else ""
        if re.fullmatch(r"[0-9]{4,6}[A-Z]?", c) and c not in [x[0] for x in out]:
            out.append((c, str(r[1]).strip() if len(r) > 1 else ""))
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    new = parse(json.load(open(sys.argv[1], encoding="utf-8")))
    if len(new) < 20:
        sys.exit(f"關注清單只讀到 {len(new)} 檔，少於 20，不更新")
    acc = AG.account()
    old_b = AG.cf("GET", f"/accounts/{acc}" + AG.kv_key("state/watchlist_tw"))
    old = {ln.split(",")[0] for ln in old_b.decode("utf-8", "replace").splitlines() if re.match(r"^[0-9]{4,6}[A-Z]?,", ln)}
    body = "\n".join(f"{c},{n}" for c, n in new) + "\n"
    d = json.loads(AG.cf("PUT", f"/accounts/{acc}" + AG.kv_key("state/watchlist_tw"), body.encode("utf-8")))
    if not d.get("success"):
        sys.exit(f"寫入 KV 失敗：{d.get('errors')}")
    cur = {c for c, _ in new}
    print(f"關注清單：{len(new)} 檔；新增 {sorted(cur - old) or '無'}；移除 {sorted(old - cur) or '無'}")
