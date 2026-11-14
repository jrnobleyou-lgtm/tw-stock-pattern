"""盤整區間跌破／突破狀態的固定檢查。執行：python3 -m unittest discover -s scripts/tests"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import engine as EN

def load(code):
    rows = json.load(open(os.path.join(HERE, "fixtures", code + ".json")))
    return [{"d": r[0], "o": r[1] * r[6], "h": r[2] * r[6], "l": r[3] * r[6], "c": r[4] * r[6], "v": r[5]} for r in rows]

class Engine(unittest.TestCase):
    def test_2368_broken_range_is_not_false_breakdown(self):
        # 11/14 使用者：金像電 10/30 跌破區間（下緣 1055），中間雖有反彈，但後來又連續收在下緣之下，區間已失效，不能還標「假跌破」
        B = load("2368")
        box, ev = EN.current_box(B, len(B) - 1)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["dir"], "down")
        self.assertNotEqual(ev["state"], "false_breakdown")

if __name__ == "__main__":
    unittest.main()
