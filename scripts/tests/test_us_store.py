"""方案 B（美股 KV 底包＋近期包）的固定檢查。執行：python3 -m unittest discover -s scripts/tests"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import us_store as S

def make(ndays, codes=("NVDA", "AAPL", "TSLA", "APH", "ARM"), start=0):
    dates = [f"D{i:04d}" for i in range(start, start + ndays)]
    stocks = {c: [[d, 1.0, 2.0, 0.5, 1.5 + int(d[1:]), 100, 1.0] for d in dates] for c in codes}   # 同一天的價格固定
    return dates, stocks

class PlanB(unittest.TestCase):
    def test_first_run_writes_all_base_and_recent(self):
        dates, stocks = make(60)
        w, man = S.plan(dates, stocks, {}, weekday=2)
        base = [k for k in w if k.startswith("site/sh/")]
        rc = [k for k in w if k.startswith("site/rc/")]
        self.assertEqual(len(base), len({S.shard(c, 256) for c in stocks}))
        self.assertEqual(len(rc), len({S.shard(c, 16) for c in stocks}))
        self.assertEqual(man["base"]["cutoff"], dates[-5])

    def test_next_day_only_recent_changes(self):
        dates, stocks = make(60)
        w0, man = S.plan(dates, stocks, {}, weekday=2)
        dates2, stocks2 = make(60, start=1)                  # 往後一天：最早一天被拿掉、多一根新的
        w, man2 = S.plan(dates2, stocks2, man, weekday=3)
        self.assertEqual([k for k in w if k.startswith("site/sh/")], [])   # 底包不重寫
        self.assertTrue(all(k.startswith("site/rc/") for k in w))
        self.assertEqual(man2["base"], man["base"])

    def test_dividend_rewrites_only_that_base_shard(self):
        dates, stocks = make(60)
        w0, man = S.plan(dates, stocks, {}, weekday=2)
        stocks["APH"] = [r[:6] + [0.98] for r in stocks["APH"]]   # 除息：舊 K 棒的還原因子改了
        w, _ = S.plan(dates, stocks, man, weekday=3)
        self.assertEqual([k for k in w if k.startswith("site/sh/")], [f"site/sh/{S.shard('APH', 256)}.json"])

    def test_saturday_rebuilds(self):
        dates, stocks = make(60)
        w0, man = S.plan(dates, stocks, {}, weekday=2)
        dates2, stocks2 = make(60, start=4)
        w, man2 = S.plan(dates2, stocks2, man, weekday=5)
        self.assertEqual(man2["base"]["cutoff"], dates2[-5])
        self.assertGreater(len([k for k in w if k.startswith("site/sh/")]), 0)

    def test_stale_cutoff_forces_rebuild(self):
        dates, stocks = make(60)
        w0, man = S.plan(dates, stocks, {}, weekday=2)
        dates2, stocks2 = make(60, start=14)                  # 兩週多沒整理：近期包太長 → 重整
        w, man2 = S.plan(dates2, stocks2, man, weekday=3)
        self.assertEqual(man2["base"]["cutoff"], dates2[-5])

    def test_merge_restores_full_bars(self):
        dates, stocks = make(60)
        w, man = S.plan(dates, stocks, {}, weekday=2)
        import json
        for c in stocks:
            base = json.loads(w[f"site/sh/{S.shard(c, 256)}.json"])[c]
            rc = json.loads(w[f"site/rc/{S.shard(c, 16)}.json"])[c]
            got = base + rc
            want = [r for r in stocks[c] if r[0] >= man["base"]["start"]]
            self.assertEqual(got, want)

    def test_write_cap(self):
        self.assertRaises(SystemExit, S.check_cap, {f"k{i}": b"" for i in range(401)})
        S.check_cap({f"k{i}": b"" for i in range(400)})

if __name__ == "__main__":
    unittest.main()
