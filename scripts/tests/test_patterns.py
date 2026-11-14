"""幾何形態的固定檢查（使用者確認過的案例）。執行：python3 -m unittest discover -s scripts/tests"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import patterns as PT

def load(code):
    rows = json.load(open(os.path.join(HERE, "fixtures", code + ".json")))
    return [{"d": r[0], "o": r[1] * r[6], "h": r[2] * r[6], "l": r[3] * r[6], "c": r[4] * r[6], "v": r[5]} for r in rows]

def geo(code):
    B = load(code)
    return [g for g in PT.detect_geometry(B, len(B) - 1) if g["status"] in ("confirmed", "near", "forming")]

def kinds(code):
    return [g["kind"] for g in geo(code)]

class Patterns(unittest.TestCase):
    def test_tsm_only_falling_wedge(self):
        # 11/14 使用者：頭肩頂（兩邊 76 天 vs 37 天）、頭肩底（右肩是今天）都不該算；三個形態共用 11/05 等多個轉折點只留一個
        k = kinds("TSM")
        self.assertIn("下降楔形", k)
        self.assertNotIn("頭肩頂", k)
        self.assertNotIn("頭肩底", k)

    def test_3374_asymmetric_double_bottom(self):
        self.assertIn("雙重底（不對稱）", kinds("3374"))

    def test_2454_v_bottom(self):
        self.assertIn("V形底", kinds("2454"))

    def test_2313_v_bottom(self):
        self.assertIn("V形底", kinds("2313"))

    def test_no_two_patterns_share_more_than_one_pivot(self):
        for code in ("TSM", "3374", "2454", "2313"):
            B = load(code); T = len(B) - 1
            gs = geo(code)
            for a in range(len(gs)):
                for b in range(a + 1, len(gs)):
                    pa = {i for i, _ in gs[a]["pts"] if i != T}
                    pb = {i for i, _ in gs[b]["pts"] if i != T}
                    self.assertLessEqual(len(pa & pb), 1, f"{code} {gs[a]['kind']} / {gs[b]['kind']}")

    def test_sorted_by_importance(self):
        rank = {"confirmed": 0, "near": 1, "forming": 2}
        for code in ("TSM", "3374", "2454", "2313"):
            r = [rank[g["status"]] for g in geo(code)]
            self.assertEqual(r, sorted(r), code)

if __name__ == "__main__":
    unittest.main()
