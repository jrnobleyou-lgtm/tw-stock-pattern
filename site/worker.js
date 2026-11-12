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
let misCookie = "", misCookieAt = 0, misErr = "";
const lastGood = {};   // 每個代號最近一次成功的證交所資料（失敗時暫用，最多 90 秒）
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
  const pos = x => { const v = num(x); return v != null && v > 0 ? v : null; };      // 價格一定大於 0（"-"、0 都視為沒有）
  const first = str => { for (const t of String(str || "").split("_")) { const v = pos(t); if (v != null) return v; } return null; };
  const z = pos(m.z), o = pos(m.o), y = pos(m.y);
  const c = z != null ? z : (first(m.b) != null ? first(m.b) : (first(m.a) != null ? first(m.a) : o));
  let h = pos(m.h), l = pos(m.l);
  if (c == null || o == null) return null;               // 還沒開盤／沒有可用價格
  if (h == null) h = Math.max(o, c);
  if (l == null) l = Math.min(o, c);
  h = Math.max(h, o, c); l = Math.min(l, o, c);
  const d = String(m.d || ""); if (d.length !== 8) return null;
  const date = d.slice(0, 4) + "-" + d.slice(4, 6) + "-" + d.slice(6, 8);
  const tl = m.tlong ? Math.floor(Number(m.tlong) / 1000) : 0;
  const idx = m.c === "t00" || m.c === "o00", amt = idx && num(m.m) != null ? Math.round(num(m.m) * (m.c === "t00" ? 0.776 : 0.967)) / 1000 : null;   // 指數：m 換算成億元，再依 11/12 官方值校正（證交所即時的 m 比官方成交金額高：加權約 +29%、櫃買約 +3.5%）；收盤後以官方為準
  return { date, o, h, l, c, amt, v: (num(m.v) || 0) * 1000, t: tl, hms: m.t || "", prev: y, src: "mis", delay: 0 };
}
async function misQuote(sym) {
  const ch = misChannel(sym); if (!ch) { misErr = "nochannel"; return null; }
  const now = Date.now();
  if (!misCookie || now - misCookieAt > 600000) {
    const r0 = await fetch(MIS_URL + "index.jsp", { headers: { "user-agent": "Mozilla/5.0" } });
    const sc = r0.headers.getSetCookie ? r0.headers.getSetCookie() : [r0.headers.get("set-cookie") || ""];
    misCookie = sc.map(x => x.split(";")[0]).filter(Boolean).join("; "); misCookieAt = now;
    misErr = "idx " + r0.status;
  }
  const r = await fetch(`${MIS_URL}api/getStockInfo.jsp?ex_ch=${ch}&json=1&delay=0&_=${now}`, {
    headers: { "user-agent": "Mozilla/5.0", "referer": MIS_URL + "index.jsp", "cookie": misCookie, "accept": "application/json" },
  });
  if (!r.ok) { misCookie = ""; misErr = "http " + r.status; return null; }
  const txt = await r.text(); let j; try { j = JSON.parse(txt); } catch (e) { misCookie = ""; misErr = "notjson " + txt.slice(0, 60).replace(/\s+/g, " "); return null; }
  const pm = parseMis(j); if (!pm) misErr = "empty"; return pm;
}

// 批次：給排程程式一次取多檔（上限 100 檔），回傳證交所原始欄位
const EX = /^(tse|otc)_([0-9a-z]{4,6}|t00|o00)\.tw$/;
async function misBatch(ex) {
  const list = ex.split("|").filter(Boolean);
  if (!list.length || list.length > 100 || !list.every(x => EX.test(x))) return null;
  for (let k = 0; k < 3; k++) {
    try {
      const now = Date.now();
      if (!misCookie || now - misCookieAt > 600000) {
        const r0 = await fetch(MIS_URL + "index.jsp", { headers: { "user-agent": "Mozilla/5.0" } });
        const sc = r0.headers.getSetCookie ? r0.headers.getSetCookie() : [r0.headers.get("set-cookie") || ""];
        misCookie = sc.map(x => x.split(";")[0]).filter(Boolean).join("; "); misCookieAt = now;
      }
      const r = await fetch(`${MIS_URL}api/getStockInfo.jsp?ex_ch=${list.join("%7C")}&json=1&delay=0&_=${now}`, {
        headers: { "user-agent": "Mozilla/5.0", "referer": MIS_URL + "index.jsp", "cookie": misCookie, "accept": "application/json" },
      });
      if (r.ok) { const j = JSON.parse(await r.text()); if (j && j.msgArray) return j.msgArray.map(m => ({ c: m.c, ex: m.ex, z: m.z, o: m.o, h: m.h, l: m.l, y: m.y, v: m.v, tv: m.tv, d: m.d, t: m.t, b: m.b, a: m.a })); }
    } catch (e) { /* 重試 */ }
    misCookie = ""; await new Promise(r => setTimeout(r, 300));
  }
  return null;
}

