import sys, json, time, os
sys.path.insert(0, 'scripts'); import news
arts = json.load(open('tmp_test/arts.json'))
for p in news.providers():
    tag = p[3].split('/')[-1]; out = {}
    for i in range(0, len(arts), 8):
        try:
            res, _ = news.judge(arts[i:i+8], [p])
            for r in res: out[r.get('id')] = r.get('stocks', [])
        except Exception as e:
            print('失敗', tag, i, e, flush=True)
        time.sleep(8)
    print('RESULT_' + tag + ' ' + json.dumps(out, ensure_ascii=False), flush=True)
