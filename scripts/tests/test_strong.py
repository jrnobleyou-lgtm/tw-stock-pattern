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
