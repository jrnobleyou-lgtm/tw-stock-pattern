import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import exadj

PREV = {"2330": ("2026-11-17", 100.0), "1101": ("2026-11-17", 40.0), "2344": ("2026-11-17", 110.5), "9999": ("2026-11-17", 50.0)}


def row(c, cl, ch):
    return {"Code": c, "ClosingPrice": str(cl), "Change": str(ch)}


class TestExAdj(unittest.TestCase):
    def test_exdiv(self):                       # 昨收 100、今天參考價 96（除息 4 元）、收 97 → 漲跌價差 +1
        r = exadj.twse_adjust([row("2330", 97, 1)], PREV, "2026-11-18")
        self.assertEqual(r, [["2330", "2026-11-18", 0.96]])

    def test_normal_day(self):                  # 沒除權息：昨收 40、收 41、漲 1
        self.assertEqual(exadj.twse_adjust([row("1101", 41, 1)], PREV, "2026-11-18"), [])

    def test_zero_change_needs_list(self):      # 漲跌價差 0 但收盤和昨收差很多：只有預告表有列才採用
        rows = [row("2344", 108.0, 0.0)]
        self.assertEqual(exadj.twse_adjust(rows, PREV, "2026-11-18"), [])
        self.assertEqual(exadj.twse_adjust(rows, PREV, "2026-11-18", {"2344"}), [["2344", "2026-11-18", round(108.0 / 110.5, 6)]])

    def test_already_have_and_stale(self):
        self.assertEqual(exadj.twse_adjust([row("2330", 97, 1)], PREV, "2026-11-18", (), {("2330", "2026-11-18")}), [])
        self.assertEqual(exadj.twse_adjust([row("2330", 97, 1)], PREV, "2026-11-17"), [])      # 同一天不比
        self.assertEqual(exadj.twse_adjust([row("0050", 97, 1)], PREV, "2026-11-18"), [])      # ETF／不在清單

    def test_bad_values(self):
        self.assertEqual(exadj.twse_adjust([{"Code": "2330", "ClosingPrice": "--", "Change": " "}], PREV, "2026-11-18"), [])


if __name__ == "__main__":
    unittest.main()
