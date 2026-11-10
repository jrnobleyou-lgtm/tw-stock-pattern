"""把 site/index.html + data.js 合成單一檔案，供 Artifact 預覽。"""
import re, os, base64
R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
html = open(f"{R}/site/index.html", encoding="utf-8").read()
data = open(f"{R}/site/data.js", encoding="utf-8").read()
style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
body = re.search(r"<body>(.*?)</body>", html, re.S).group(1)
import json, csv
EMBED = {r["代號"] for r in csv.DictReader(open(f"{R}/data/groups_tw.csv", encoding="utf-8"))}
_d = json.loads(data[len("window.DATA="):-1])
for code in EMBED:
    pth = f"{R}/site/s/{code}.json"
    if code in _d["stocks"] and os.path.exists(pth) and "bars" not in _d["stocks"][code]:
        _d["stocks"][code]["bars"] = json.load(open(pth))["bars"]
data = "window.DATA=" + json.dumps(_d, ensure_ascii=False, separators=(",", ":")) + ";"
body = body.replace('<script src="data.js"></script>', "<script>" + data + "</script>")
style = style.replace(".wrap{max-width:1100px;margin:0 auto;padding:0 16px 40px}", ".wrap{max-width:1100px;margin:0 auto;padding:0 0 40px}")
style = style.replace("header{padding:16px;", "header{padding:16px 0;")
style = style.replace("*{box-sizing:border-box}", "*{box-sizing:border-box}\n:root{color-scheme:dark}")
style = style.replace("body{margin:0;", "body{margin:0;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));")
bg = base64.b64encode(open(f"{R}/site/bg.jpg","rb").read()).decode()
style = style.replace("url(bg.jpg)", "url(data:image/jpeg;base64,"+bg+")")
out = f'''<title>每日股票型態確認</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>{style}</style>
{body}'''
open(f"{R}/site/preview.html", "w", encoding="utf-8").write(out)
print(len(out)//1024, "KB")
