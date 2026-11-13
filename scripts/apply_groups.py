"""把使用者在 Google 試算表維護的族群，套用到網站。

用法：
  apply_groups.py tw <試算表內容.json>            → 更新 data/groups_tw_all.csv（台股，公開，會進 GitHub）
  apply_groups.py us <試算表內容.json> [--upload] → 更新 data/groups_us.csv、data/groups_us_all.csv（美股，私人）
                                                   --upload：直接寫進 Cloudflare KV（用 Cloudflare API，不經過 GitHub）

試算表內容.json：Google Sheets 讀出來的二維陣列，第一列是欄位名稱「代號,名稱,產業別,主族群」。
主族群可以用「+」列多個族群（例如 汽車+電池/能源+機器人/自動化），第一個是主族群，股票會出現在每個族群裡。
試算表沒列到的股票維持原本（系統自動）的分類。印出有變動的股票，給使用者確認。"""
import csv, io, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KV_NS = "a9956db1f402402cb08454fc7ae6ef03"


def split_groups(*parts):
    out = []
    for p in parts:
        for x in (p or "").replace("、", "+").split("+"):
            x = x.strip()
            if x and x not in out:
                out.append(x)
    return out


def load_sheet(path):
    rows = json.load(open(path, encoding="utf-8"))
    head = [h.strip() for h in rows[0]]
    need = ("代號", "名稱", "產業別", "主族群")
    if any(h not in head for h in need):
        sys.exit(f"試算表欄位不對：{head}，需要 {need}")
    out = {}
    for r in rows[1:]:
        r = dict(zip(head, [str(x).strip() for x in r] + [""] * (len(head) - len(r))))
        if r["代號"] and r["主族群"]:
            out[r["代號"]] = r
    if len(out) < 50:
        sys.exit(f"試算表只有 {len(out)} 檔，看起來不完整，停止更新")
    return out


def cf(method, path, data=None):
    """Cloudflare API（金鑰由雲端環境的 network secret 自動帶入，這裡不放金鑰）。"""
    cmd = ["curl", "-sS", "-X", method, "https://api.cloudflare.com/client/v4" + path]
    if data is not None:
        cmd += ["-H", "Content-Type: application/octet-stream", "--data-binary", "@-"]
    r = subprocess.run(cmd, input=data, capture_output=True, check=True)
    return r.stdout


def kv_key(k):
    return "/storage/kv/namespaces/" + KV_NS + "/values/" + k.replace("/", "%2F")


def account():
    d = json.loads(cf("GET", "/accounts"))
    if not d.get("success") or not d["result"]:
        sys.exit("Cloudflare API 讀不到帳號（金鑰沒有帶入？）")
    return d["result"][0]["id"]


def apply_tw(sheet):
    p = os.path.join(ROOT, "data", "groups_tw_all.csv")
    raw = open(p, encoding="utf-8", newline="").read()
    rd = csv.DictReader(io.StringIO(raw))
    fields, rows = rd.fieldnames, list(rd)
    if "副族群" not in fields:
        fields.append("副族群")
    seen, changes = set(), []
    for r in rows:
        s = sheet.get(r["代號"])
        if not s:
            continue
        seen.add(r["代號"])
        old = split_groups(r["主族群"], r.get("副族群"))
        new = split_groups(s["主族群"])
        if old != new:
            changes.append(f"{r['代號']} {r['名稱']}：{'+'.join(old)} → {'+'.join(new)}")
        r["主族群"], r["副族群"] = new[0], "+".join(new[1:])
    w = csv.DictWriter(open(p, "w", encoding="utf-8", newline=""), fieldnames=fields, lineterminator="\r\n" if "\r\n" in raw else "\n")
    w.writeheader()
    w.writerows(rows)
    return changes, [f"{c} {s['名稱']}" for c, s in sheet.items() if c not in seen]


def apply_us(sheet, upload):
    acc = account() if upload else None
    pa, pu = os.path.join(ROOT, "data", "groups_us_all.csv"), os.path.join(ROOT, "data", "groups_us.csv")
    if upload:                                   # 以 KV 裡最新的全市場清單為底
        b = cf("GET", f"/accounts/{acc}" + kv_key("state/groups_us_all.csv"))
        if not b.startswith("代號".encode()):
            sys.exit("KV 裡讀不到 state/groups_us_all.csv")
        open(pa, "wb").write(b)
    rows = list(csv.DictReader(open(pa, encoding="utf-8")))
    seen, changes = set(), []
    for r in rows:
        s = sheet.get(r["代號"])
        if not s:
            continue
        seen.add(r["代號"])
        old, new = split_groups(r["主族群"]), split_groups(s["主族群"])
        if old != new:
            changes.append(f"{r['代號']} {s['名稱']}：{'+'.join(old)} → {'+'.join(new)}")
        r.update({"名稱": s["名稱"], "產業別": s["產業別"] or r["產業別"], "主族群": "+".join(new), "把握度": "使用者"})
    for c, s in sheet.items():                   # 試算表有、全市場清單沒有的也加進去
        if c not in seen:
            rows.append({"代號": c, "名稱": s["名稱"], "產業別": s["產業別"], "主族群": "+".join(split_groups(s["主族群"])), "把握度": "使用者"})
            changes.append(f"{c} {s['名稱']}：新增 → {s['主族群']}")
    rows.sort(key=lambda r: r["代號"])
    with open(pa, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["代號", "名稱", "產業別", "主族群", "把握度"])
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in w.fieldnames} for r in rows)
    with open(pu, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["代號", "名稱", "產業別", "主族群"])
        w.writerows([c, s["名稱"], s["產業別"], "+".join(split_groups(s["主族群"]))] for c, s in sheet.items())
    if upload:                                   # 只寫 2 筆 KV
        for k, p in (("state/groups_us.csv", pu), ("state/groups_us_all.csv", pa)):
            d = json.loads(cf("PUT", f"/accounts/{acc}" + kv_key(k), open(p, "rb").read()))
            if not d.get("success"):
                sys.exit(f"寫入 KV 失敗：{k} {d.get('errors')}")
    return changes, []


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("tw", "us"):
        sys.exit(__doc__)
    sheet = load_sheet(sys.argv[2])
    if sys.argv[1] == "tw":
        ch, miss = apply_tw(sheet)
    else:
        ch, miss = apply_us(sheet, "--upload" in sys.argv)
    print(f"{'台股' if sys.argv[1] == 'tw' else '美股'}：試算表 {len(sheet)} 檔，變動 {len(ch)} 檔")
    for x in ch:
        print("  " + x)
    if miss:
        print("  不在全市場清單（略過）：" + "、".join(miss))
