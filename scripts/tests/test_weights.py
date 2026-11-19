import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analyze


def st(pc, c, chg=0.0, **k):
    d = {"_w": (pc, c), "chg": chg}; d.update(k); return d


class TestWeights(unittest.TestCase):
    def test_basic(self):
        # A：市值 80（100×0.8），漲 10%；B：市值 20（100×0.2），跌 10%。指數 10000
        S = {"A": st(100, 110), "B": st(100, 90)}
        r = analyze.index_weights(S, {"A": 0.8, "B": 0.2}, 10000)
        self.assertEqual(S["A"]["wt"], 80.0); self.assertEqual(S["B"]["wt"], 20.0)
        self.assertAlmostEqual(S["A"]["wc"], 800.0, places=1); self.assertAlmostEqual(S["B"]["wc"], -200.0, places=1)
        self.assertAlmostEqual(r["all"], 600.0, places=1)

    def test_exdiv_uses_raw(self):             # 除息：未還原價跌 5%（還原後只跌 0），指數會跟著跌，貢獻要用未還原
        S = {"A": st(100, 95, chg=0.0)}
        analyze.index_weights(S, {"A": 1.0}, 10000)
        self.assertAlmostEqual(S["A"]["wc"], -500.0, places=1)

    def test_split_uses_adjusted(self):        # 分割：未還原價腰斬（>10.5%），改用還原後漲跌幅 +2%
        S = {"A": st(100, 50, chg=2.0)}
        analyze.index_weights(S, {"A": 1.0}, 10000)
        self.assertAlmostEqual(S["A"]["wc"], 200.0, places=1)

    def test_skip_and_top(self):               # 沒股數（ETF、TDR）、新股不算；只寫前 top 名
        S = {"A": st(100, 101), "E": st(10, 10), "N": st(10, 11, new=1), "B": st(50, 50)}
        r = analyze.index_weights(S, {"A": 1.0, "B": 1.0, "N": 1.0}, 10000, top=1)
        self.assertEqual(r["n"], 2); self.assertIn("wt", S["A"]); self.assertNotIn("wt", S["B"]); self.assertNotIn("wt", S["E"]); self.assertNotIn("wt", S["N"])
        self.assertNotIn("_w", S["E"])

    def test_stale_zero(self):
        S = {"A": st(100, 100, stale="11-10")}
        analyze.index_weights(S, {"A": 1.0}, 10000)
        self.assertEqual(S["A"]["wc"], 0.0)


if __name__ == "__main__":
    unittest.main()
