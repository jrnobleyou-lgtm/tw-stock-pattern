// 盤中即時 K 棒：瀏覽器呼叫 /api/quote?s=2330.TW ，這裡代為向 Yahoo 取當日 1 分 K 並合成今天的 開高低收量。
// 其餘網址由 Cloudflare 直接提供靜態網站檔案（不會進到這支程式）。
const SYM = /^(\d{4,6}[A-Z]?\.(TW|TWO)|\^TWII|\^TWOII|[A-Z][A-Z0-9.\-]{0,9})$/;     // 最後一種是美股代號

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
<script>try{if(localStorage.getItem("work")==="1"){document.documentElement.classList.add("work");document.querySelector("link[rel=icon]").href="/icon-work-32.png"}}catch(_){}</script>
<style>html.work body{background:#07060d url(/bg-work.jpg) center/cover}body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#100c1f url(/bg.jpg) center/cover;font:15px/1.6 -apple-system,"Noto Sans TC","PingFang TC",sans-serif;color:#ece8f5}
.box{background:rgba(20,16,32,.92);border:1px solid #3a3450;border-radius:12px;padding:24px;width:min(92vw,380px);display:flex;flex-direction:column;gap:12px}
h1{font-size:19px;margin:0}input{font:inherit;padding:9px 11px;border-radius:8px;border:1px solid #3a3450;background:#0c0a16;color:#ece8f5}
button{font:inherit;padding:9px;border-radius:8px;border:0;background:#f0d34a;color:#241c00;font-weight:700;cursor:pointer}.m{color:#9a93ad;font-size:13px}.e{color:#fb7185;font-size:13px}a{color:#c9b6ff}
table{border-collapse:collapse;font-size:13px}td{padding:3px 8px 3px 0}</style></head><body><div class="box">${body}</div></body></html>`, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
const loginForm = (err = "", next = "/admin/") => page("管理者專區", `<h1>管理者專區</h1><div class="m">請輸入密碼</div>
<form method="post" action="/admin/login" style="display:flex;flex-direction:column;gap:10px"><input type="hidden" name="next" value="${next.replace(/"/g, "")}"><input type="password" name="pw" id="pw" autocomplete="current-password" autofocus required><button>登入</button></form>
${err ? `<div class="e">${err}</div>` : ""}<a href="/" class="m">← 回台股</a>`);
const TYPES = { html: "text/html; charset=utf-8", js: "application/javascript; charset=utf-8", json: "application/json", css: "text/css", png: "image/png", jpg: "image/jpeg" };
// 從 {"代號":[[…],…],…} 文字切出某檔的陣列文字（不 JSON.parse 整包）
function sliceArr(txt, code) {
  const key = JSON.stringify(code) + ":[", i = txt ? txt.indexOf(key) : -1;
  if (i < 0) return null;
  let j = i + key.length - 1, depth = 0;
  const st = j;
  for (; j < txt.length; j++) { const c = txt.charCodeAt(j); if (c === 91) depth++; else if (c === 93 && --depth === 0) break; }
  return txt.slice(st, j + 1);
}
// 底包＋近期包接起來（底包的日期都早於近期包）
function joinBars(a, b) {
  if (!a || a === "[]") return b; if (!b || b === "[]") return a;
  return a.slice(0, -1) + "," + b.slice(1);
}
async function usRoute(req, env, u) {
  const p = u.pathname;
  if (!env.US) return new Response("美股尚未設定", { status: 503 });
  if (p === "/admin/login" && req.method === "POST") {
    const f = await req.formData(), auth = await env.US.get("auth", "json");
    const next = /^\/admin\/[\w\-./?=%&]*$/.test(String(f.get("next") || "")) ? String(f.get("next")) : "/admin/";
    if (!auth || (await pbkdf2(String(f.get("pw") || ""), auth.salt, auth.iter)) !== auth.hash) return loginForm("密碼不對，請再試一次", next);
    const exp = String(Date.now() + 30 * 864e5);
    const h = new Headers({ location: next });
    h.append("set-cookie", `us_auth=${exp}.${await hmac(auth.hash, exp)}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax`);
    h.append("set-cookie", "adm=1; Path=/; Max-Age=2592000; Secure; SameSite=Lax");      // 讓台股頁知道可以跨到管理者專區搜尋（不含任何權限）
    return new Response(null, { status: 303, headers: h });
  }
  if (p === "/admin/logout") { const h = new Headers({ location: "/admin/login" }); h.append("set-cookie", "us_auth=; Path=/admin; Max-Age=0; HttpOnly; Secure; SameSite=Lax"); h.append("set-cookie", "us_auth=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Lax"); h.append("set-cookie", "adm=; Path=/; Max-Age=0; Secure; SameSite=Lax"); return new Response(null, { status: 303, headers: h }); }
  if (!(await usAuthed(req, env))) return p === "/admin/login" ? loginForm("", u.searchParams.get("next") || "/admin/") : new Response(null, { status: 303, headers: { location: "/admin/login?next=" + encodeURIComponent(p + u.search) } });
  if (p === "/admin/login") return new Response(null, { status: 303, headers: { location: "/admin/" } });
  if (p === "/admin/settings") {
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
        return new Response(null, { status: 303, headers: { location: "/admin/settings?ok=1", "set-cookie": `us_auth=${exp}.${await hmac(hash, exp)}; Path=/; Max-Age=2592000; HttpOnly; Secure; SameSite=Lax` } });
      }
    }
    if (u.searchParams.get("ok")) msg = `<div class="m" style="color:#7ee0a1">密碼已更新，其他裝置需要重新登入。</div>`;
    const meta = (await env.US.get("meta", "json")) || {};
    const cl = (await env.US.get("cron/last", "json")) || null;
    const dl = (await env.US.get("deploy/last", "json")) || null, dc = await env.US.get("deploy/check");
    const rows = [["排程最後觸發", cl ? `${new Date(cl.at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false })}　${cl.res.join("、")}` : (env.GH_TOKEN ? "尚未觸發" : "尚未設定 GitHub 金鑰")], ["部署看門狗", !env.CF_BUILD_TOKEN ? "尚未設定 CF_BUILD_TOKEN" : dl ? `最後補部署 ${new Date(dl.at).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false })}　${dl.ok ? "成功" : "失敗"}` : "已啟用（還沒需要補部署）"], ["看門狗權限檢查", dc || "還沒跑過（每 10 分鐘一次）"], ["資料日期（美東）", meta.asof], ["最後更新", meta.updated], ["股票數", meta.stocks], ["抓不到資料", meta.missingN ? `${meta.missingN} 檔（${(meta.missing || []).slice(0, 15).join("、")}${meta.missingN > 15 ? "…" : ""}）` : "無"]]
      .map(([a, b]) => `<tr><td class="m">${a}</td><td>${b ?? "—"}</td></tr>`).join("");
    return page("管理者專區｜資料庫狀態與管理", `<h1>資料庫狀態與管理</h1><table>${rows}</table>
