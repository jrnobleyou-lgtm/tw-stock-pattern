"""月營收、EPS 固定檢查（11/16）。"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import revenue as RV
import eps as EP


class T(unittest.TestCase):
    def test_eps_single_quarter(self):              # 台泥 115Q3 累計 0.63 = 0.10 + 0.29 + 0.24
        cum = {"2026Q1": 0.10, "2026Q2": 0.39, "2026Q3": 0.63}
        self.assertEqual(EP.single("2026Q3", cum, {}), 0.24)
        self.assertEqual(EP.single("2026Q1", cum, {}), 0.10)
        self.assertEqual(EP.single("2026Q3", {"2026Q3": 0.63}, {"2026Q3": 0.24}), 0.24)   # 缺前季累計 → FinMind
        self.assertIsNone(EP.single("2026Q3", {"2026Q3": 0.63}, {}))
        self.assertEqual(EP.single("2025Q4", {"2025Q3": -1.29, "2025Q4": -1.61}, {}), -0.32)   # Q4 累計＝全年
        s = EP.summary({"1101": cum}, {"1101": {"2025Q4": -0.32}})
        self.assertEqual(s["1101"], [["115Q3", 0.24], ["115Q2", 0.29], ["115Q1", 0.1]])

    def test_eps_parse(self):                         # 上市中文欄位、上櫃英文欄位
        self.assertEqual(EP.parse_row({"公司代號": "1101", "年度": "115", "季別": "3", "基本每股盈餘(元)": "0.63"}), ("1101", "2026Q3", 0.63))
        self.assertEqual(EP.parse_row({"SecuritiesCompanyCode": "1240", "Year": "115", "Season": "3", "基本每股盈餘（元）": "3.63"}), ("1240", "2026Q3", 3.63))
        self.assertIsNone(EP.parse_row({"公司代號": "", "年度": "", "季別": "", "基本每股盈餘（元）": ""}))

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
        d = self._mk(40, 100); d["2026-11"] = 300; many["E"] = d     # 月初先公布 11 月（全市場最新仍是 10 月）→ 也要標
        s = RV.summary(many)
        self.assertTrue(s["A"]["revHi"]); self.assertFalse(s["A"]["yoyHi"])
        self.assertFalse(s["B"]["revHi"])
        self.assertTrue(s["C"]["revHi"]); self.assertTrue(s["C"]["yoyHi"])
        self.assertEqual(len(s["C"]["rev"]), 6)
        self.assertTrue(s["E"]["revHi"]); self.assertTrue(s["E"]["yoyHi"])
        self.assertEqual(s["C"]["rev"][0][0], "2026-10")


if __name__ == "__main__":
    unittest.main()
