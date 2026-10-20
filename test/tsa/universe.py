"""번들 예비 유니버스(코스피 시가총액 상위 200종목).

``assets/data/universe_seed.json`` 은 2026-10-19 KRX 상장종목 스냅샷에서
시가총액 순으로 뽑은 목록이다. fdr.StockListing('KOSPI')가 실패하거나
데모 데이터를 만들 때 사용한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from . import config

SEED_FILE = config.DATA_DIR / "universe_seed.json"


@lru_cache(maxsize=1)
def load_seed_document() -> dict[str, Any]:
    if not SEED_FILE.exists():
        return {"as_of": None, "stocks": []}
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))


def seed_as_of() -> str | None:
    return load_seed_document().get("as_of")


def load_seed_universe() -> list[dict[str, Any]]:
    stocks = load_seed_document().get("stocks", [])
    return [dict(item) for item in stocks]
