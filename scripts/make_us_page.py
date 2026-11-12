"""把台股的 site/index.html 複製成美股版 site/us/index.html（同一套程式，只改共用檔案的路徑）。"""
import os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
s = open(os.path.join(ROOT, "site", "index.html"), encoding="utf-8").read()
for f in ("favicon.ico", "icon-32.png", "icon-192.png", "icon-512.png", "apple-touch-icon.png", "bg.jpg", "bg-work.jpg",
          "icon-work-32.png", "icon-work-192.png", "apple-touch-icon-work.png"):
    s = re.sub(r'(["(])' + re.escape(f), r'\g<1>../' + f, s)
s = s.replace("<title>每日股票型態確認</title>", "<title>美股型態確認</title>")
os.makedirs(os.path.join(ROOT, "site", "us"), exist_ok=True)
open(os.path.join(ROOT, "site", "us", "index.html"), "w", encoding="utf-8").write(s)
print("site/us/index.html 完成")
