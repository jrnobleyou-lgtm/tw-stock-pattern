import sys, json, time, os
sys.path.insert(0, 'scripts'); import news
arts = json.load(open('tmp_test/arts.json'))
CF = "https://api.cloudflare.com/client/v4/accounts/%s/ai/v1/chat/completions" % os.environ.get("CF_ACCOUNT", "")
provs = []
if os.environ.get("GROQ_API_KEY"):
    provs.append(("Groq", "https://api.groq.com/openai/v1/chat/completions", os.environ["GROQ_API_KEY"], "openai/gpt-oss-120b"))
if os.environ.get("CF_AI_TOKEN"):
    for m in ("@cf/openai/gpt-oss-120b", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"):
        provs.append(("Cloudflare", CF, os.environ["CF_AI_TOKEN"], m))
print("要測", [p[3] for p in provs], flush=True)
for p in provs:
    tag = p[0] + "_" + p[3].split('/')[-1]; out = {}
    for i in range(0, len(arts), 4):                 # 免費額度小，每批 4 篇
        try:
            res, _ = news.judge(arts[i:i+4], [p])
            for r in res: out[r.get('id')] = r.get('stocks', [])
        except Exception as e:
            print('失敗', tag, i, str(e)[:200], flush=True)
        time.sleep(6)
    print('RESULT_' + tag + ' ' + json.dumps(out, ensure_ascii=False), flush=True)
# 重跑 1794842842
