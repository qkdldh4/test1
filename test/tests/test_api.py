"""HTTP API 통합 테스트."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsa import config  # noqa: E402
from tsa.server import Handler, State  # noqa: E402
from tests.fixtures import make_raw  # noqa: E402


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data_path = Path(cls.tmp.name) / "latest.json"
        cls.data_path.write_text(json.dumps(make_raw(days=45, stocks=6)), encoding="utf-8")
        state = State(cls.data_path)
        handler = type(
            "TestHandler", (Handler,), {"state": state, "web_dir": config.WEB_DIR}
        )
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.tmp.cleanup()

    def fetch(self, path: str) -> tuple[int, bytes, dict[str, str]]:
        request = urllib.request.Request(self.base + path)
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, response.read(), dict(response.headers)

    def get_json(self, path: str) -> dict:
        status, body, headers = self.fetch(path)
        self.assertEqual(status, 200)
        self.assertIn("application/json", headers.get("Content-Type", ""))
        return json.loads(body)

    def test_health(self) -> None:
        payload = self.get_json("/api/health")
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["stocks"], 6)
        self.assertEqual(payload["source"], "test")

    def test_meta(self) -> None:
        payload = self.get_json("/api/meta")
        self.assertEqual(payload["stock_count"], 6)
        self.assertEqual(payload["benchmark"]["name"], "KODEX 200")
        self.assertIn("lookback_choices", payload)

    def test_overview(self) -> None:
        payload = self.get_json("/api/overview?window=20&threshold=0.5&lookback=10")
        self.assertEqual(len(payload["days"]), 10)
        self.assertEqual(payload["latest"]["date"], payload["end"])
        self.assertEqual(
            payload["latest"]["up"] + payload["latest"]["flat"] + payload["latest"]["down"], 6
        )
        self.assertTrue(payload["contributors"])
        self.assertEqual(payload["window"], 20)

    def test_overview_bad_params(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.fetch("/api/overview?window=abc")
        self.assertEqual(ctx.exception.code, 400)

    def test_universe(self) -> None:
        payload = self.get_json("/api/universe?window=20&lookback=10")
        self.assertEqual(len(payload["rows"]), 6)
        self.assertEqual(payload["counts"]["all"], 6)
        self.assertIn("score", payload["rows"][0])
        self.assertIn("prev_grp", payload["rows"][0])

    def test_universe_with_date(self) -> None:
        meta = self.get_json("/api/meta")
        target = "2026-10-14"
        payload = self.get_json(f"/api/universe?window=20&lookback=10&date={target}")
        self.assertEqual(payload["date"], target)
        self.assertLess(payload["end"], meta["date_end"])

    def test_transitions(self) -> None:
        payload = self.get_json("/api/transitions?window=20&lookback=20")
        self.assertEqual(len(payload["matrix"]), 3)
        self.assertEqual(payload["matrix_labels"], ["상향", "횡보", "하향"])
        self.assertIn("daily", payload)
        self.assertIn("leaders", payload)

    def test_stock(self) -> None:
        payload = self.get_json("/api/stock/000001?window=20&lookback=10")
        self.assertEqual(payload["code"], "000001")
        self.assertGreater(len(payload["series"]), 5)
        self.assertIsNotNone(payload["stats"])

    def test_stock_not_found(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.fetch("/api/stock/999999?window=20")
        self.assertEqual(ctx.exception.code, 400)

    def test_csv_export(self) -> None:
        status, body, headers = self.fetch("/api/export.csv?window=20&lookback=10")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", headers.get("Content-Type", ""))
        self.assertIn("attachment", headers.get("Content-Disposition", ""))
        text = body.decode("utf-8-sig")
        self.assertTrue(text.startswith("code,name,close"))
        self.assertEqual(len(text.strip().splitlines()), 7)

    def test_unknown_api(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.fetch("/api/nope")
        self.assertEqual(ctx.exception.code, 404)

    def test_static_index_served(self) -> None:
        status, body, headers = self.fetch("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(b"KOSPI", body)

    def test_path_traversal_blocked(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.fetch("/..%2Fserver.py")
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
