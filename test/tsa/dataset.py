"""원본 OHLCV → 분석 데이터셋.

``assets/data/latest.json`` (collect.py 산출물)을 읽어 다음을 계산한다.

* 종목별 당일 등락률, KODEX 200 대비 초과 등락률
* 이동 표준편차로 정규화한 상대강도 z (기본 20거래일)
* z 임계값 기반 상향/횡보/하향 그룹
* 시총 비중 · 거래대금 기반 지수 영향력과 영향력 점수
* 그룹 전환(상향→하향 등) 이력과 전환 행렬

모든 계산은 표준 라이브러리만 사용한다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import analytics, config

EPS = 1e-12
GROUP_LETTERS = "UFD"


def _r(value: float | None, digits: int = 4) -> float | None:
    return None if value is None else round(float(value), digits)


def _pct(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value) * 100.0, digits)


def group_key(group: int | None) -> str | None:
    return None if group is None else GROUP_LETTERS[group]


@dataclass
class Stock:
    code: str
    name: str
    preferred: bool
    shares: float
    closes: list[float | None]
    volumes: list[float | None]
    returns: list[float | None] = field(default_factory=list)
    relatives: list[float | None] = field(default_factory=list)
    volume_ratios: list[float | None] = field(default_factory=list)
    values: list[float | None] = field(default_factory=list)
    mcaps: list[float | None] = field(default_factory=list)

    @property
    def last_close(self) -> float | None:
        for value in reversed(self.closes):
            if value is not None:
                return value
        return None


class Dataset:
    """분석용 데이터셋. 한 번 로드한 뒤 여러 파라미터로 조회한다."""

    def __init__(self, raw: dict[str, Any], path: Path | None = None) -> None:
        self.raw = raw
        self.path = path
        self.source = str(raw.get("source") or "unknown")
        self.generated_at = str(raw.get("generated_at") or "")
        self.warnings = list(raw.get("warnings") or [])
        benchmark = raw.get("benchmark") or {}
        self.benchmark_code = str(benchmark.get("code") or "")
        self.benchmark_name = str(benchmark.get("name") or config.BENCHMARK_NAME)
        self.dates: list[str] = [str(d)[:10] for d in benchmark.get("dates") or []]
        if not self.dates:
            raise ValueError("벤치마크 날짜가 없습니다. collect.py를 먼저 실행하세요.")
        self._date_index = {d: i for i, d in enumerate(self.dates)}

        bench_close_map = {
            str(d)[:10]: float(v)
            for d, v in zip(benchmark.get("dates") or [], benchmark.get("closes") or [])
            if v is not None and float(v) > 0
        }
        self.bench_closes: list[float | None] = [bench_close_map.get(d) for d in self.dates]
        self.bench_returns = analytics.pct_returns(self.bench_closes)
        if sum(1 for v in self.bench_closes if v) < 2:
            raise ValueError("벤치마크 종가가 부족합니다.")

        self.stocks: list[Stock] = []
        for item in raw.get("stocks") or []:
            stock = self._build_stock(item)
            if stock is not None:
                self.stocks.append(stock)
        if not self.stocks:
            raise ValueError("종목 데이터가 없습니다.")

        self._z_cache: dict[int, list[list[float | None]]] = {}
        self._beta_cache: dict[int, list[list[float | None]]] = {}
        self._group_cache: dict[tuple[int, float], list[list[int | None]]] = {}
        self._daily_cache: dict[tuple[int, float], list[dict[str, Any]]] = {}
        self._stock_index = {s.code: i for i, s in enumerate(self.stocks)}
        self._cap_totals: list[float] | None = None

        first_candidates = [
            analytics.first_valid_index(zs) for zs in self._z_arrays(config.DEFAULT_WINDOW)
        ]
        valid = [i for i in first_candidates if i is not None]
        self.first_valid_day = min(valid) if valid else 0
        self.last_day = len(self.dates) - 1

    # -- 구성 ---------------------------------------------------------
    def _build_stock(self, item: dict[str, Any]) -> Stock | None:
        code = str(item.get("code") or "").zfill(6)
        name = str(item.get("name") or code).strip()
        if not code or name == "None":
            return None
        closes_map = {
            str(d)[:10]: float(v)
            for d, v in zip(item.get("dates") or [], item.get("closes") or [])
            if v is not None and float(v) > 0
        }
        if not closes_map:
            return None
        volumes_map = {
            str(d)[:10]: float(v)
            for d, v in zip(item.get("dates") or [], item.get("volumes") or [])
            if v is not None and float(v) >= 0
        }
        shares = float(item.get("shares") or 0.0)
        closes = [closes_map.get(d) for d in self.dates]
        if shares <= 0:
            hint = float(item.get("marcap_hint") or 0.0)
            last = next((v for v in reversed(closes) if v), None)
            if hint and last:
                shares = hint / last
        volumes = [volumes_map.get(d) for d in self.dates]
        stock = Stock(
            code=code,
            name=name,
            preferred=bool(item.get("preferred")),
            shares=shares,
            closes=closes,
            volumes=volumes,
        )
        stock.returns = analytics.pct_returns(closes)
        stock.relatives = analytics.relative_returns(stock.returns, self.bench_returns)
        stock.volume_ratios = analytics.rolling_volume_ratio(volumes)
        stock.values = [
            (c * v if c is not None and v is not None else None) for c, v in zip(closes, volumes)
        ]
        stock.mcaps = [(c * shares if c is not None and shares > 0 else None) for c in closes]
        return stock

    # -- 파라미터 -----------------------------------------------------
    @staticmethod
    def validate_window(window: int) -> int:
        return max(2, min(int(window), 250))

    @staticmethod
    def validate_threshold(threshold: float) -> float:
        try:
            value = float(threshold)
        except (TypeError, ValueError):
            return config.DEFAULT_THRESHOLD
        return max(0.0, min(value, 10.0))

    def date_range(
        self, start: str | None, end: str | None, lookback: int | None = None
    ) -> tuple[int, int]:
        end_i = self.last_day if not end else self._date_index.get(str(end)[:10], self.last_day)
        end_i = max(0, min(end_i, self.last_day))
        if start:
            start_i = self._date_index.get(str(start)[:10], self.first_valid_day)
        elif lookback:
            start_i = max(self.first_valid_day, end_i - int(lookback) + 1)
        else:
            start_i = self.first_valid_day
        start_i = max(self.first_valid_day, min(start_i, end_i))
        return start_i, end_i

    def day_index(self, day: str | None) -> int:
        if not day:
            return self.last_day
        return self._date_index.get(str(day)[:10], self.last_day)

    # -- 롤링 지표 ----------------------------------------------------
    def _z_arrays(self, window: int) -> list[list[float | None]]:
        window = self.validate_window(window)
        if window not in self._z_cache:
            self._z_cache[window] = [
                analytics.rolling_zscore(stock.relatives, window) for stock in self.stocks
            ]
        return self._z_cache[window]

    def _beta_arrays(self, window: int) -> list[list[float | None]]:
        window = self.validate_window(window)
        if window not in self._beta_cache:
            self._beta_cache[window] = [
                analytics.rolling_beta(stock.returns, self.bench_returns, window)
                for stock in self.stocks
            ]
        return self._beta_cache[window]

    def _group_arrays(self, window: int, threshold: float) -> list[list[int | None]]:
        key = (self.validate_window(window), self.validate_threshold(threshold))
        if key not in self._group_cache:
            mapping = {None: None, analytics.UP: 0, analytics.FLAT: 1, analytics.DOWN: 2}
            self._group_cache[key] = [
                [mapping[analytics.classify(z, key[1])] for z in zs] for zs in self._z_arrays(key[0])
            ]
        return self._group_cache[key]

    def cap_totals(self) -> list[float]:
        if self._cap_totals is None:
            self._cap_totals = [
                sum(stock.mcaps[i] or 0.0 for stock in self.stocks)
                for i in range(len(self.dates))
            ]
        return self._cap_totals

    # -- 일별 집계 ----------------------------------------------------
    def daily(self, window: int, threshold: float) -> list[dict[str, Any]]:
        window = self.validate_window(window)
        threshold = self.validate_threshold(threshold)
        key = (window, threshold)
        if key in self._daily_cache:
            return self._daily_cache[key]
        zs = self._z_arrays(window)
        groups = self._group_arrays(window, threshold)
        caps = self.cap_totals()
        days: list[dict[str, Any]] = []
        active = [s for s in range(len(self.stocks))]
        for i in range(len(self.dates)):
            valid = [s for s in active if zs[s][i] is not None]
            if not valid:
                continue
            counts = [0, 0, 0]
            z_sum = 0.0
            up_returns = 0
            return_count = 0
            cap_total = caps[i]
            cap_return = 0.0
            flow_pos = 0.0
            flow_neg = 0.0
            contributions: list[tuple[float, int]] = []
            turnover = 0.0
            for s in valid:
                stock = self.stocks[s]
                z = zs[s][i]
                g = groups[s][i]
                if g is not None:
                    counts[g] += 1
                z_sum += z or 0.0
                ret = stock.returns[i]
                if ret is not None:
                    return_count += 1
                    if ret > 0:
                        up_returns += 1
                value = stock.values[i]
                if value is not None and value > 0:
                    turnover += value
                    if z is not None and z >= 0:
                        flow_pos += value
                    else:
                        flow_neg += value
                mcap = stock.mcaps[i]
                if mcap and cap_total > 0 and ret is not None:
                    weight = mcap / cap_total
                    cap_return += weight * ret
                    contributions.append((weight * ret * 100.0, s))
            contributions.sort(key=lambda pair: abs(pair[0]), reverse=True)
            total_abs = sum(abs(c) for c, _ in contributions)
            top5 = sum(abs(c) for c, _ in contributions[:5])
            trans = {f"{a}>{b}": 0 for a in GROUP_LETTERS for b in GROUP_LETTERS}
            upgrades = downgrades = 0
            if i > 0:
                for s in valid:
                    cur = groups[s][i]
                    prev = groups[s][i - 1]
                    if cur is None or prev is None:
                        continue
                    trans[f"{GROUP_LETTERS[prev]}>{GROUP_LETTERS[cur]}"] += 1
                    if cur < prev:
                        upgrades += 1
                    elif cur > prev:
                        downgrades += 1
            leaders = []
            for contrib, s in contributions[:5]:
                stock = self.stocks[s]
                leaders.append(
                    {
                        "code": stock.code,
                        "name": stock.name,
                        "contrib": _r(contrib, 3),
                        "z": _r(zs[s][i], 2),
                        "grp": group_key(groups[s][i]),
                    }
                )
            days.append(
                {
                    "i": i,
                    "date": self.dates[i],
                    "bench_ret": _pct(self.bench_returns[i], 3),
                    "bench_close": _r(self.bench_closes[i], 2),
                    "up": counts[0],
                    "flat": counts[1],
                    "down": counts[2],
                    "net": counts[0] - counts[2],
                    "breadth": round(100.0 * up_returns / return_count, 2) if return_count else None,
                    "sum_z": _r(z_sum, 2),
                    "avg_z": _r(z_sum / len(valid), 3),
                    "universe_ret": _r(cap_return * 100.0, 3),
                    "top5_share": round(100.0 * top5 / total_abs, 2) if total_abs > EPS else None,
                    "inflow": round(100.0 * flow_pos / (flow_pos + flow_neg), 2)
                    if (flow_pos + flow_neg) > 0
                    else None,
                    "turnover": _r(turnover / 1e8, 0),
                    "transitions": trans,
                    "upgrades": upgrades,
                    "downgrades": downgrades,
                    "leaders": leaders,
                }
            )
        self._daily_cache[key] = days
        return days

    # -- 스냅샷 -------------------------------------------------------
    def snapshot(self, window: int, threshold: float, day_index: int) -> dict[str, Any]:
        window = self.validate_window(window)
        threshold = self.validate_threshold(threshold)
        day_index = max(0, min(int(day_index), self.last_day))
        zs = self._z_arrays(window)
        betas = self._beta_arrays(window)
        groups = self._group_arrays(window, threshold)
        cap_total = self.cap_totals()[day_index]
        rows: list[dict[str, Any]] = []
        for s, stock in enumerate(self.stocks):
            price = stock.closes[day_index]
            if price is None:
                continue
            mcap = stock.mcaps[day_index]
            value = stock.values[day_index]
            weight = (mcap / cap_total) if (mcap and cap_total > 0) else None
            ret = stock.returns[day_index]
            contrib = weight * ret * 100.0 if (weight is not None and ret is not None) else None
            rows.append(
                {
                    "code": stock.code,
                    "name": stock.name,
                    "preferred": stock.preferred,
                    "close": _r(price, 2),
                    "ret": _pct(ret, 2),
                    "rel": _pct(stock.relatives[day_index], 2),
                    "z": _r(zs[s][day_index], 2),
                    "grp": group_key(groups[s][day_index]),
                    "prev_grp": group_key(groups[s][day_index - 1]) if day_index > 0 else None,
                    "vr": _r(stock.volume_ratios[day_index], 2),
                    "mcap": _r((mcap or 0) / 1e12, 3),
                    "weight": _pct(weight, 3),
                    "contrib": _r(contrib, 3),
                    "value": _r((value or 0) / 1e8, 0),
                    "beta": _r(betas[s][day_index], 2),
                }
            )
        day = next((d for d in self.daily(window, threshold) if d["i"] == day_index), None)
        return {"date": self.dates[day_index], "i": day_index, "summary": day, "rows": rows}

    # -- 기간 통계 ----------------------------------------------------
    def range_stats(
        self, window: int, threshold: float, start_i: int, end_i: int
    ) -> list[dict[str, Any]]:
        window = self.validate_window(window)
        threshold = self.validate_threshold(threshold)
        start_i, end_i = max(0, start_i), min(end_i, self.last_day)
        zs = self._z_arrays(window)
        groups = self._group_arrays(window, threshold)
        betas = self._beta_arrays(window)
        caps = self.cap_totals()
        cap_end = caps[end_i] or 0.0
        stats: list[dict[str, Any]] = []
        for s, stock in enumerate(self.stocks):
            idx = [i for i in range(start_i, end_i + 1) if groups[s][i] is not None]
            if not idx:
                continue
            counts = [0, 0, 0]
            abs_z: list[float] = []
            vr_values: list[float] = []
            abs_contribs: list[float] = []
            contribs: list[float] = []
            value_sum = 0.0
            trans_counts: dict[str, int] = {}
            trans_events: list[dict[str, Any]] = []
            prev = None
            for i in idx:
                g = groups[s][i]
                counts[g] += 1  # type: ignore[index]
                value = zs[s][i]
                if value is not None:
                    abs_z.append(abs(value))
                vr = stock.volume_ratios[i]
                if vr is not None:
                    vr_values.append(vr)
                mcap = stock.mcaps[i]
                ret = stock.returns[i]
                if mcap and ret is not None and caps[i] > 0:
                    contrib = (mcap / caps[i]) * ret * 100.0
                    contribs.append(contrib)
                    abs_contribs.append(abs(contrib))
                if stock.values[i] is not None:
                    value_sum += stock.values[i] or 0.0
                if prev is not None and g != prev:
                    key = f"{GROUP_LETTERS[prev]}>{GROUP_LETTERS[g]}"
                    trans_counts[key] = trans_counts.get(key, 0) + 1
                    trans_events.append(
                        {"date": self.dates[i], "from": GROUP_LETTERS[prev], "to": GROUP_LETTERS[g]}
                    )
                prev = g
            cur = groups[s][end_i]
            streak = 0
            if cur is not None:
                for i in range(end_i, start_i - 1, -1):
                    if groups[s][i] != cur:
                        break
                    streak += 1
            mcap_end = stock.mcaps[end_i]
            stats.append(
                {
                    "code": stock.code,
                    "name": stock.name,
                    "preferred": stock.preferred,
                    "days": len(idx),
                    "up": counts[0],
                    "flat": counts[1],
                    "down": counts[2],
                    "up_share": round(100.0 * counts[0] / len(idx), 1),
                    "down_share": round(100.0 * counts[2] / len(idx), 1),
                    "avg_abs_z": round(sum(abs_z) / len(abs_z), 2) if abs_z else None,
                    "avg_vr": round(sum(vr_values) / len(vr_values), 2) if vr_values else None,
                    "avg_contrib": round(sum(contribs) / len(contribs), 4) if contribs else None,
                    "abs_contrib": round(sum(abs_contribs) / len(abs_contribs), 4)
                    if abs_contribs
                    else None,
                    "cum_contrib": round(sum(contribs), 3) if contribs else None,
                    "weight": round((mcap_end / cap_end) * 100.0, 3) if (mcap_end and cap_end) else 0.0,
                    "mcap": round((mcap_end or 0) / 1e12, 3),
                    "value": round(value_sum / max(len(idx), 1) / 1e8, 0),
                    "beta": _r(betas[s][end_i], 2),
                    "changes": sum(trans_counts.values()),
                    "transitions": trans_counts,
                    "events": trans_events[-8:],
                    "last_group": group_key(groups[s][end_i]),
                    "streak": streak,
                    "start_group": group_key(groups[s][idx[0]]),
                }
            )
        self._score(stats)
        return stats

    @staticmethod
    def _score(stats: list[dict[str, Any]]) -> None:
        """영향력 점수 = |기여도|·거래대금·시총 백분위 가중합(0~100)."""
        if not stats:
            return
        p_contrib = analytics.percentile_ranks([row.get("abs_contrib") for row in stats])
        p_value = analytics.percentile_ranks([row.get("value") for row in stats])
        p_mcap = analytics.percentile_ranks([row.get("mcap") for row in stats])
        for row, a, b, c in zip(stats, p_contrib, p_value, p_mcap):
            if a is None or b is None or c is None:
                row["score"] = None
                row["score_parts"] = None
                continue
            row["score"] = round(100.0 * (0.5 * a + 0.3 * b + 0.2 * c), 1)
            row["score_parts"] = {
                "contrib": round(a * 100, 1),
                "turnover": round(b * 100, 1),
                "mcap": round(c * 100, 1),
            }

    # -- 전환 분석 ----------------------------------------------------
    def transitions(
        self,
        window: int,
        threshold: float,
        start_i: int,
        end_i: int,
        day_index: int | None = None,
    ) -> dict[str, Any]:
        window = self.validate_window(window)
        threshold = self.validate_threshold(threshold)
        start_i, end_i = max(0, start_i), min(end_i, self.last_day)
        groups = self._group_arrays(window, threshold)
        zs = self._z_arrays(window)
        matrix = [[0, 0, 0] for _ in range(3)]
        events_by_day: dict[str, dict[str, int]] = {}
        for s in range(len(self.stocks)):
            for i in range(max(1, start_i), end_i + 1):
                cur, prev = groups[s][i], groups[s][i - 1]
                if cur is None or prev is None:
                    continue
                matrix[prev][cur] += 1
                if cur != prev:
                    key = f"{GROUP_LETTERS[prev]}>{GROUP_LETTERS[cur]}"
                    bucket = events_by_day.setdefault(self.dates[i], {})
                    bucket[key] = bucket.get(key, 0) + 1
        target = self.last_day if day_index is None else max(0, min(day_index, self.last_day))
        changes: list[dict[str, Any]] = []
        if target > 0:
            for s, stock in enumerate(self.stocks):
                cur, prev = groups[s][target], groups[s][target - 1]
                if cur is None or prev is None or cur == prev:
                    continue
                changes.append(
                    {
                        "code": stock.code,
                        "name": stock.name,
                        "from": GROUP_LETTERS[prev],
                        "to": GROUP_LETTERS[cur],
                        "z": _r(zs[s][target], 2),
                        "change": _pct(stock.relatives[target], 2),
                        "ret": _pct(stock.returns[target], 2),
                        "vr": _r(stock.volume_ratios[target], 2),
                        "mcap": _r((stock.mcaps[target] or 0) / 1e12, 2),
                        "upgrade": cur < prev,
                    }
                )
        changes.sort(key=lambda row: abs(row["z"] or 0), reverse=True)
        return {
            "date": self.dates[target],
            "matrix": matrix,
            "matrix_labels": [analytics.UP, analytics.FLAT, analytics.DOWN],
            "changes": changes,
            "daily": [
                {"date": date, "counts": counts}
                for date, counts in sorted(events_by_day.items())
            ],
        }

    # -- 종목 상세 ----------------------------------------------------
    def stock_detail(
        self,
        code: str,
        window: int,
        threshold: float,
        start_i: int,
        end_i: int,
    ) -> dict[str, Any] | None:
        s = self._stock_index.get(str(code).zfill(6))
        if s is None:
            return None
        window = self.validate_window(window)
        threshold = self.validate_threshold(threshold)
        start_i, end_i = max(0, start_i), min(end_i, self.last_day)
        stock = self.stocks[s]
        zs = self._z_arrays(window)
        groups = self._group_arrays(window, threshold)
        betas = self._beta_arrays(window)
        caps = self.cap_totals()
        series = []
        for i in range(start_i, end_i + 1):
            if stock.closes[i] is None:
                continue
            mcap = stock.mcaps[i]
            ret = stock.returns[i]
            weight = (mcap / caps[i]) if (mcap and caps[i] > 0) else None
            series.append(
                {
                    "date": self.dates[i],
                    "close": _r(stock.closes[i], 2),
                    "ret": _pct(ret, 2),
                    "z": _r(zs[s][i], 2),
                    "grp": group_key(groups[s][i]),
                    "vr": _r(stock.volume_ratios[i], 2),
                    "contrib": _r(
                        weight * ret * 100.0 if (weight is not None and ret is not None) else None,
                        3,
                    ),
                    "beta": _r(betas[s][i], 2),
                    "value": _r((stock.values[i] or 0) / 1e8, 0),
                }
            )
        stats = self.range_stats(window, threshold, start_i, end_i)
        stat = next((row for row in stats if row["code"] == stock.code), None)
        return {
            "code": stock.code,
            "name": stock.name,
            "preferred": stock.preferred,
            "shares": round(stock.shares, 0),
            "series": series,
            "stats": stat,
            "benchmark": {
                "code": self.benchmark_code,
                "name": self.benchmark_name,
                "returns": [_pct(self.bench_returns[i], 2) for i in range(start_i, end_i + 1)],
                "closes": [_r(self.bench_closes[i], 2) for i in range(start_i, end_i + 1)],
                "dates": self.dates[start_i:end_i + 1],
            },
        }

    # -- 메타 ---------------------------------------------------------
    def meta(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_label": "데모(합성) 데이터" if self.source == "demo" else "fdr 실데이터",
            "generated_at": self.generated_at,
            "benchmark": {"code": self.benchmark_code, "name": self.benchmark_name},
            "stock_count": len(self.stocks),
            "preferred_count": sum(1 for s in self.stocks if s.preferred),
            "date_start": self.dates[0],
            "date_end": self.dates[-1],
            "trading_days": len(self.dates),
            "first_valid_date": self.dates[self.first_valid_day] if self.dates else None,
            "defaults": {
                "window": config.DEFAULT_WINDOW,
                "threshold": config.DEFAULT_THRESHOLD,
                "lookback": config.DEFAULT_LOOKBACK,
            },
            "warnings": self.warnings,
        }


def load_raw(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_dataset(path: Path) -> Dataset:
    return Dataset(load_raw(path), path=path)


def age_hours(generated_at: str) -> float | None:
    try:
        stamp = datetime.fromisoformat(generated_at)
    except (TypeError, ValueError):
        return None
    now = datetime.now().astimezone()
    return max(0.0, (now - stamp).total_seconds() / 3600.0)
