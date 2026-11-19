import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analyze


def mk(w5, tv5, vr_ok=False, chg=0):
    v20 = 100.0
    return {"tags": [], "chg": chg, "close": 10, "_s": {"w5": w5, "tv": tv5, "tv5": tv5, "vt": 100, "v5": 160 if vr_ok else 100, "v20": v20, "vp5": 100, "a20": 1}}


class TestStrong(unittest.TestCase):
    def run_it(self, us):
        base = 1e8 if not us else 1e7
        st = {}
        for i in range(150):                              # 150 檔普通股：近 5 日漲 0%
            st["N%d" % i] = mk(0.0, base * (1 + i / 10))
        st["BIG_OK"] = mk(6.0, base * 1000)               # 大型股：漲 6% → 要標（大型）
        st["BIG_LOW"] = mk(3.0, base * 1000)              # 大型股漲 3% → 不標
        st["SMALL6"] = mk(6.0, base * 1.5)                # 小型股漲 6% → 不標
        st["SMALL12"] = mk(12.0, base * 1.5, vr_ok=True)  # 小型股漲 12%＋量增 → 本週強勢
        st["BIG12"] = mk(12.0, base * 1000, vr_ok=True)   # 大型股同時符合原條件 → 只標原本那個
        analyze.strong_flags(st, None, us=us)
        self.assertIn("本週強勢（大型）", st["BIG_OK"]["tags"])
        self.assertEqual(st["BIG_LOW"]["tags"], [])
        self.assertEqual(st["SMALL6"]["tags"], [])
        self.assertEqual(st["SMALL12"]["tags"], ["本週強勢"])
        self.assertEqual(st["BIG12"]["tags"], ["本週強勢"])

    def test_tw(self): self.run_it(False)
    def test_us(self): self.run_it(True)


if __name__ == "__main__":
    unittest.main()


class TestLimitAndLive(unittest.TestCase):
    def test_limit_price_tick(self):            # 昨收 93 → 漲停價 102.0（>100 用 0.5 檔位）；48 → 52.8→52.8? 48*1.1=52.8 落在 50~100，0.1 檔 → 52.8
        def lu(pc, c): return analyze.at_limit_up({"pc": pc, "close": c})
        self.assertTrue(lu(93, 102.0)); self.assertFalse(lu(93, 101.5))
        self.assertTrue(lu(48, 52.8)); self.assertFalse(lu(48, 52.7))
        self.assertTrue(lu(9.2, 10.1)); self.assertFalse(lu(9.2, 10.05))

    def test_stale_live_not_partial(self):      # 暫時價日期不是台灣今天 → 不算盤中，今日強勢照標
        import datetime
        tw = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
        old = (tw - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        st = {"A%d" % i: mk(0.0, 1e8 * (1 + i / 10)) for i in range(60)}
        st["UP"] = mk(0.0, 1e8, chg=8.0)
        for s in st.values(): s.setdefault("chg", 0)
        analyze.strong_flags(st, {"date": old, "hms": "13:30"})
        self.assertIn("今日強勢", st["UP"]["tags"])