<h1 style="font-size:16px;margin-top:6px">更改密碼</h1><form method="post" style="display:flex;flex-direction:column;gap:8px">
<input type="password" name="cur" placeholder="目前密碼" autocomplete="current-password" required><input type="password" name="n1" placeholder="新密碼（至少 6 個字）" autocomplete="new-password" required><input type="password" name="n2" placeholder="再輸入一次新密碼" autocomplete="new-password" required><button>更改密碼</button></form>${msg}
<div class="m"><a href="/admin/">← 回管理者專區</a>　<a href="/admin/logout">登出</a></div>`);
  }
  const sm = p.match(/^\/admin\/s\/([A-Za-z0-9.\-^]+)\.json$/);          // 個股 K 線：從分包裡取出那一檔
  if (sm) {
    let h = 0; for (const ch of sm[1]) h = (h * 31 + ch.charCodeAt(0)) % 1000003;
    // 方案 B：底包 site/sh/<h%256> ＋ 近期包 site/rc/<h%16>，各自用文字切出該檔再接起來（不解析整包，免費方案 CPU 只有約 10 毫秒）
    const [tb, tr] = await Promise.all([env.US.get("site/sh/" + (h % 256) + ".json"), env.US.get("site/rc/" + (h % 16) + ".json")]);
    const bars = joinBars(sliceArr(tb, sm[1]), sliceArr(tr, sm[1]));
    return bars ? new Response('{"bars":' + bars + "}", { headers: { "content-type": "application/json", "cache-control": "private, max-age=300" } }) : new Response("找不到", { status: 404 });
  }
  let key = "site/" + (p.slice(7) || "index.html");
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
    if (u.searchParams.get("key") === "draw-list/US")          // 分析程式讀美股畫線（只讀取、不寫入 KV）
      return new Response(JSON.stringify(await drawList(env, "US", true)), { headers: { "content-type": "application/json" } });
    const v = await env.US.get(u.searchParams.get("key") || "", "arrayBuffer");
    return v ? new Response(v) : new Response("not found", { status: 404 });
  }
  if (req.method === "PUT") {                       // 一次一個檔案、原始內容直接寫入（不解析，避免超過 Worker 的 CPU 上限）
    const k = u.searchParams.get("key") || "";
    if (!/^(site|state)\/[\w\-./]+$/.test(k) && k !== "meta") return new Response("bad key", { status: 400 });
    await env.US.put(k, await req.arrayBuffer());
    return new Response(JSON.stringify({ ok: true }), { headers: { "content-type": "application/json" } });
  }
  const j = await req.json();
  for (const [k, b64] of Object.entries(j.files || {})) {
    if (!/^(site|state)\//.test(k)) continue;
    await env.US.put(k, Uint8Array.from(atob(b64), c => c.charCodeAt(0)));
  }
  if (j.meta) await env.US.put("meta", JSON.stringify(j.meta));
  return new Response(JSON.stringify({ ok: true, n: Object.keys(j.files || {}).length }), { headers: { "content-type": "application/json" } });
}

// 備援：Yahoo 奇摩股市的台指期近一（WTX&）與現貨（WTX00），只有「目前時段」的報價，期交所連不上時使用
async function yahooTX() {
  const r = await fetch("https://tw.stock.yahoo.com/_td-stock/api/resource/StockServices.stockList;symbols=WTX%26%2CWTX00", { headers: { "user-agent": "Mozilla/5.0" } });
  if (!r.ok) return null;
  const arr = await r.json(), f = arr.find(x => x.symbol === "WTX&"), sp = arr.find(x => x.symbol === "WTX00");
  if (!f) return null;
  const raw = x => x && x.raw != null ? Number(x.raw) : null;
  const t = new Date(f.regularMarketTime), tw = new Date(t.getTime() + 8 * 3600e3);
  const hm = tw.getUTCHours() * 60 + tw.getUTCMinutes();
  const isDay = hm >= 525 && hm <= 830;
  const d0 = new Date(tw.getTime() - (hm < 300 ? 86400e3 : 0));               // 夜盤過了半夜，日期算開盤那天
  const ymd8 = d0.toISOString().slice(0, 10).replace(/-/g, ""), hms6 = tw.toISOString().slice(11, 19).replace(/:/g, "");
  const q = { id: "WTX&", name: f.symbolName, date: ymd8, time: hms6, o: raw(f.regularMarketOpen), h: raw(f.regularMarketDayHigh), l: raw(f.regularMarketDayLow),
              c: raw(f.price), ref: raw(f.regularMarketPreviousClose), v: Number(f.volume) || 0, oi: Number(f.openInterest) || null };
  const spot = sp ? { c: raw(sp.price), ref: raw(sp.regularMarketPreviousClose) } : null;
  return isDay ? { day: q, night: null, spot, spotNight: null, src: "yahoo" } : { day: null, night: q, spot: null, spotNight: spot ? { ref: spot.c } : null, src: "yahoo" };
}

// ── 管理者自己畫的型態線：KV 的 draw/<市場>/<代號>；所有人都能讀（管理者專區的美股本身就要登入），只有管理者能寫
async function drawRoute(req, env, u) {
  const m = u.searchParams.get("m"), c = u.searchParams.get("c") || "";
  if (!env.US || !/^(TW|US)$/.test(m) || !/^[A-Za-z0-9.\-^]{1,12}$/.test(c)) return new Response("bad", { status: 400 });
  const key = `draw/${m}/${c}`;
  if (req.method === "GET") {
    if (m === "US" && !(await usAuthed(req, env))) return new Response("[]", { headers: { "content-type": "application/json" } });
    return new Response((await env.US.get(key)) || "[]", { headers: { "content-type": "application/json", "cache-control": "no-store" } });
  }
  if (!(await usAuthed(req, env))) return new Response("請先登入管理者專區", { status: 403 });
  const list = await req.json();
  if (!Array.isArray(list) || list.length > 200) return new Response("bad", { status: 400 });
  const clean = list.map(d => ({ id: String(d.id || "").slice(0, 20), kind: ["poly", "line", "hline"].includes(d.kind) ? d.kind : "poly",
    name: String(d.name || "").slice(0, 30), note: String(d.note || "").slice(0, 200),
    pts: (d.pts || []).slice(0, 30).map(p => [String(p[0]).slice(0, 10), Number(p[1])]).filter(p => /^\d{4}-\d\d-\d\d$/.test(p[0]) && isFinite(p[1])) }));
  await env.US.put(key, JSON.stringify(clean));
  return new Response(JSON.stringify({ ok: true, n: clean.length }), { headers: { "content-type": "application/json" } });
}

// ── 排程：GitHub 自己的排程常常不準時或被略過，改由 Cloudflare 每 10 分鐘檢查一次、到點就叫 GitHub 開工（需要 Worker secret GH_TOKEN）
const REPO = "jrnobleyou-lgtm/tw-stock-pattern";
function jobsAt(t) {                                       // t 為 UTC 時間；回傳這個時間點要啟動的工作流程
  const d = t.getUTCDay(), hm = t.getUTCHours() * 60 + t.getUTCMinutes(), wk = d >= 1 && d <= 5, jobs = [];
  if (wk && hm === 50) jobs.push("intraday.yml");                                   // 台灣 08:50 盤中循環
  if (wk && hm >= 430 && hm <= 580 && hm % 30 === 10) jobs.push("update.yml");      // 台灣 15:10–17:40 上櫃收盤資料
  if (wk && hm >= 1320 && hm <= 1410 && hm % 30 === 0) jobs.push("update.yml");     // 台灣 隔天 06:00–07:30 上市收盤資料
  if (d >= 2 && d <= 6 && hm === 10) jobs.push("us.yml");                          // 台灣 08:10 美股（等 KV 每日寫入額度在台灣 08:00 重置後）
  if (d === 6 && hm === 1260) jobs.push("weekly-adjust.yml");                       // 台灣 週日 05:00 除權息檢查
  return jobs;
}
// ── 部署看門狗：GitHub deploy 分支有新版，但 Cloudflare 超過 4 分鐘沒開始部署 → 自動觸發一次（Worker secret CF_BUILD_TOKEN）
async function deployWatchdog(env) {
  if (!env.CF_BUILD_TOKEN || !env.GH_TOKEN) return;
  const cf = (path, init = {}) => fetch("https://api.cloudflare.com/client/v4" + path, { ...init,
    headers: { authorization: "Bearer " + env.CF_BUILD_TOKEN, "content-type": "application/json" } }).then(r => r.json());
  const gh = await fetch(`https://api.github.com/repos/${REPO}/commits/deploy`, {
    headers: { authorization: "Bearer " + env.GH_TOKEN, accept: "application/vnd.github+json", "user-agent": "tw-stock-pattern-cron" } }).then(r => r.json());
  const head = Date.parse(gh?.commit?.committer?.date || "");
  // 權限自我檢查：各步驟結果有變才寫 KV（deploy/check），省寫入額度
  const chk = async (txt) => { if (env.US && (await env.US.get("deploy/check")) !== txt) await env.US.put("deploy/check", txt); };
  const acc = (await cf("/accounts")).result?.[0]?.id; if (!acc) return chk("讀不到帳戶（缺 Account Settings 讀取權限？）");
  const tag = (await cf(`/accounts/${acc}/workers/scripts`)).result?.find(x => x.id === "news-findstockpattern-swing-breakout")?.tag; if (!tag) return chk("讀不到 Workers 指令碼（缺 Workers Scripts 讀取權限？）");
  const bl = await cf(`/accounts/${acc}/builds/workers/${tag}/builds?per_page=5`);
  if (!bl.success) return chk("讀不到部署紀錄（缺 Workers Builds Configuration 權限？）");
  await chk("正常");
  if (!head || Date.now() - head < 4 * 60000) return;                   // 剛推的先等 Cloudflare 自己處理
  const builds = bl.result || [];
  if (builds.some(b => b.status !== "stopped")) return;                  // 正在部署
  const last = Math.max(0, ...builds.map(b => Date.parse(b.created_on) || 0));
  if (last >= head) return;                                              // 已經部署過這一版
  const trig = (await cf(`/accounts/${acc}/builds/workers/${tag}/triggers`)).result?.[0]?.trigger_uuid; if (!trig) return;
  const r = await cf(`/accounts/${acc}/builds/triggers/${trig}/builds`, { method: "POST", body: JSON.stringify({ branch: "deploy" }) });
  if (env.US) await env.US.put("deploy/last", JSON.stringify({ at: new Date().toISOString(), ok: !!r.success }));
}