// ── 台指期（大台近月）即時：期交所行情網站，日盤（MarketType 0）與夜盤（MarketType 1）
let txErr = "";
const txLast = {};
async function taifexList(mt) {
  const body = JSON.stringify({ MarketType: String(mt), SymbolType: "F", KindID: "1", CID: "TXF", ExpireMonth: "", RowSize: "全部", PageNo: "", SortColumn: "", AscDesc: "A" });
  for (let k = 0; k < 2; k++) {
    try {
      const r = await fetch("https://mis.taifex.com.tw/futures/api/getQuoteList", { method: "POST", body, headers: {
        "content-type": "application/json;charset=UTF-8", "accept": "application/json, text/plain, */*",
        "origin": "https://mis.taifex.com.tw", "referer": "https://mis.taifex.com.tw/futures/RegularSession/EquityIndices/FuturesDomestic/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" } });
      const t = await r.text();
      if (!r.ok) { txErr = "http " + r.status + " " + t.slice(0, 60); continue; }
      const j = JSON.parse(t);
      const list = j && j.RtData && j.RtData.QuoteList;
      if (list && list.length) { txLast[mt] = { list, at: Date.now() }; return list; }
      txErr = "empty " + t.slice(0, 80);
    } catch (e) { txErr = "exc " + String(e).slice(0, 80); }
  }
  const c = txLast[mt];
  return c && Date.now() - c.at < 120000 ? c.list : null;       // 失敗時暫用 2 分鐘內最近一次成功的資料
}
function txPick(list) {
  if (!list) return { fut: null, spot: null };
  const spot = list.find(q => /^TXF-[SP]$/.test(q.SymbolID)) || null;
  const fut = list.find(q => /^TXF[A-L]\d-[FM]$/.test(q.SymbolID)) || null;      // 清單依到期月份排序，第一個就是近月
  const f = q => q && {
    id: q.SymbolID, name: q.DispCName, date: q.CDate, time: q.CTime,
    o: num(q.COpenPrice), h: num(q.CHighPrice), l: num(q.CLowPrice), c: num(q.CLastPrice), ref: num(q.CRefPrice),
    v: num(q.CTotalVolume) || 0, oi: num(q.OpenInterest),
  };
  return { fut: f(fut), spot: f(spot) };
}


