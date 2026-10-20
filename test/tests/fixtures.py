"""테스트용 소형 OHLCV 데이터 생성기."""

from __future__ import annotations

import random
from datetime import date, timedelta
from typing import Any


def business_days(end: date, count: int) -> list[str]:
    days: list[str] = []
    cur = end
    while len(days) < count:
        if cur.weekday() < 5:
            days.append(cur.isoformat())
        cur -= timedelta(days=1)
    return list(reversed(days))


def make_raw(days: int = 40, stocks: int = 5, seed: int = 7) -> dict[str, Any]:
    rng = random.Random(seed)
    dates = business_days(date(2026, 10, 19), days)
    bench_rets = [rng.gauss(0.0008, 0.007) for _ in range(days)]
    bench_rets[0] = 0.0
    bench_closes = [1000.0]
    for ret in bench_rets[1:]:
        bench_closes.append(bench_closes[-1] * (1 + ret))
    bench_volumes = [1_000_000 + i * 1000 for i in range(days)]

    items = []
    names = ["알파전자", "베타화학", "감마바이오", "델타금융", "엡실론중공업", "제타소재", "에타식품"]
    for index in range(stocks):
        beta = 0.6 + 0.18 * index
        alpha = 0.0004 * (index - 2)
        idio = 0.006 + 0.001 * index
        returns = [0.0]
        for day in range(1, days):
            returns.append(beta * bench_rets[day] + alpha + rng.gauss(0, idio))
        close = 20_000.0 + index * 7_500
        closes = [close]
        for day in range(1, days):
            closes.append(closes[-1] * (1 + returns[day]))
        shares = 2_000_000 + index * 500_000
        volumes = [int(shares * (0.002 + rng.random() * 0.004)) for _ in range(days)]
        items.append(
            {
                "code": f"{index + 1:06d}",
                "name": names[index % len(names)],
                "dates": dates,
                "closes": [round(value, 2) for value in closes],
                "volumes": volumes,
                "shares": shares,
                "preferred": False,
            }
        )
    return {
        "schema": 1,
        "source": "test",
        "generated_at": "2026-10-19T16:00:00+09:00",
        "benchmark": {
            "code": "069500",
            "name": "KODEX 200",
            "dates": dates,
            "closes": [round(value, 2) for value in bench_closes],
            "volumes": bench_volumes,
        },
        "stocks": items,
        "warnings": [],
    }
