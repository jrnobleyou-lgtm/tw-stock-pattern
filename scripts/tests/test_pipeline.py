"""整條判斷流程（盤整區間→五種型態→形態→打架）的固定案例（11/17，Fable 建議補的）。
案例的「預期值」是 11/17 使用者確認過規則後的結果；規則故意改動而讓這裡失敗時，要先確認新結果是對的再更新。"""
import json, os, sys, unittest
HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, ".."))
import engine as E
import patterns as PT


def run(code):
    rows = json.load(open(os.path.join(HERE, "fixtures", code + ".json")))
    bars = [{"d": r[0], "o": r[1] * r[6], "h": r[2] * r[6], "l": r[3] * r[6], "c": r[4] * r[6], "v": r[5]} for r in rows]
    T = len(bars) - 1
    closes = [b["c"] for b in bars]
    ma = {n: E.sma(closes, n) for n in (5, 10, 20, 60)}
    box, ev = E.current_box(bars, T)
    state, tags, sub = E.classify(bars, ma[5], ma[10], ma[20], ma[60], T, box, ev)
    geo = [g for g in PT.detect_geometry(bars, T) if g["status"] in ("confirmed", "near", "forming", "hist")]
    state, tags, sub = E.apply_patterns(state, tags, sub, geo)
    return state, tags, sub, geo, box, ev


class Pipeline(unittest.TestCase):
    def test_all_fixtures_run(self):                     # 每個案例整條流程都跑得完、型態是五種之一、形態兩兩不共用 ≥2 個轉折點
        for code in ("1216", "1233", "1409", "2313", "2368", "2454", "3374", "3617", "TSM", "4609", "6146", "2406", "1201"):
            state, tags, sub, geo, box, ev = run(code)
            self.assertIn(state, ("轉強", "弱轉強", "型態好", "盤整", "走弱"), code)
            for i, a in enumerate(geo):
                for b in geo[i + 1:]:
                    pa = set(a["pivots"]) if a.get("pivots") else {x for x, _ in a["pts"]}
                    pb = set(b["pivots"]) if b.get("pivots") else {x for x, _ in b["pts"]}
                    self.assertLessEqual(len(pa & pb), 1, (code, a["kind"], b["kind"]))

    def test_frozen_states(self):                        # 11/17 當天資料的結果（轉強優先於走弱的案例 4609、6146 當時的資料已不再是轉強，改用合成資料檢查，見 test_engine）
        self.assertEqual(run("6146")[0], "轉強")
        self.assertEqual(run("4609")[0], "走弱")

    def test_2454_2313_v_bottom_label(self):             # 使用者畫過的 V 形底，系統要認得
        for code in ("2454", "2313"):
            self.assertTrue(any(g["kind"] == "V形底" for g in run(code)[3]) or "V形底" in " ".join(run(code)[1]), code)


if __name__ == "__main__":
    unittest.main()
