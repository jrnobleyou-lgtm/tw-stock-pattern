"""季營收、三率固定檢查（11/17）。"""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import margins as M


def months(vals):   # vals: {"2026Q3": [7月,8月,9月]} → {"2026-07": ...}
    out = {}
    for q, v in vals.items():
        y, n = int(q[:4]), int(q[-1])
        for k, x in enumerate(v):
            out[f"{y}-{(n - 1) * 3 + k + 1:02d}"] = x
    return out


class T(unittest.TestCase):
    def test_single(self):
        cum = {"2026Q2": [200, 80, 40, 30], "2026Q3": [330, 140, 70, 52]}
        self.assertEqual(M.single("2026Q3", cum, {}), [130, 60, 30, 22])
        self.assertEqual(M.single("2026Q1", {"2026Q1": [90, 30, 10, 8]}, {}), [90, 30, 10, 8])
        self.assertEqual(M.single("2026Q3", {"2026Q3": [330, 140, 70, 52]}, {"2026Q3": [130, 60, 30, 22]}), [130, 60, 30, 22])  # 缺前季累計 → FinMind
        self.assertIsNone(M.single("2026Q3", {"2026Q3": [330, 140, 70, 52]}, {}))

    def test_parse(self):
        self.assertEqual(M.parse_row({"公司代號": "1101", "年度": "115", "季別": "3", "營業收入": "112522875.00", "營業毛利（毛損）淨額": "21229246.00",
                                       "營業利益（損失）": "9571599.00", "本期淨利（淨損）": "7921300.00"}), ("1101", "2026Q3", [112522875, 21229246, 9571599, 7921300]))
        self.assertIsNone(M.parse_row({"SecuritiesCompanyCode": "", "Year": "", "Season": "", "營業收入": ""}))

    def test_quarter_math(self):
        self.assertEqual(M.q_add("2026Q1", -1), "2025Q4")
        self.assertEqual(M.q_add("2026Q3", -4), "2025Q3")
        self.assertIsNone(M.qrev({"2026-07": 1, "2026-08": 2}, "2026Q3"))      # 缺月不算
        self.assertEqual(M.qrev({"2026-07": 1, "2026-08": 2, "2026-09": 3}, "2026Q3"), 6)

    def test_summary(self):
        mm = months({"2025Q3": [100, 100, 100], "2026Q1": [90, 90, 90], "2026Q2": [100, 100, 100], "2026Q3": [120, 120, 120]})
        fm = {"2026Q2": [300, 90, 45, 30], "2026Q3": [360, 126, 72, 54]}   # 毛利率 30→35、營益率 15→20、淨利率 10→15
        s = M.summary({}, {"X": fm}, {"X": mm})["X"]
        r = s["q"][0]
        self.assertEqual(r[:4], ["115Q3", 360, 20.0, 20.0])               # 營收 360 vs 上季 300、去年同季 300
        self.assertEqual(r[4:7], [35.0, 20.0, 20.0 - 5.0])                # 毛利率 35、營益率 20、淨利率 15
        self.assertEqual(r[7:10], [5.0, 5.0, 5.0])
        self.assertTrue(s["m3"])
        self.assertEqual([x[0] for x in s["q"]], ["115Q3", "115Q2", "115Q1"])
        self.assertFalse(s["q"][0][10])                                   # 只有 4 季資料 → 不標歷史新高
        mm2 = months({f"{2023 + i // 4}Q{i % 4 + 1}": [10 + i] * 3 for i in range(13)})   # 13 季營收逐季成長 → 最新季創高
        fm3 = {"2026Q1": [1, 1, 1, 1]}
        r3 = M.summary({}, {"X": fm3}, {"X": mm2})["X"]["q"][0]
        self.assertEqual(r3[0], "115Q1")
        self.assertTrue(r3[10])
        fm2 = {"2026Q2": [300, 90, 45, 30], "2026Q3": [360, 126, 72, 30]}  # 淨利率下降 → 不算三升
        self.assertFalse(M.summary({}, {"X": fm2}, {"X": mm})["X"]["m3"])


if __name__ == "__main__":
    unittest.main()
