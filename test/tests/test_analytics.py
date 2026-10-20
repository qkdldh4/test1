"""analytics.py 순수 함수 테스트."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsa import analytics  # noqa: E402


class ReturnTests(unittest.TestCase):
    def test_pct_returns_basic(self) -> None:
        values = analytics.pct_returns([100, 110, 99, None, 120])
        self.assertIsNone(values[0])
        self.assertAlmostEqual(values[1], 0.10)
        self.assertAlmostEqual(values[2], -0.10)
        self.assertIsNone(values[3])
        self.assertIsNone(values[4])

    def test_pct_returns_ignores_non_positive(self) -> None:
        values = analytics.pct_returns([0, 100, 50])
        self.assertIsNone(values[1])
        self.assertAlmostEqual(values[2], -0.5)

    def test_relative_returns(self) -> None:
        result = analytics.relative_returns([0.02, 0.01, None], [0.01, 0.01, 0.03])
        self.assertAlmostEqual(result[0], 0.01)
        self.assertAlmostEqual(result[1], 0.0)
        self.assertIsNone(result[2])

    def test_relative_returns_length_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            analytics.relative_returns([0.1], [0.1, 0.2])


class ZScoreTests(unittest.TestCase):
    def test_warmup_and_shape(self) -> None:
        values = [0.01, -0.02, 0.03, 0.0, 0.01, -0.01]
        z = analytics.rolling_zscore(values, 3)
        self.assertEqual(len(z), len(values))
        self.assertEqual(z[:2], [None, None])
        for value in z[2:]:
            self.assertIsInstance(value, float)

    def test_constant_series_has_no_z(self) -> None:
        z = analytics.rolling_zscore([0.01] * 10, 4)
        self.assertTrue(all(value is None for value in z))

    def test_current_value_included(self) -> None:
        values = [1.0, 1.0, 1.0, 2.0]
        z = analytics.rolling_zscore(values, 3)
        mean = (1.0 + 1.0 + 2.0) / 3
        std = math.sqrt(((1 - mean) ** 2 + (1 - mean) ** 2 + (2 - mean) ** 2) / 3)
        self.assertAlmostEqual(z[3], (2.0 - mean) / std)

    def test_none_breaks_window(self) -> None:
        z = analytics.rolling_zscore([0.1, 0.2, None, 0.3, 0.4, 0.5], 2)
        self.assertIsNone(z[2])
        self.assertIsNone(z[3])
        self.assertIsNotNone(z[4])
        self.assertIsNotNone(z[5])

    def test_invalid_window(self) -> None:
        with self.assertRaises(ValueError):
            analytics.rolling_zscore([1, 2], 1)


class VolumeBetaTests(unittest.TestCase):
    def test_volume_ratio(self) -> None:
        values = [100, 100, 100, 200]
        ratio = analytics.rolling_volume_ratio(values, 3)
        self.assertEqual(ratio[:3], [None, None, None])
        self.assertAlmostEqual(ratio[3], 2.0)

    def test_volume_ratio_cap(self) -> None:
        values = [1, 1, 1, 1, 10_000]
        ratio = analytics.rolling_volume_ratio(values, 2)
        self.assertAlmostEqual(ratio[-1], analytics.MAX_VOLUME_RATIO)

    def test_beta_exact(self) -> None:
        bench = [0.01, -0.01, 0.02, -0.02, 0.005]
        stock = [value * 2 for value in bench]
        beta = analytics.rolling_beta(stock, bench, 5)
        self.assertAlmostEqual(beta[-1], 2.0, places=6)

    def test_beta_constant_benchmark(self) -> None:
        bench = [0.0] * 5
        beta = analytics.rolling_beta([0.01, 0.02, 0.03, 0.04, 0.05], bench, 5)
        self.assertIsNone(beta[-1])


class GroupTests(unittest.TestCase):
    def test_classify(self) -> None:
        self.assertEqual(analytics.classify(0.5, 0.5), analytics.UP)
        self.assertEqual(analytics.classify(-0.5, 0.5), analytics.DOWN)
        self.assertEqual(analytics.classify(0.49, 0.5), analytics.FLAT)
        self.assertIsNone(analytics.classify(None, 0.5))

    def test_percentile_ranks(self) -> None:
        ranks = analytics.percentile_ranks([10, 20, 30, None])
        self.assertAlmostEqual(ranks[0], 0.0)
        self.assertAlmostEqual(ranks[1], 0.5)
        self.assertAlmostEqual(ranks[2], 1.0)
        self.assertIsNone(ranks[3])

    def test_percentile_ties(self) -> None:
        ranks = analytics.percentile_ranks([5, 5, 10])
        self.assertAlmostEqual(ranks[0], 0.25)
        self.assertAlmostEqual(ranks[1], 0.25)
        self.assertAlmostEqual(ranks[2], 1.0)

    def test_first_valid_index(self) -> None:
        self.assertEqual(analytics.first_valid_index([None, None, 1.0]), 2)
        self.assertIsNone(analytics.first_valid_index([None, None]))

    def test_helpers(self) -> None:
        self.assertEqual(analytics.clamp(5, 0, 3), 3)
        self.assertEqual(analytics.safe_div(4, 0, default=1.0), 1.0)
        self.assertAlmostEqual(analytics.mean([1, None, 3]), 2.0)
        self.assertIsNone(analytics.mean([None]))
        self.assertAlmostEqual(analytics.contribution(0.1, 0.02), 0.2)
        self.assertIsNone(analytics.contribution(0.1, None))
        self.assertAlmostEqual(analytics.flow_score(-1.0, 500), -500)


if __name__ == "__main__":
    unittest.main()
