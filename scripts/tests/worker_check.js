// Worker 的固定檢查（11/19）：不連網，只測純函式與登入驗證。執行：node scripts/tests/worker_check.js
const fs = require("fs"), vm = require("vm"), path = require("path"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "site", "worker.js"), "utf8").replace("export default", "globalThis.__W =");
const ctx = { crypto: globalThis.crypto, TextEncoder, URL, Response, Request, fetch: () => { throw new Error("不可連網"); }, console };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(src + "\nglobalThis.__F={misChannel,txPick,sliceArr,joinBars,jobsAt,usAuthed,hmac,autoRecmp,recmpDirtySweep};", ctx);
const F = ctx.__F;
let n = 0; const t = (name, f) => Promise.resolve().then(f).then(() => { n++; }, e => { console.error("失敗：" + name + "\n", e.message); process.exitCode = 1; });

(async () => {
  await t("證交所頻道", () => {
    assert.strictEqual(F.misChannel("^TWII"), "tse_t00.tw");
    assert.strictEqual(F.misChannel("^TWOII"), "otc_o00.tw");
    assert.strictEqual(F.misChannel("2330.TW"), "tse_2330.tw");
    assert.strictEqual(F.misChannel("6488.TWO"), "otc_6488.tw");
    assert.strictEqual(F.misChannel("00981A.TW"), "tse_00981a.tw");
    assert.strictEqual(F.misChannel("AAPL"), null);
  });
  await t("台指期挑近月", () => {
    const r = F.txPick([{ SymbolID: "TXF-S", CLastPrice: "100" }, { SymbolID: "TXFK6-F", CLastPrice: "38,x", CRefPrice: "200" }, { SymbolID: "TXFL6-F", CLastPrice: "300" }]);
    assert.strictEqual(r.fut.id, "TXFK6-F"); assert.strictEqual(r.spot.id, "TXF-S"); assert.strictEqual(r.fut.c, 38);
    assert.strictEqual(JSON.stringify(F.txPick(null)), '{"fut":null,"spot":null}');   // vm 內外的物件不同源，用字串比
  });
  await t("美股 K 線切包與接包", () => {
    const txt = '{"AAPL":[[1,2],[3,[4]]],"ARM":[[9]]}';
    assert.strictEqual(F.sliceArr(txt, "AAPL"), "[[1,2],[3,[4]]]");
    assert.strictEqual(F.sliceArr(txt, "ARM"), "[[9]]");
    assert.strictEqual(F.sliceArr(txt, "NVDA"), null);
    assert.strictEqual(F.joinBars("[[1]]", "[[2]]"), "[[1],[2]]");
    assert.strictEqual(F.joinBars("[]", "[[2]]"), "[[2]]");
    assert.strictEqual(F.joinBars("[[1]]", null), "[[1]]");
  });
  await t("排程時間（UTC → 台灣）", () => {
    const J = s => F.jobsAt(new Date(s)).sort().join(",");
    assert.strictEqual(J("2026-11-16T00:50:00Z"), "intraday.yml");                    // 週一台灣 08:50
    assert.strictEqual(J("2026-11-16T07:10:00Z"), "update.yml");                      // 週一台灣 15:10 上櫃收盤
    assert.strictEqual(J("2026-11-16T22:00:00Z"), "news.yml,update.yml");             // 週二台灣 06:00 上市收盤＋新聞
    assert.strictEqual(J("2026-11-17T00:10:00Z"), "us.yml");                          // 週二台灣 08:10 美股
    assert.ok(!F.jobsAt(new Date("2026-11-15T00:10:00Z")).includes("us.yml"));        // 週日（UTC）不跑美股
    assert.ok(F.jobsAt(new Date("2026-11-14T21:00:00Z")).includes("weekly-adjust.yml")); // 台灣週日 05:00
    assert.ok(!F.jobsAt(new Date("2026-11-16T00:20:00Z")).includes("intraday.yml"));
    assert.ok(F.jobsAt(new Date("2026-11-16T02:00:00Z")).includes("news.yml"));       // 平日每 30 分
    assert.ok(!F.jobsAt(new Date("2026-11-14T02:30:00Z")).includes("news.yml"));      // 週末只有整點
    assert.ok(F.jobsAt(new Date("2026-11-14T02:00:00Z")).includes("news.yml"));
    assert.ok(F.jobsAt(new Date("2026-11-16T17:00:00Z")).includes("news.yml"));       // 台灣 01:00 夜間補一輪
    assert.ok(F.jobsAt(new Date("2026-11-16T19:30:00Z")).includes("news.yml"));       // 台灣 03:30
    assert.ok(!F.jobsAt(new Date("2026-11-16T18:00:00Z")).includes("news.yml"));      // 其他夜間時段不跑
  });
  await t("登入驗證", async () => {
    const hash = "ab".repeat(32), exp = String(Date.now() + 3600e3), sig = await F.hmac(hash, exp);
    const env = a => ({ US: { get: async () => a } });
    const req = c => ({ headers: { get: k => (k === "cookie" ? c : "") } });
    assert.strictEqual(await F.usAuthed(req(`us_auth=${exp}.${sig}`), env({ hash })), true);
    assert.strictEqual(await F.usAuthed(req(`x=1; us_auth=${exp}.${sig}`), env({ hash })), true);
    assert.strictEqual(await F.usAuthed(req(`us_auth=${exp}.${sig}`), env(null)), false);            // 沒設密碼
    assert.strictEqual(await F.usAuthed(req(`us_auth=${exp}.${"0".repeat(64)}`), env({ hash })), false); // 簽章錯
    assert.strictEqual(await F.usAuthed(req(`us_auth=${exp}.${sig}`), env({ hash: "cd".repeat(32) })), false); // 改密碼後舊登入失效
    const old = String(Date.now() - 1000);
    assert.strictEqual(await F.usAuthed(req(`us_auth=${old}.${await F.hmac(hash, old)}`), env({ hash })), false); // 過期
    assert.strictEqual(await F.usAuthed(req(""), env({ hash })), false);
  });
  await t("畫線變動自動重算：送出、連續修改合併、排程補送", async () => {
    const kv = new Map(), calls = [];
    const env = { GH_TOKEN: "x", US: { get: async (k, ty) => { const v = kv.get(k); return v == null ? null : (ty === "json" ? JSON.parse(v) : v) }, put: async (k, v) => { kv.set(k, v) }, delete: async k => { kv.delete(k) } } };
    ctx.fetch = async (url) => { calls.push(String(url)); return { status: 204 } };
    await F.autoRecmp(env, "TW");                       // 第一次：立刻送出 recompare.yml
    assert.strictEqual(calls.length, 1); assert.ok(calls[0].includes("recompare.yml")); assert.ok(!kv.has("recmp/dirty/TW"));
    await F.autoRecmp(env, "TW");                       // 3 分鐘內再改：不重送，記下待重算
    assert.strictEqual(calls.length, 1); assert.ok(kv.has("recmp/dirty/TW"));
    await F.recmpDirtySweep(env);                       // 排程：還沒過 1 分鐘＋冷卻中，不送
    assert.strictEqual(calls.length, 1);
    kv.set("recmp/dirty/TW", String(Date.now() - 200000)); kv.set("recmp/TWd", JSON.stringify({ at: Date.now() - 400000 }));
    await F.recmpDirtySweep(env);                       // 過了冷卻：補送一次並清掉標記
    assert.strictEqual(calls.length, 2); assert.ok(!kv.has("recmp/dirty/TW"));
    await F.autoRecmp(env, "US"); assert.ok(calls[2].includes("us_recompare.yml"));
    ctx.fetch = () => { throw new Error("不可連網") };
  });
  console.log(process.exitCode ? "有失敗" : `Worker 固定檢查 ${n} 組通過`);
})();
