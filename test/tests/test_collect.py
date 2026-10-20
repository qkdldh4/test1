"""collect.py 데모 생성/유틸 테스트 (네트워크 불필요)."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tsa import analytics, collect  # noqa: E402


def demo_args(**overrides):
    values = {
        "top": 8,
        "no_preferred": False,
        "start": None,
        "end": None,
        "fetch": False,
        "demo": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class DemoGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = collect.generate_demo(demo_args())

    def test_shape(self) -> None:
        self.assertEqual(self.payload["source"], "demo")
        self.assertEqual(len(self.payload["stocks"]), 8)
        self.assertEqual(
            len(self.payload["benchmark"]["dates"]), len(self.payload["benchmark"]["closes"])
        )
        self.assertGreaterEqual(len(self.payload["benchmark"]["dates"]), 150)
        self.assertEqual(self.payload["schema"], collect.SCHEMA_VERSION)

    def test_dates_are_weekdays(self) -> None:
        for value in self.payload["benchmark"]["dates"]:
            self.assertLess(date.fromisoformat(value).weekday(), 5)

    def test_last_close_matches_seed(self) -> None:
        from tsa.universe import load_seed_universe

        seed = {item["code"]: item for item in load_seed_universe()}
        for stock in self.payload["stocks"]:
            expected = seed[stock["code"]]["close"]
            self.assertAlmostEqual(stock["closes"][-1], expected, delta=max(1.0, expected * 0.001))

    def test_prices_and_volumes_positive(self) -> None:
        for stock in self.payload["stocks"]:
            self.assertTrue(all(value > 0 for value in stock["closes"]))
            self.assertTrue(all(value >= 0 for value in stock["volumes"]))
        self.assertTrue(all(value > 0 for value in self.payload["benchmark"]["closes"]))

    def test_deterministic(self) -> None:
        second = collect.generate_demo(demo_args())
        self.assertEqual(
            json.dumps(self.payload["stocks"], sort_keys=True),
            json.dumps(second["stocks"], sort_keys=True),
        )

    def test_preferred_excluded(self) -> None:
        payload = collect.generate_demo(demo_args(top=200, no_preferred=True))
        self.assertFalse(any(stock["preferred"] for stock in payload["stocks"]))

    def test_start_end_honoured(self) -> None:
        payload = collect.generate_demo(
            demo_args(start="2026-08-03", end="2026-09-30")
        )
        self.assertEqual(payload["benchmark"]["dates"][0], "2026-08-03")
        self.assertEqual(payload["benchmark"]["dates"][-1], "2026-09-30")


class UtilityTests(unittest.TestCase):
    def test_trading_days(self) -> None:
        days = collect.trading_days(date(2026, 10, 1), date(2026, 10, 12))
        self.assertEqual(len(days), 8)  # 주말 4일 제외
        self.assertTrue(all(day.weekday() < 5 for day in days))

    def test_backcast_roundtrip(self) -> None:
        returns = [0.0, 0.02, -0.015, 0.03, -0.01]
        closes = collect._backcast(10_000.0, returns)
        self.assertAlmostEqual(closes[-1], 10_000.0)
        recovered = analytics.pct_returns(closes)
        for expected, actual in zip(returns[1:], recovered[1:]):
            self.assertAlmostEqual(expected, actual, places=9)

    def test_preferred_detection(self) -> None:
        self.assertTrue(collect.is_preferred("삼성전자우"))
        self.assertTrue(collect.is_preferred("현대차2우B"))
        self.assertFalse(collect.is_preferred("삼성전자"))

    def test_fetch_universe_fallback(self) -> None:
        class FailingFdr:
            @staticmethod
            def StockListing(market):
                raise ConnectionError("offline")

        universe = collect.fetch_universe(FailingFdr, top=5)
        self.assertEqual(len(universe), 5)
        self.assertEqual(universe[0]["code"], "005930")
        self.assertGreater(universe[0]["marcap"], 0)

    def test_save_raw(self) -> None:
        import tempfile

        payload = collect.generate_demo(demo_args(top=2, start="2026-09-01", end="2026-09-30"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.json"
            collect.save_raw(payload, path)
            self.assertTrue(path.exists())
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(loaded["stocks"]), 2)


if __name__ == "__main__":
    unittest.main()
