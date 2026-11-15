"""島型反轉固定檢查（11/15 使用者：標籤最多 10 天、跌回島內就消失；K 線圖上的島畫 30 天）。"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import patterns as PT, engine as EN


def load(code):
    rows = json.load(open(os.path.join(HERE, "fixtures", code + ".json")))
    return [{"d": r[0], "o": r[1] * r[6], "h": r[2] * r[6], "l": r[3] * r[6], "c": r[4] * r[6], "v": r[5]} for r in rows]


class Island(unittest.TestCase):
    def test_3617_island_day5_still_tagged(self):
        # 碩天：11/06 向下跳空（高 218 < 前一天低 222.5）、11/09 向上跳空（低 234）→ 單日島型反轉底；11/13 是第 5 天，仍要標
        B = load("3617"); T = len(B) - 1
        isl = [g for g in PT.detect_geometry(B, T) if "島型" in g["kind"]]
        self.assertEqual(len(isl), 1)
        self.assertEqual(isl[0]["kind"], "單日島型反轉底")
        self.assertEqual(isl[0]["status"], "confirmed")
        _, tags, _ = EN.apply_patterns("弱轉強", [], None, isl)
        self.assertIn("單日島型反轉底", tags)

    def test_3617_day_limits(self):
        # 用 11/09 之後的天數模擬：第 10 天還標（confirmed），第 11～30 天只畫在圖上（hist），之後不再出現
        B = load("3617"); T = len(B) - 1
        b = next(i for i in range(len(B)) if B[i]["d"] == "2026-11-09")
        isl_hi = 218.0
        # 往後補 30 根守在島之上的平盤 K 棒
        ext = B + [{"d": f"2027-01-{k + 1:02d}", "o": 279, "h": 281, "l": 277, "c": 279, "v": 1000} for k in range(30)]
        for day, want in ((10, "confirmed"), (11, "hist"), (30, "hist"), (31, None)):
            t = b + day - 1
            g = [x for x in PT.island(ext[:t + 1], t) if "島型" in x["kind"]]
            got = g[0]["status"] if g and g[0]["status"] in ("confirmed", "hist") else None
            self.assertEqual(got, want, f"第 {day} 天")
        self.assertLess(isl_hi, min(x["c"] for x in ext[b:]))

    def test_failed_when_back_into_island(self):
        # 跌回島裡（收盤 ≤ 島的最高 218）→ 失敗，不標也不畫
        B = load("3617")
        ext = B + [{"d": "2026-12-01", "o": 230, "h": 231, "l": 210, "c": 215, "v": 1000}]
        t = len(ext) - 1
        g = [x for x in PT.island(ext, t) if "島型" in x["kind"]]
        self.assertTrue(not g or g[0]["status"] == "failed")


if __name__ == "__main__":
    unittest.main()
