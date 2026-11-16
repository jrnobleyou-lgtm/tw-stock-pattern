"""月營收、EPS 固定檢查（11/16）。"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import revenue as RV
import eps as EP


class T(unittest.TestCase):
    def test_eps_single_quarter(self):              # 台泥 115Q3 累計 0.63 = 0.10 + 0.29 + 0.24
        self.assertEqual(EP.single_from_cum("2026Q3", 0.63, {"2026Q1": 0.10, "2026Q2": 0.29}), 0.24)
        self.assertEqual(EP.single_from_cum("2026Q1", 0.10, {}), 0.10)
        self.assertIsNone(EP.single_from_cum("2026Q3", 0.63, {"2026Q2": 0.29}))

    def test_roc(self):
        self.assertEqual(RV.roc_ym("11510"), "2026-10")
        self.assertEqual(RV.ym_add("2026-01", -1), "2025-12")

    def _mk(self, n, last_val, base=100):
        d, ym = {}, "2026-10"
        for k in range(n):
            d[RV.ym_add(ym, -k)] = base + (k % 5)
        d[ym] = last_val
        return d

    def test_rev_hi(self):
        many = {f"X{i}": self._mk(40, 100) for i in range(120)}       # 讓 2026-10 成為全市場最新月
        many["A"] = self._mk(13, 200)      # 13 個月、最新最高 → 創新高；不足 36 個月 → 不標年增新高
        many["B"] = self._mk(12, 200)      # 只有 12 個月 → 不標
        many["C"] = self._mk(40, 200)      # 40 個月、歷史新高且年增 > 0 → 兩個都標
        s = RV.summary(many)
        self.assertTrue(s["A"]["revHi"]); self.assertFalse(s["A"]["yoyHi"])
        self.assertFalse(s["B"]["revHi"])
        self.assertTrue(s["C"]["revHi"]); self.assertTrue(s["C"]["yoyHi"])
        self.assertEqual(len(s["C"]["rev"]), 6)
        self.assertEqual(s["C"]["rev"][0][0], "2026-10")


if __name__ == "__main__":
    unittest.main()