// ════════ 美股（需要密碼）：資料放在 Cloudflare KV（綁定名稱 US），不經過公開的 GitHub ════════
// KV 內容：site/<路徑>＝美股頁面檔案；auth＝{salt,hash,iter}（PBKDF2-SHA256）；meta＝更新狀態；state/*＝每日更新用的歷史資料
const enc = new TextEncoder();
const hex = b => [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, "0")).join("");
const unhex = h => new Uint8Array(h.match(/../g).map(x => parseInt(x, 16)));
async function pbkdf2(pw, saltHex, iter) {
  const k = await crypto.subtle.importKey("raw", enc.encode(pw), "PBKDF2", false, ["deriveBits"]);
  return hex(await crypto.subtle.deriveBits({ name: "PBKDF2", hash: "SHA-256", salt: unhex(saltHex), iterations: iter }, k, 256));
}
async function hmac(keyHex, msg) {
  const k = await crypto.subtle.importKey("raw", unhex(keyHex), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return hex(await crypto.subtle.sign("HMAC", k, enc.encode(msg)));
}
async function usAuthed(req, env) {
  const auth = await env.US.get("auth", "json"); if (!auth) return false;
  const m = (req.headers.get("cookie") || "").match(/(?:^|;\s*)us_auth=(\d+)\.([0-9a-f]{64})/);
  if (!m || Number(m[1]) < Date.now()) return false;
  return (await hmac(auth.hash, m[1])) === m[2];               // 改密碼後舊的登入自動失效
}
const page = (title, body) => new Response(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><link rel="icon" href="/favicon.ico">
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#100c1f url(/bg.jpg) center/cover;font:15px/1.6 -apple-system,"Noto Sans TC","PingFang TC",sans-serif;color:#ece8f5}
.box{background:rgba(20,16,32,.92);border:1px solid #3a3450;border-radius:12px;padding:24px;width:min(92vw,380px);display:flex;flex-direction:column;gap:12px}
h1{font-size:19px;margin:0}input{font:inherit;padding:9px 11px;border-radius:8px;border:1px solid #3a3450;background:#0c0a16;color:#ece8f5}
button{font:inherit;padding:9px;border-radius:8px;border:0;background:#f0d34a;color:#241c00;font-weight:700;cursor:pointer}.m{color:#9a93ad;font-size:13px}.e{color:#fb7185;font-size:13px}a{color:#c9b6ff}
table{border-collapse:collapse;font-size:13px}td{padding:3px 8px 3px 0}</style></head><body><div class="box">${body}</div></body></html>`, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
const loginForm = (err = "") => page("美股型態確認｜登入", `<h1>美股型態確認</h1><div class="m">請輸入密碼</div>
<form method="post" action="/us/login" style="display:flex;flex-direction:column;gap:10px"><input type="password" name="pw" id="pw" autocomplete="current-password" autofocus required><button>登入</button></form>
${err ? `<div class="e">${err}</div>` : ""}<a href="/" class="m">← 回台股</a>`);
const TYPES = { html: "text/html; charset=utf-8", js: "application/javascript; charset=utf-8", json: "application/json", css: "text/css", png: "image/png", jpg: "image/jpeg" };
async function usRoute(req, env, u) {
  const p = u.pathname;
  if (!env.US) return new Response("美股尚未設定", { status: 503 });
  if (p === "/us/login" && req.method === "POST") {
    const f = await req.formData(), auth = await env.US.get("auth", "json");
    if (!auth || (await pbkdf2(String(f.get("pw") || ""), auth.salt, auth.iter)) !== auth.hash) return loginForm("密碼不對，請再試一次");
    const exp = String(Date.now() + 30 * 864e5);
    return new Response(null, { status: 303, headers: { location: "/us/", "set-cookie": `us_auth=${exp}.${await hmac(auth.hash, exp)}; Path=/us; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax` } });
  }
  if (p === "/us/logout") return new Response(null, { status: 303, headers: { location: "/us/login", "set-cookie": "us_auth=; Path=/us; Max-Age=0; HttpOnly; Secure; SameSite=Lax" } });
  if (!(await usAuthed(req, env))) return p === "/us/login" ? loginForm() : new Response(null, { status: 303, headers: { location: "/us/login" } });
  if (p === "/us/login") return new Response(null, { status: 303, headers: { location: "/us/" } });
  if (p === "/us/admin") {
    let msg = "";
    if (req.method === "POST") {
      const f = await req.formData(), auth = await env.US.get("auth", "json");
      const cur = String(f.get("cur") || ""), n1 = String(f.get("n1") || ""), n2 = String(f.get("n2") || "");
      if ((await pbkdf2(cur, auth.salt, auth.iter)) !== auth.hash) msg = `<div class="e">目前密碼不對</div>`;
      else if (n1.length < 6) msg = `<div class="e">新密碼至少 6 個字</div>`;
      else if (n1 !== n2) msg = `<div class="e">兩次輸入的新密碼不一樣</div>`;
      else {
        const salt = hex(crypto.getRandomValues(new Uint8Array(16))), iter = 100000;
        const hash = await pbkdf2(n1, salt, iter);
        await env.US.put("auth", JSON.stringify({ salt, hash, iter }));
        const exp = String(Date.now() + 30 * 864e5);
        return new Response(null, { status: 303, headers: { location: "/us/admin?ok=1", "set-cookie": `us_auth=${exp}.${await hmac(hash, exp)}; Path=/us; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax` } });
      }
    }
    if (u.searchParams.get("ok")) msg = `<div class="m" style="color:#7ee0a1">密碼已更新，其他裝置需要重新登入。</div>`;
    const meta = (await env.US.get("meta", "json")) || {};
    const rows = [["資料日期（美東）", meta.asof], ["最後更新", meta.updated], ["股票數", meta.stocks], ["抓不到資料", (meta.missing || []).join("、") || "無"]]
      .map(([a, b]) => `<tr><td class="m">${a}</td><td>${b ?? "—"}</td></tr>`).join("");
    return page("美股｜資料庫狀態與管理", `<h1>資料庫狀態與管理</h1><table>${rows}</table>
<h1 style="font-size:16px;margin-top:6px">更改密碼</h1><form method="post" style="display:flex;flex-direction:column;gap:8px">
<input type="password" name="cur" placeholder="目前密碼" autocomplete="current-password" required><input type="password" name="n1" placeholder="新密碼（至少 6 個字）" autocomplete="new-password" required><input type="password" name="n2" placeholder="再輸入一次新密碼" autocomplete="new-password" required><button>更改密碼</button></form>${msg}
<div class="m"><a href="/us/">← 回美股</a>　<a href="/us/logout">登出</a></div>`);
  }
  let key = "site/" + (p.slice(4) || "index.html");
  if (key.endsWith("/")) key += "index.html";
  const v = await env.US.get(key, "arrayBuffer");
  if (!v) return new Response("找不到", { status: 404 });
  const ext = key.split(".").pop();
  return new Response(v, { headers: { "content-type": TYPES[ext] || "application/octet-stream", "cache-control": "private, no-cache" } });
}
// GitHub Actions 的 OIDC 身分證明：只有本專案 main 分支上的工作流程能上傳，不需要把金鑰放進 GitHub
let jwks = null, jwksAt = 0;
const b64u = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), c => c.charCodeAt(0));
async function githubOidcOk(tok) {
  try {
    const [h, p, sig] = tok.split("."); const head = JSON.parse(new TextDecoder().decode(b64u(h))), c = JSON.parse(new TextDecoder().decode(b64u(p)));
    if (c.iss !== "https://token.actions.githubusercontent.com" || c.aud !== "tw-stock-us" || c.exp * 1000 < Date.now()) return false;
    if (c.repository !== "jrnobleyou-lgtm/tw-stock-pattern" || c.ref !== "refs/heads/main") return false;
    if (!jwks || Date.now() - jwksAt > 3600e3) { jwks = (await (await fetch("https://token.actions.githubusercontent.com/.well-known/jwks")).json()).keys; jwksAt = Date.now(); }
    const jwk = jwks.find(k => k.kid === head.kid); if (!jwk) return false;
    const key = await crypto.subtle.importKey("jwk", jwk, { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"]);
    return await crypto.subtle.verify("RSASSA-PKCS1-v1_5", key, b64u(sig), enc.encode(h + "." + p));
  } catch (e) { return false; }
}
async function usIngest(req, env, u) {          // 每日更新程式用：上傳／下載 KV。GitHub Actions 用 OIDC，手動用 X-Ingest-Key
  const bearer = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
  const ok = (env.US_INGEST_KEY && req.headers.get("x-ingest-key") === env.US_INGEST_KEY) || (bearer && await githubOidcOk(bearer));
  if (!env.US || !ok) return new Response("forbidden", { status: 403 });
  if (req.method === "GET") {
    const v = await env.US.get(u.searchParams.get("key") || "", "arrayBuffer");
    return v ? new Response(v) : new Response("not found", { status: 404 });
  }
  const j = await req.json();
  for (const [k, b64] of Object.entries(j.files || {})) {
    if (!/^(site|state)\//.test(k)) continue;
    await env.US.put(k, Uint8Array.from(atob(b64), c => c.charCodeAt(0)));
  }
  if (j.meta) await env.US.put("meta", JSON.stringify(j.meta));
  return new Response(JSON.stringify({ ok: true, n: Object.keys(j.files || {}).length }), { headers: { "content-type": "application/json" } });
}

export default {
  async fetch(req, env) {
    const u = new URL(req.url);
    if (u.pathname === "/us" ) return new Response(null, { status: 301, headers: { location: "/us/" } });
    if (u.pathname.startsWith("/us/")) return usRoute(req, env, u);
    if (u.pathname === "/api/us-ingest") return usIngest(req, env, u);
    if (u.pathname === "/api/tx") {
      try {
        const [d, n] = await Promise.all([taifexList(0), taifexList(1)]);
        const day = txPick(d), night = txPick(n);
        const out = { day: day.fut, night: night.fut, spot: day.spot, spotNight: night.spot };
        if (!out.day && !out.night) out.dbg = { colo: (req.cf && req.cf.colo) || "", err: txErr };
        return new Response(JSON.stringify(out), { status: 200, headers: { "content-type": "application/json", "cache-control": "public, max-age=3" } });
      } catch (e) {
        return new Response(JSON.stringify({ error: "unavailable" }), { status: 502, headers: { "content-type": "application/json" } });
      }
    }
    if (u.pathname === "/api/misraw") {      // 除錯用：只允許證交所即時行情網站的 stock/data、stock/api 路徑
      const path = u.searchParams.get("p") || "";
      if (!/^stock\/(data|api)\/[A-Za-z_]+\.jsp(\?[A-Za-z0-9_=&.|%]*)?$/.test(path)) return new Response("bad path", { status: 400 });
      try {
        const r0 = await fetch(MIS_URL + "index.jsp", { headers: { "user-agent": "Mozilla/5.0" } });
        const sc = r0.headers.getSetCookie ? r0.headers.getSetCookie() : [];
        const ck = sc.map(x => x.split(";")[0]).join("; ");
        const r = await fetch("https://mis.twse.com.tw/" + path, { headers: { "user-agent": "Mozilla/5.0", "referer": MIS_URL + "index.jsp", "cookie": ck } });
        return new Response((await r.text()).slice(0, 4000), { status: r.status, headers: { "content-type": "text/plain; charset=utf-8" } });
      } catch (e) { return new Response("err " + e, { status: 502 }); }
    }
    if (u.pathname === "/api/mis") {
      const arr = await misBatch(u.searchParams.get("ex_ch") || "");
      return new Response(JSON.stringify(arr ? { msgArray: arr } : { error: "unavailable" }), { status: arr ? 200 : 502, headers: { "content-type": "application/json", "cache-control": "no-store" } });
    }
    if (u.pathname !== "/api/quote") return new Response("Not found", { status: 404 });
    const sym = u.searchParams.get("s") || "";
    if (!SYM.test(sym)) return new Response(JSON.stringify({ error: "bad symbol" }), { status: 400, headers: { "content-type": "application/json" } });
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(sym)}?interval=1m&range=1d&includePrePost=false`;
    let out = { error: "unavailable" }, status = 502;
    let q = null;
    for (let k = 0; k < 3 && !q; k++) { if (k) await new Promise(r => setTimeout(r, 300)); try { q = await misQuote(sym); } catch (e) { misCookie = ""; misErr = "exc " + String(e).slice(0, 80); } }
    if (q) lastGood[sym] = { q, at: Date.now() };
    else if (lastGood[sym] && Date.now() - lastGood[sym].at < 90000) q = { ...lastGood[sym].q, stale: true };   // 失敗就換新的連線 cookie 再試一次
    try { if (q) return new Response(JSON.stringify(q), { status: 200, headers: { "content-type": "application/json", "cache-control": "public, max-age=3" } }); } catch (e) { /* 改用 Yahoo */ }
    try {
      const r = await fetch(url, { headers: { "user-agent": "Mozilla/5.0" }, cf: { cacheTtl: 20, cacheEverything: true } });
      if (r.ok) { const p = parseChart(await r.json()); if (p) { out = { ...p, src: "yahoo", delay: 20, dbg: { colo: (req.cf && req.cf.colo) || "", misErr } }; status = 200; } }
    } catch (e) { /* 回傳 502 */ }
    if (status !== 200) out.dbg = { colo: (req.cf && req.cf.colo) || "", misErr };   // 失敗原因（在失敗之後才取，才是這次的結果）
    return new Response(JSON.stringify(out), { status, headers: { "content-type": "application/json", "cache-control": "public, max-age=5" } });
  },
};
