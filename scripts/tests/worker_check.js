// Worker 的固定檢查（11/19）：不連網，只測純函式與登入驗證。執行：node scripts/tests/worker_check.js
const fs = require("fs"), vm = require("vm"), path = require("path"), assert = require("assert");
const src = fs.readFileSync(path.join(__dirname, "..", "..", "site", "worker.js"), "utf8").replace("export default", "globalThis.__W =");
const ctx = { crypto: globalThis.crypto, TextEncoder, URL, Response, Request, fetch: () => { throw new Error("不可連網"); }, console };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(src + "\nglobalThis.__F={misChannel,txPick,sliceArr,joinBars,jobsAt,usAuthed,hmac};", ctx);
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
  console.log(process.exitCode ? "有失敗" : `Worker 固定檢查 ${n} 組通過`);
})();
