"""DMI 標籤固定檢查（2026-11-13 收盤資料）。執行：python3 -m unittest discover -s scripts/tests"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import analyze as A


def load(code):
    rows = json.load(open(os.path.join(HERE, "fixtures", code + ".json")))
    return [{"d": r[0], "o": r[1] * r[6], "h": r[2] * r[6], "l": r[3] * r[6], "c": r[4] * r[6], "v": r[5]} for r in rows]


def kd(bars):
    k_ = d_ = 50.0
    Ks, Ds = [], []
    for i in range(len(bars)):
        lo9 = min(b["l"] for b in bars[max(0, i - 8): i + 1]); hi9 = max(b["h"] for b in bars[max(0, i - 8): i + 1])
        rsv = 50.0 if hi9 == lo9 else (bars[i]["c"] - lo9) / (hi9 - lo9) * 100
        k_ = 2 / 3 * k_ + rsv / 3; d_ = 2 / 3 * d_ + k_ / 3
        Ks.append(k_); Ds.append(d_)
    return Ks, Ds


def tags(code):
    B = load(code)
    return A.dmi_tags(B, *kd(B)), B


class DMI(unittest.TestCase):
    def test_1216_fresh_cross_even_if_adx_falling(self):
        # 統一：+DI 剛穿過 -DI，ADX 25.9（3 天前 30.1，在下降）。剛交叉時 ADX 本來就會下降，仍要標剛翻多
        t, B = tags("1216")
        self.assertIn("DMI剛翻多", t)
        self.assertEqual(A.dmi_now(B)[2], -1)          # ADX 方向：下降

    def test_1409_about_to_cross(self):
        # 新纖：+DI 23.2 < -DI 25.2（差 2），兩線正在靠近 → 即將翻多
        t, _ = tags("1409")
        self.assertIn("DMI即將翻多", t)
        self.assertNotIn("DMI剛翻多", t)

    def test_1233_bull_needs_price_above_prev_high(self):
        # DMI 偏多、ADX ≥25 且上升，但收盤 28.3 沒站上前段高點 31.0 → 不算多頭趨勢（節目：價格要突破前段高點）
        t, B = tags("1233")
        self.assertNotIn("DMI多頭趨勢", t)
        self.assertGreater(A.prev_swing(B, len(B) - 1, True), B[-1]["c"])


if __name__ == "__main__":
    unittest.main()
