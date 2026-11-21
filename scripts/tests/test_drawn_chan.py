"""管理者畫的趨勢通道（11/21 台達電 2308）：用最新一根判斷在通道內／出界。"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import analyze as A

def bars(n, f):
    return [{"d": "2026-%02d-%02d" % (1 + i // 28, 1 + i % 28), "c": f(i)} for i in range(n)]

class DrawnChan(unittest.TestCase):
    def test_down_channel_inside(self):
        raw = bars(60, lambda i: 200 - i)               # 收盤 141
        ds = [b["d"] for b in raw]
        dr = [{"kind": "chan", "pts": [[ds[0], 205], [ds[59], 148], [ds[0], 195], [ds[59], 138]]}]
        r = A.drawn_channels(raw, dr)
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["kind"], "下降趨勢通道")
        self.assertEqual(r[0]["status"], "inchan")

    def test_break_above(self):
        raw = bars(60, lambda i: 200 - i if i < 59 else 190)
        ds = [b["d"] for b in raw]
        dr = [{"kind": "chan", "pts": [[ds[0], 205], [ds[59], 148], [ds[0], 195], [ds[59], 138]]}]
        r = A.drawn_channels(raw, dr)
        self.assertEqual(r[0]["status"], "break")
        self.assertEqual(r[0]["side"], 1)

    def test_ignores_other_kinds_and_old_format(self):
        raw = bars(10, lambda i: 10)
        self.assertEqual(A.drawn_channels(raw, [{"kind": "line", "pts": []}, "x", {"kind": "chan", "pts": [["a", 1]]}]), [])
