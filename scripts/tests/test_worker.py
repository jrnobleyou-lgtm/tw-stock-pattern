"""Worker 固定檢查：呼叫 node scripts/tests/worker_check.js（沒有 node 就略過）。"""
import os, shutil, subprocess, unittest

class TestWorker(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "沒有 node")
    def test_worker(self):
        r = subprocess.run(["node", os.path.join(os.path.dirname(__file__), "worker_check.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

if __name__ == "__main__":
    unittest.main()
