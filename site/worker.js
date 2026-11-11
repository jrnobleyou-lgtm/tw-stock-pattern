// 盤中即時 K 棒：瀏覽器呼叫 /api/quote?s=2330.TW ，這裡代為向 Yahoo 取當日 1 分 K 並合成今天的 開高低收量。
// 其餘網址由 Cloudflare 直接提供靜態網站檔案（不會進到這支程式）。
const SYM = /^(\d{4,6}[A-Z]?\.(TW|TWO)|\^TWII|\^TWOII)$/;

function parseChart(j) {
  const r = j && j.chart && j.chart.result && j.chart.result[0];
  if (!r || !r.timestamp || !r.indicators || !r.indicators.quote) return null;
  const q = r.indicators.quote[0], ts = r.timestamp, off = (r.meta && r.meta.gmtoffset) || 28800;
  let o = null, h = -Infinity, l = Infinity, c = null, last = 0, n = 0;
  for (let i = 0; i < ts.length; i++) {
    if (q.close[i] == null || q.high[i] == null || q.low[i] == null) continue;
    if (o == null) o = q.open[i] != null ? q.open[i] : q.close[i];
    h = Math.max(h, q.high[i]); l = Math.min(l, q.low[i]); c = q.close[i]; last = ts[i]; n++;
  }
  if (!n) return null;
  const meta = r.meta || {};
  let v = meta.regularMarketVolume;
  if (v == null) { v = 0; for (let i = 0; i < ts.length; i++) v += q.volume && q.volume[i] || 0; }
  const day = new Date((last + off) * 1000).toISOString().slice(0, 10);
  const r2 = x => Math.round(x * 100) / 100;
  return { date: day, o: r2(o), h: r2(h), l: r2(l), c: r2(c), v, t: last, prev: meta.chartPreviousClose || meta.previousClose || null };
}

// ── 證交所即時行情（mis.twse.com.tw，幾秒延遲）：個股、加權、櫃買指數都有；失敗才退回 Yahoo（約延遲 20 分）
const MIS_URL = "https://mis.twse.com.tw/stock/";
let misCookie = "", misCookieAt = 0;
function misChannel(sym) {
  if (sym === "^TWII") return "tse_t00.tw";
  if (sym === "^TWOII") return "otc_o00.tw";
  const m = sym.match(/^(\d{4,6}[A-Z]?)\.(TW|TWO)$/);
  return m ? (m[2] === "TW" ? "tse_" : "otc_") + m[1].toLowerCase() + ".tw" : null;
}
const num = x => { const v = parseFloat(x); return isFinite(v) ? v : null; };
function parseMis(j) {
  const m = j && j.msgArray && j.msgArray[0];
  if (!m) return null;
  const z = num(m.z), o = num(m.o), h = num(m.h), l = num(m.l), y = num(m.y);
  const c = z != null ? z : (num((m.b || "").split("_")[0]) != null ? num((m.b || "").split("_")[0]) : o);
  if (c == null || h == null || l == null) return null;
  const d = String(m.d || ""); if (d.length !== 8) return null;
  const date = d.slice(0, 4) + "-" + d.slice(4, 6) + "-" + d.slice(6, 8);
  const tl = m.tlong ? Math.floor(Number(m.tlong) / 1000) : 0;
  return { date, o: o != null ? o : c, h: Math.max(h, c), l: Math.min(l, c), c, v: (num(m.v) || 0) * 1000, t: tl, hms: m.t || "", prev: y, src: "mis", delay: 0 };
}
async function misQuote(sym) {
  const ch = misChannel(sym); if (!ch) return null;
  const now = Date.now();
  if (!misCookie || now - misCookieAt > 600000) {
    const r0 = await fetch(MIS_URL + "index.jsp", { headers: { "user-agent": "Mozilla/5.0" } });
    const sc = r0.headers.getSetCookie ? r0.headers.getSetCookie() : [r0.headers.get("set-cookie") || ""];
    misCookie = sc.map(x => x.split(";")[0]).filter(Boolean).join("; "); misCookieAt = now;
  }
  const r = await fetch(`${MIS_URL}api/getStockInfo.jsp?ex_ch=${ch}&json=1&delay=0&_=${now}`, {
    headers: { "user-agent": "Mozilla/5.0", "referer": MIS_URL + "index.jsp", "cookie": misCookie, "accept": "application/json" },
  });
  if (!r.ok) { misCookie = ""; return null; }
  const txt = await r.text(); let j; try { j = JSON.parse(txt); } catch (e) { misCookie = ""; return null; }
  return parseMis(j);
}

export default {
  async fetch(req) {
    const u = new URL(req.url);
    if (u.pathname !== "/api/quote") return new Response("Not found", { status: 404 });
    const sym = u.searchParams.get("s") || "";
    if (!SYM.test(sym)) return new Response(JSON.stringify({ error: "bad symbol" }), { status: 400, headers: { "content-type": "application/json" } });
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1m&range=1d&includePrePost=false`;
    let out = { error: "unavailable" }, status = 502;
    try { const q = await misQuote(sym); if (q) return new Response(JSON.stringify(q), { status: 200, headers: { "content-type": "application/json", "cache-control": "public, max-age=3" } }); } catch (e) { /* 改用 Yahoo */ }
    try {
      const r = await fetch(url, { headers: { "user-agent": "Mozilla/5.0" }, cf: { cacheTtl: 20, cacheEverything: true } });
      if (r.ok) { const p = parseChart(await r.json()); if (p) { out = { ...p, src: "yahoo", delay: 20 }; status = 200; } }
    } catch (e) { /* 回傳 502 */ }
    return new Response(JSON.stringify(out), { status, headers: { "content-type": "application/json", "cache-control": "public, max-age=5" } });
  },
};