async function runSchedule(env, when) {
  try { await deployWatchdog(env); } catch (e) { console.log("watchdog", e); }
  const t = new Date(Math.round(when / 600000) * 600000), jobs = jobsAt(t);
  if (!jobs.length || !env.GH_TOKEN) return;
  const res = [];
  for (const wf of jobs) {
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${wf}/dispatches`, { method: "POST",
      headers: { authorization: "Bearer " + env.GH_TOKEN, accept: "application/vnd.github+json", "user-agent": "tw-stock-pattern-cron", "content-type": "application/json" },
      body: JSON.stringify({ ref: "main" }) });
    res.push(`${wf} ${r.status}`);
  }
  if (env.US) await env.US.put("cron/last", JSON.stringify({ at: new Date(when).toISOString(), res }));
}

// ── 管理者畫線清單（台股，公開）：分析程式用來以管理者的判斷取代系統的形態
async function drawList(env, m = "TW", span = false) {
  const out = {}; let cursor; const pre = `draw/${m}/`;
  do {
    const r = await env.US.list({ prefix: pre, cursor }); cursor = r.list_complete ? null : r.cursor;
    for (const k of r.keys) { const v = await env.US.get(k.name, "json"); if (Array.isArray(v) && v.length) out[k.name.slice(pre.length)] = v.map(d => span ? { name: d.name, kind: d.kind, d0: (d.pts || []).map(p => p[0]).sort()[0] || "", d1: (d.pts || []).map(p => p[0]).sort().pop() || "" } : d.name); }
  } while (cursor);
  return out;
}

export default {
  async scheduled(ev, env, ctx) { ctx.waitUntil(runSchedule(env, ev.scheduledTime)); },
  async fetch(req, env, ctx) {
    const u = new URL(req.url);
    if (u.pathname === "/api/draw-list") {
      // 預設：台股（公開，分析程式用）；?all=1：管理者的「我的畫線」，台股＋美股（美股要登入）
      const all = u.searchParams.get("all") === "1" && env.US && (await usAuthed(req, env));
      const body = !env.US ? {} : all ? { TW: await drawList(env, "TW"), US: await drawList(env, "US") } : await drawList(env, "TW", u.searchParams.get("span") === "1");   // ?span=1：附每條線的起訖日期（分析程式比對系統形態用）
      return new Response(JSON.stringify(body), { headers: { "content-type": "application/json", "cache-control": "no-store" } });
    }
    if (u.pathname === "/api/draw") return drawRoute(req, env, u);
    if (u.pathname === "/admin" || u.pathname === "/us" || u.pathname.startsWith("/us/")) return new Response(null, { status: 301, headers: { location: "/admin/" } });
    if (u.pathname.startsWith("/admin/")) {
      const r = await usRoute(req, env, u);
      // 早先登入的裝置沒有 adm 標記：只要帶著有效登入進入管理者專區，就補上（台股頁靠它把右上角改成「美股」）
      if (r.status === 200 && !/(?:^|;\s*)adm=1/.test(req.headers.get("cookie") || "") && (await usAuthed(req, env))) {
        const h = new Headers(r.headers); h.append("set-cookie", "adm=1; Path=/; Max-Age=2592000; Secure; SameSite=Lax");
        return new Response(r.body, { status: 200, headers: h });
      }
      return r;
    }
    if (u.pathname === "/api/us-ingest") return usIngest(req, env, u);
    if (u.pathname === "/api/tx") {
      try {
        const ck = new Request("https://cache.local/api/tx"), cache = caches.default;        // 同一節點 5 秒內共用一次結果，減少對期交所的請求
        const hit = await cache.match(ck); if (hit) return hit;
        const [d, n] = await Promise.all([taifexList(0), taifexList(1)]);
        const day = txPick(d), night = txPick(n);
        let out = { day: day.fut, night: night.fut, spot: day.spot, spotNight: night.spot, src: "taifex" };
        if (!out.day && !out.night) {
          const err = txErr;
          try { const y = await yahooTX(); if (y) out = y; } catch (e) { /* 兩邊都失敗 */ }
          out.dbg = { colo: (req.cf && req.cf.colo) || "", err };
        }
        const resp = new Response(JSON.stringify(out), { status: 200, headers: { "content-type": "application/json", "cache-control": "public, max-age=5" } });
        if (out.day || out.night) ctx.waitUntil(cache.put(ck, resp.clone()));
        return resp;
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
    const isUS = !/\.(TW|TWO)$|^\^/.test(sym);
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(isUS ? sym.replace(/\./g, "-") : sym)}?interval=1m&range=1d&includePrePost=false`;
    let out = { error: "unavailable" }, status = 502;
    let q = null;
    for (let k = 0; k < (isUS ? 0 : 3) && !q; k++) { if (k) await new Promise(r => setTimeout(r, 300)); try { q = await misQuote(sym); } catch (e) { misCookie = ""; misErr = "exc " + String(e).slice(0, 80); } }
    if (q) lastGood[sym] = { q, at: Date.now() };
    else if (lastGood[sym] && Date.now() - lastGood[sym].at < 90000) q = { ...lastGood[sym].q, stale: true };   // 失敗就換新的連線 cookie 再試一次
    try { if (q) return new Response(JSON.stringify(q), { status: 200, headers: { "content-type": "application/json", "cache-control": "public, max-age=3" } }); } catch (e) { /* 改用 Yahoo */ }
    try {
      const r = await fetch(url, { headers: { "user-agent": "Mozilla/5.0" }, cf: { cacheTtl: 20, cacheEverything: true } });
      if (r.ok) { const p = parseChart(await r.json()); if (p) { out = { ...p, src: isUS ? "yahoo-us" : "yahoo", delay: isUS ? 0 : 20, dbg: { colo: (req.cf && req.cf.colo) || "", misErr } }; status = 200; } }
    } catch (e) { /* 回傳 502 */ }
    if (status !== 200) out.dbg = { colo: (req.cf && req.cf.colo) || "", misErr };   // 失敗原因（在失敗之後才取，才是這次的結果）
    return new Response(JSON.stringify(out), { status, headers: { "content-type": "application/json", "cache-control": "public, max-age=5" } });
  },
};
