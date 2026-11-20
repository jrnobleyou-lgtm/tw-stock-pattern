"""趨勢通道的固定檢查（使用者畫過的案例要全抓到；沒方向的盤整誤判要很少）。執行：python3 -m unittest discover -s scripts/tests"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import patterns as PT

def load(code):
    rows = json.load(open(os.path.join(HERE, "fixtures", code + ".json")))
    return [{"d": r[0], "o": r[1] * r[6], "h": r[2] * r[6], "l": r[3] * r[6], "c": r[4] * r[6], "v": r[5]} for r in rows]

class Channel(unittest.TestCase):
    def chan(self, code):
        B = load(code)
        return PT.detect_channel(B, len(B) - 1)

    def test_user_drawn_cases(self):
        want = {"6488": "下降趨勢通道", "6725": "下降趨勢通道", "2412": "上升趨勢通道", "6782": "上升趨勢通道", "6515": "下降趨勢通道"}
        for code, kind in want.items():
            r = self.chan(code)
            self.assertIsNotNone(r, code)
            self.assertEqual(r["kind"], kind, code)
            self.assertEqual(r["status"], "inchan", code)

    def test_2412_has_short_channel_like_user_drawing(self):
        B = load("2412")
        r = PT.detect_channels(B, len(B) - 1)
        short = [c for c in r if c["which"] == "短"]
        self.assertTrue(short)
        self.assertTrue(30 <= short[0]["L"] <= 40)        # 使用者畫的是最近約 35 天
        self.assertEqual(short[0]["kind"], "上升趨勢通道")

    def test_flat_series_has_no_channel(self):
        B = [{"d": str(i), "o": 100, "h": 101 + (i % 3), "l": 99 - (i % 2), "c": 100 + (i % 4 - 1.5), "v": 1} for i in range(200)]
        self.assertIsNone(PT.detect_channel(B, len(B) - 1))

    def test_short_series_is_safe(self):
        self.assertIsNone(PT.detect_channel(load("6488")[:20], 19))

    def test_lines_parallel(self):
        r = self.chan("6782")
        (a, pa, b, pb), (c, pc, d, pd) = r["lines"]
        self.assertAlmostEqual((pb - pa) / (b - a), (pd - pc) / (d - c), places=6)

if __name__ == "__main__":
    unittest.main()
