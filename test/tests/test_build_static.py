"""정적 사이트 데이터 생성 테스트."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsa import build_static  # noqa: E402
from tests.fixtures import make_raw  # noqa: E402


class BuildStaticTests(unittest.TestCase):
    def test_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "latest.json"
            data.write_text(json.dumps(make_raw(days=45, stocks=6)), encoding="utf-8")
            out = root / "web" / "data"
            result = build_static.build(data, out, days=10, window=20, threshold=0.5, lookback=10)
            self.assertGreater(result["bytes"], 0)
            meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["static"]["days"], 10)
            self.assertEqual(meta["static"]["lookback"], 10)
            self.assertEqual(meta["lookback_choices"], [10])
            overview = json.loads((out / "overview.json").read_text(encoding="utf-8"))
            self.assertEqual(len(overview["days"]), 10)
            universe_files = sorted((out / "universe").glob("*.json"))
            self.assertEqual(len(universe_files), 10)
            stock_files = sorted((out / "stock").glob("*.json"))
            self.assertEqual(len(stock_files), 6)
            payload = json.loads(universe_files[-1].read_text(encoding="utf-8"))
            self.assertEqual(len(payload["rows"]), 6)
            self.assertNotIn("events", payload["rows"][0])
            self.assertIn("prev_grp", payload["rows"][0])
            detail = json.loads((out / "stock" / "000001.json").read_text(encoding="utf-8"))
            self.assertNotIn("benchmark", detail)
            transitions = json.loads((out / "transitions.json").read_text(encoding="utf-8"))
            self.assertEqual(transitions["matrix_labels"], ["상향", "횡보", "하향"])

    def test_build_replaces_stale_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "latest.json"
            data.write_text(json.dumps(make_raw(days=45, stocks=6)), encoding="utf-8")
            out = root / "data"
            stale = out / "universe" / "1999-01-01.json"
            stale.parent.mkdir(parents=True)
            stale.write_text("{}", encoding="utf-8")
            build_static.build(data, out, days=5, window=20, threshold=0.5, lookback=5)
            self.assertFalse(stale.exists())
            self.assertEqual(len(list((out / "universe").glob("*.json"))), 5)


if __name__ == "__main__":
    unittest.main()
