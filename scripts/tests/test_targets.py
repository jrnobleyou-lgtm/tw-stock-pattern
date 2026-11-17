import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import targets as T

NAMES = {"台積電": "2330", "貿聯-KY": "3665", "緯穎": "6669", "聯電": "2303"}
CODES = {v: k for k, v in NAMES.items()}


class TestTargets(unittest.TestCase):
    def test_factset(self):
        r = T.from_article({"title": "鉅亨速報 - Factset 最新調查：貿聯-KY(3665-TW)EPS預估上修至72.51元，預估目標價為3065元", "link": "u", "t": 100}, NAMES, CODES)
        self.assertEqual((r[0]["c"], r[0]["p"], r[0]["fs"]), ("3665", 3065.0, 1))

    def test_broker_title(self):
        r = T.from_article({"title": "大摩下調貿聯-KY 目標價至 2,500 元，但仍維持優於大盤投資評等", "link": "u", "t": 100}, NAMES, CODES)
        self.assertEqual((r[0]["c"], r[0]["p"], r[0]["who"], r[0]["d"]), ("3665", 2500.0, "大摩", -1))

    def test_unnamed_foreign_ignored(self):
        self.assertEqual(T.from_article({"title": "外資看好緯穎 目標價4000元", "link": "u", "t": 1}, NAMES, CODES), [])

    def test_two_stocks_ignored(self):
        self.assertEqual(T.from_article({"title": "高盛：台積電、聯電目標價分別3000、60元", "link": "u", "t": 1}, NAMES, CODES), [])

    def test_summarize_validate_and_stats(self):
        now = 10 ** 9
        rows = [{"c": "2330", "p": p, "who": w, "t": now - 86400, "title": "t", "link": "l" + w, "fs": 0, "d": 0} for p, w in ((3000, "A"), (3200, "B"), (3400, "C"), (99999, "D"))]
        o = T.summarize(rows, 2300, now)
        self.assertEqual((o["n"], o["hi"], o["lo"], o["med"]), (3, 3400, 3000, 3200))     # 99999 超過 3 倍現價，丟掉

    def test_old_and_direction(self):
        now = 10 ** 9
        rows = [{"c": "1", "p": 100, "who": "A", "t": now - 5 * 86400, "title": "", "link": "x", "fs": 0, "d": 0},
                {"c": "1", "p": 120, "who": "A", "t": now - 86400, "title": "", "link": "y", "fs": 0, "d": 0},
                {"c": "1", "p": 90, "who": "B", "t": now - 90 * 86400, "title": "", "link": "z", "fs": 0, "d": 0}]
        o = T.summarize(rows, 100, now)
        self.assertEqual(len(o["list"]), 1)
        self.assertEqual(o["list"][0]["d"], 1)


if __name__ == "__main__":
    unittest.main()
