// 上線前檢查：把所有篩選鈕、綜合篩選鈕、五種型態、族群頁各點一次，只要有任何錯誤（pageerror）就失敗。
// 用法：先在本機跑 python3 scripts/analyze.py all 產生 site/data.js，再 NODE_PATH=$(npm root -g) node scripts/ui_check.js
const { chromium } = require('playwright'); const http = require('http'), fs = require('fs'), path = require('path');
const R = path.join(__dirname, '..', 'site');
const srv = http.createServer((q, r) => { let u = decodeURIComponent(q.url.split('?')[0]); if (u.endsWith('/')) u += 'index.html'; const p = path.join(R, u); fs.readFile(p, (e, b) => { if (e) { r.statusCode = 404; return r.end() } r.setHeader('content-type', { '.js': 'text/javascript', '.json': 'application/json', '.html': 'text/html' }[path.extname(p)] || 'a/b'); r.end(b) }) }).listen(8790);
(async () => {
  const b = await chromium.launch(); const errs = []; let n = 0;
  for (const vp of [{ width: 1280, height: 800 }, { width: 390, height: 844 }]) {
    const pg = await b.newPage({ viewport: vp }); pg.on('pageerror', e => errs.push(vp.width + ' ' + e.message));
    await pg.route('**/api/**', r => r.fulfill({ status: 404, body: '' }));
    for (const base of ['scr', 'mix']) {
      await pg.goto('http://localhost:8790/#' + base); await pg.waitForTimeout(1200);
      const keys = await pg.evaluate(() => [...document.querySelectorAll('.filters .btn')].map(x => x.dataset.k).filter(Boolean));
      for (const k of keys) {
        await pg.goto('http://localhost:8790/#' + base + '-' + k); await pg.waitForTimeout(250); n++;
        const subs = await pg.evaluate(() => [...document.querySelectorAll('.subf .btn')].map(x => x.dataset.k).filter(Boolean));
        for (const s of subs) { await pg.goto('http://localhost:8790/#' + base + '-' + s); await pg.waitForTimeout(150); n++ }
      }
    }
    for (const h of ['etf', 'etf-active', 'etf-passive', 'etf-all.高股息', 'etf-all.槓桿', 'etf-all.債券', 'e-0050']) { await pg.goto('http://localhost:8790/#' + h); await pg.waitForTimeout(500); n++ }   // 11/18 ETF 專區
    await pg.goto('http://localhost:8790/#'); await pg.waitForTimeout(1500);
    const gs = await pg.evaluate(() => [...document.querySelectorAll('[data-swg],[data-g]')].slice(0, 6).map(x => x.dataset.swg || x.dataset.g));
    for (const g of gs) { await pg.goto('http://localhost:8790/#g-' + encodeURIComponent(g)); await pg.waitForTimeout(200); n++ }
    // 11/19 Opus 審查：個股 K 線視窗也要開過——新股、停牌、有形態、一般各挑幾檔，開 K 線、切「消息」分頁（11/16 新股欄位不全害整頁掛掉就是這一類）
    const codes = await pg.evaluate(() => { const S = Object.values(D.stocks), pick = (f, k) => S.filter(f).slice(0, k).map(s => s.code); return [...new Set([...pick(s => s.new, 3), ...pick(s => s.stale, 2), ...pick(s => (s.geo || []).length, 3), ...pick(s => !s.new && !s.stale, 3), ...pick(s => /本週強勢（大型）|今日強勢/.test((s.tags || []).join()), 2)])] });
    for (const c of codes) {
      await pg.goto('http://localhost:8790/#s-' + c); await pg.waitForTimeout(900); n++;
      const mt = await pg.$('[data-mt="n"]'); if (mt) { await mt.click(); await pg.waitForTimeout(500); n++ }
    }
    await pg.goto('http://localhost:8790/#'); await pg.waitForTimeout(300);
    await pg.close();
  }
  console.log('檢查了', n, '個畫面，錯誤', errs.length); errs.slice(0, 10).forEach(e => console.log(' ', e));
  await b.close(); srv.close(); process.exit(errs.length ? 1 : 0);
})();
