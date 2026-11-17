import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import news as N


def L(*names):
    return [{"name": "models/" + n, "supportedGenerationMethods": ["generateContent"]} for n in names]


NOW = L("gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.5-pro", "gemini-3.5-flash-preview-05", "gemini-3-flash", "text-embedding-004", "gemma-3-27b")


class TestPick(unittest.TestCase):
    def test_current(self):
        self.assertEqual(N.pick_models(NOW)[0], ["gemini-3.5-flash-lite", "gemini-3.5-flash"])

    def test_new_version_wins(self):
        r, _ = N.pick_models(NOW + L("gemini-4-flash-lite", "gemini-4-flash", "gemini-4-flash-lite-preview"))
        self.assertEqual(r[:2], ["gemini-4-flash-lite", "gemini-4-flash"])
        self.assertIn("gemini-3.5-flash-lite", r)            # 舊型號還在時留作後備

    def test_removed(self):
        r, _ = N.pick_models(L("gemini-4-flash-lite", "gemini-4-flash"))
        self.assertEqual(r, ["gemini-4-flash-lite", "gemini-4-flash"])

    def test_never_downgrade(self):
        r, _ = N.pick_models(L("gemini-2.5-flash", "gemini-2.5-flash-lite"))
        self.assertEqual(r, [])                               # 都比預設舊：不用，呼叫端退回寫死預設

    def test_empty(self):
        self.assertEqual(N.pick_models([])[0], [])
        self.assertEqual(N.pick_models(None)[0], [])

    def test_unrecognised_flash_reported(self):
        _, odd = N.pick_models(NOW + L("gemini-flash-4"))
        self.assertIn("gemini-flash-4", odd)


if __name__ == "__main__":
    unittest.main()
