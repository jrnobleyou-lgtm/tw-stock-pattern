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


class ApplyPatterns(unittest.TestCase):
    BEAR = [{"kind": "V形頂", "dir": "bear", "status": "confirmed", "day": 2, "neck": None}]

    def test_strong_stays_strong_with_warning(self):
        # 11/15 使用者：轉強優先於走弱；看跌形態只加警示標籤
        st, tags, sub = EN.apply_patterns("轉強", ["站回5/10日線"], None, self.BEAR)
        self.assertEqual(st, "轉強")
        self.assertIn("⚠V形頂", tags)
        self.assertIn("站回5/10日線", tags)
        self.assertIsNone(sub)

    def test_bear_pattern_still_weakens_when_not_strong(self):
        st, tags, sub = EN.apply_patterns("盤整", [], None, self.BEAR)
        self.assertEqual(st, "走弱")
        self.assertEqual(sub, "回檔走弱")


class TestVLate(unittest.TestCase):
    """11/17 使用者：V 形底第 4～10 天只加標籤，不改五種型態（比照島型反轉）"""
    def geo(self, day):
        return [{"kind": "V形底", "status": "confirmed", "dir": "bull", "day": day, "neck": None}]

    def test_early_v_changes_state(self):
        st, tags, sub = EN.apply_patterns("走弱", [], "破底走弱", self.geo(2))
        self.assertEqual(st, "轉強")

    def test_late_v_keeps_state_but_tags(self):
        st, tags, sub = EN.apply_patterns("走弱", [], "破底走弱", self.geo(6))
        self.assertEqual(st, "走弱")
        self.assertEqual(sub, "破底走弱")
        self.assertIn("V形底", tags)
