"""Dataset 계산 테스트."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsa.dataset import Dataset, load_dataset  # noqa: E402
from tests.fixtures import make_raw  # noqa: E402


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = make_raw(days=45, stocks=6)
        cls.ds = Dataset(cls.raw)

    def test_meta(self) -> None:
        meta = self.ds.meta()
        self.assertEqual(meta["stock_count"], 6)
        self.assertEqual(meta["benchmark"]["code"], "069500")
        self.assertEqual(meta["source"], "test")
        self.assertEqual(meta["trading_days"], 45)
        self.assertEqual(meta["defaults"]["window"], 20)

    def test_first_valid_day(self) -> None:
        self.assertGreaterEqual(self.ds.first_valid_day, 20)
        values = self.ds._z_arrays(20)
        self.assertEqual(len(values), 6)
        self.assertIsNone(values[0][0])
        self.assertIsNotNone(values[0][self.ds.first_valid_day])

    def test_daily_aggregates(self) -> None:
        days = self.ds.daily(20, 0.5)
        self.assertEqual(len(days), 45 - 20)
        last = days[-1]
        self.assertEqual(last["up"] + last["flat"] + last["down"], 6)
        self.assertIsNotNone(last["breadth"])
        self.assertIsNotNone(last["universe_ret"])
        self.assertGreater(last["turnover"], 0)
        self.assertTrue(last["leaders"])

    def test_snapshot_weights_and_contributions(self) -> None:
        snapshot = self.ds.snapshot(20, 0.5, self.ds.last_day)
        self.assertEqual(len(snapshot["rows"]), 6)
        weights = sum(row["weight"] for row in snapshot["rows"])
        self.assertAlmostEqual(weights, 100.0, places=2)
        contribs = sum(row["contrib"] for row in snapshot["rows"] if row["contrib"] is not None)
        self.assertAlmostEqual(contribs, snapshot["summary"]["universe_ret"], places=2)
        for row in snapshot["rows"]:
            self.assertIn(row["grp"], (None, "U", "F", "D"))
            if snapshot["i"] > 0:
                self.assertIn(row["prev_grp"], (None, "U", "F", "D"))

    def test_range_stats_scores(self) -> None:
        stats = self.ds.range_stats(20, 0.5, 25, self.ds.last_day)
        self.assertEqual(len(stats), 6)
        scores = [row["score"] for row in stats if row["score"] is not None]
        self.assertEqual(len(scores), 6)
        self.assertTrue(all(0 <= score <= 100 for score in scores))
        self.assertTrue(any(score > 90 for score in scores))
        for row in stats:
            self.assertEqual(row["days"], self.ds.last_day - 25 + 1)
            self.assertEqual(row["up"] + row["flat"] + row["down"], row["days"])

    def test_transitions_matrix_total(self) -> None:
        start, end = 21, self.ds.last_day
        payload = self.ds.transitions(20, 0.5, start, end, day_index=end)
        matrix_total = sum(sum(row) for row in payload["matrix"])
        self.assertEqual(matrix_total, 6 * (end - max(1, start) + 1))
        self.assertEqual(len(payload["matrix"]), 3)
        self.assertIn(payload["date"], self.ds.dates)

    def test_threshold_changes_groups(self) -> None:
        wide = self.ds.snapshot(20, 0.0, self.ds.last_day)["summary"]
        narrow = self.ds.snapshot(20, 3.0, self.ds.last_day)["summary"]
        self.assertGreaterEqual(wide["up"] + wide["down"], narrow["up"] + narrow["down"])
        self.assertEqual(narrow["flat"], 6)

    def test_stock_detail(self) -> None:
        detail = self.ds.stock_detail("000001", 20, 0.5, 20, self.ds.last_day)
        self.assertIsNotNone(detail)
        self.assertEqual(detail["code"], "000001")
        self.assertGreater(len(detail["series"]), 10)
        self.assertIsNotNone(detail["stats"]["score"])
        self.assertIsNone(self.ds.stock_detail("999999", 20, 0.5, 0, 1))

    def test_date_range(self) -> None:
        start, end = self.ds.date_range(None, None, lookback=10)
        self.assertEqual(end, self.ds.last_day)
        self.assertEqual(end - start + 1, 10)
        start2, end2 = self.ds.date_range(self.ds.dates[30], self.ds.dates[35])
        self.assertEqual((start2, end2), (30, 35))

    def test_load_dataset_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "latest.json"
            path.write_text(json.dumps(self.raw), encoding="utf-8")
            loaded = load_dataset(path)
            self.assertEqual(len(loaded.stocks), 6)
            self.assertEqual(loaded.source, "test")


class ValidationTests(unittest.TestCase):
    def test_validate_window(self) -> None:
        self.assertEqual(Dataset.validate_window(1), 2)
        self.assertEqual(Dataset.validate_window(999), 250)
        self.assertEqual(Dataset.validate_window(30), 30)

    def test_validate_threshold(self) -> None:
        self.assertEqual(Dataset.validate_threshold(-1), 0.0)
        self.assertEqual(Dataset.validate_threshold(99), 10.0)
        self.assertEqual(Dataset.validate_threshold("bad"), 0.5)

    def test_missing_benchmark(self) -> None:
        with self.assertRaises(ValueError):
            Dataset({"stocks": []})


if __name__ == "__main__":
    unittest.main()
