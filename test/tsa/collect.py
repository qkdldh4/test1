"""OHLCV 수집기.

두 가지 모드를 제공한다.

* ``--fetch`` : FinanceDataReader(fdr)로 KODEX 200 ETF와 코스피 시총 상위
  종목의 일봉을 내려받아 ``assets/data/latest.json`` 에 저장한다.
* ``--demo``  : 네트워크가 없는 환경에서도 웹앱을 확인할 수 있도록
  실제 종목 코드/이름/시가총액에 맞춘 **합성(데모)** 시계열을 만든다.

사용 예::

    python -m tsa.collect --fetch
    python -m tsa.collect --fetch --start 2025-01-01 --top 200 --workers 2
    python -m tsa.collect --demo
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from . import config
from .universe import load_seed_universe, seed_as_of

BENCHMARK_CODE = "069500"
BENCHMARK_NAME = "KODEX 200"
SCHEMA_VERSION = 1
CACHE_VERSION = 1

ETF_NAME_PATTERN = re.compile(
    r"^(KODEX|TIGER|ARIRANG|KBSTAR|HANARO|SOL|ACE|KIM|TIMEFOLIO|RISE|PLUS|TREX|1Q|WON|FOCUS|히어로즈|ETN)"
)
PREFERRED_PATTERN = re.compile(r"(우|우B|우C|2우B|3우B|1우B)$")


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------
def _log(message: str) -> None:
    print(message, flush=True)


def _retry(fn: Callable[[], Any], tries: int = 4, base_delay: float = 1.2) -> Any:
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # 네트워크/파싱 오류는 재시도
            last = exc
            if attempt == tries:
                break
            delay = base_delay * (2 ** (attempt - 1))
            _log(f"    · 일시 오류({type(exc).__name__}: {exc}) → {delay:.1f}s 후 재시도")
            time.sleep(delay)
    raise RuntimeError(f"재시도 실패: {last}") from last


def is_preferred(name: str) -> bool:
    return bool(PREFERRED_PATTERN.search(name.strip()))


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def trading_days(start: date, end: date) -> list[date]:
    """주말을 제외한 날짜 목록(데모용, 공휴일은 고려하지 않음)."""
    days: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            days.append(cur)
        cur += timedelta(days=1)
    return days


# ---------------------------------------------------------------------------
# fdr 실데이터 수집
# ---------------------------------------------------------------------------
def _import_fdr():
    try:
        import FinanceDataReader as fdr  # type: ignore
    except ImportError as exc:  # pragma: no cover - 사용자 환경 의존
        raise SystemExit(
            "FinanceDataReader가 설치되어 있지 않습니다.\n"
            "  python -m pip install -r test/tsa/requirements.txt\n"
            "  (또는 python -m pip install finance-datareader pandas)"
        ) from exc
    return fdr


def fetch_universe(fdr, top: int, include_preferred: bool = True) -> list[dict[str, Any]]:
    """코스피 시가총액 상위 종목. 실패하면 번들 예비 목록을 사용한다."""
    try:
        listing = _retry(lambda: fdr.StockListing("KOSPI"), tries=3)
        listing = listing.copy()
        listing.columns = [str(c).strip() for c in listing.columns]
        # fdr 버전에 따라 컬럼명이 다르다.
        rename = {
            "종목코드": "Code",
            "종목명": "Name",
            "시가총액": "Marcap",
            "상장주식수": "Stocks",
            "현재가": "Close",
        }
        listing = listing.rename(columns={k: v for k, v in rename.items() if k in listing.columns})
        required = {"Code", "Name", "Marcap"}
        if not required.issubset(listing.columns):
            raise ValueError(f"예상 컬럼이 없습니다: {sorted(listing.columns)}")
        listing["Code"] = listing["Code"].astype(str).str.zfill(6)
        listing["Name"] = listing["Name"].astype(str).str.strip()
        listing["Marcap"] = _to_number(listing["Marcap"])
        listing = listing[listing["Marcap"] > 0]
        listing = listing[~listing["Name"].str.match(ETF_NAME_PATTERN)]
        listing = listing.sort_values("Marcap", ascending=False)
        rows: list[dict[str, Any]] = []
        for _, row in listing.iterrows():
            name = row["Name"]
            if not include_preferred and is_preferred(name):
                continue
            close = _to_number(row.get("Close")) or 0.0
            shares = _to_number(row.get("Stocks")) or (row["Marcap"] / close if close else 0.0)
            rows.append(
                {
                    "code": row["Code"],
                    "name": name,
                    "marcap": float(row["Marcap"]),
                    "close": close,
                    "shares": shares,
                    "preferred": is_preferred(name),
                }
            )
            if len(rows) >= top:
                break
        if len(rows) < min(top, 20):
            raise ValueError(f"유니버스가 너무 작습니다({len(rows)}개)")
        _log(f"  · KRX 상장 목록에서 {len(rows)}종목을 선별했습니다.")
        return rows
    except Exception as exc:
        _log(f"  ! fdr.StockListing 실패 → 번들 예비 유니버스 사용 ({exc})")
        seed = load_seed_universe()
        if not include_preferred:
            seed = [s for s in seed if not s.get("preferred")]
        if len(seed) < top:
            raise SystemExit(
                f"예비 유니버스가 {len(seed)}종목뿐입니다. fdr 연결을 확인하거나 --top 값을 낮추세요."
            )
        return seed[:top]


def _to_number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return 0.0 if value != value else float(value)
    text = str(value).replace(",", "").strip()
    if not text or text in {"-", "nan", "None"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _frame_series(frame, code: str, name: str) -> dict[str, Any] | None:
    """fdr DataFrame → 정렬된 날짜/종가/거래량 목록."""
    if frame is None or len(frame) == 0:
        return None
    frame = frame.copy().sort_index()
    frame.columns = [str(c).strip().title() for c in frame.columns]
    if "Close" not in frame.columns:
        return None
    frame = frame.dropna(subset=["Close"])
    frame = frame[frame["Close"] > 0]
    if len(frame) < 30:
        return None
    volumes = frame["Volume"] if "Volume" in frame.columns else None
    dates = [str(idx)[:10] for idx in frame.index]
    closes = [_round(v, 4) for v in frame["Close"].tolist()]
    vols = [_round(v, 2) if v == v else 0.0 for v in (volumes.tolist() if volumes is not None else [0.0] * len(frame))]
    return {"code": code, "name": name, "dates": dates, "closes": closes, "volumes": vols}


def _cache_path(cache_dir: Path, code: str) -> Path:
    return cache_dir / f"{code}.json"


def _read_cache(cache_dir: Path, code: str, start: str, end: str) -> dict[str, Any] | None:
    path = _cache_path(cache_dir, code)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("cache_version") != CACHE_VERSION:
        return None
    dates = payload.get("dates") or []
    if not dates or dates[0] > start or dates[-1] < end:
        return None
    return payload


def _write_cache(cache_dir: Path, payload: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(payload, cache_version=CACHE_VERSION)
    path = _cache_path(cache_dir, payload["code"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def fetch_series(
    fdr,
    code: str,
    name: str,
    start: str,
    end: str,
    cache_dir: Path,
    refresh: bool = False,
) -> dict[str, Any] | None:
    if not refresh:
        cached = _read_cache(cache_dir, code, start, end)
        if cached is not None:
            return cached
    frame = _retry(lambda: fdr.DataReader(code, start, end), tries=4)
    payload = _frame_series(frame, code, name)
    if payload is not None:
        _write_cache(cache_dir, payload)
    return payload


def collect_live(args: argparse.Namespace) -> dict[str, Any]:
    fdr = _import_fdr()
    start, end = args.start, args.end
    cache_dir = Path(args.cache_dir).resolve() if args.cache_dir else config.data_dir() / "cache"
    _log(f"■ 실데이터 수집: {start} ~ {end}")
    _log("① 코스피 시가총액 상위 종목 조회")
    universe = fetch_universe(fdr, args.top, include_preferred=not args.no_preferred)

    _log(f"② 벤치마크 {BENCHMARK_NAME}({BENCHMARK_CODE}) 일봉")
    benchmark = None
    try:
        benchmark = fetch_series(fdr, BENCHMARK_CODE, BENCHMARK_NAME, start, end, cache_dir, args.refresh)
    except Exception as exc:
        _log(f"  ! {BENCHMARK_NAME} 수집 실패: {exc}")
    if benchmark is None:
        _log("  · 코스피200 지수(KS200)로 대체합니다.")
        benchmark = fetch_series(fdr, "KS200", "코스피200 지수", start, end, cache_dir, args.refresh)
        if benchmark is None:
            raise SystemExit("벤치마크 데이터를 가져오지 못했습니다. 시작일을 조정해 보세요.")
    _log(f"  · {len(benchmark['dates'])}거래일")

    _log(f"③ 종목 일봉 수집 ({len(universe)}개, workers={args.workers})")
    stocks: list[dict[str, Any]] = []
    warnings: list[str] = []

    def work(item: dict[str, Any]) -> dict[str, Any] | None:
        try:
            series = fetch_series(
                fdr, item["code"], item["name"], start, end, cache_dir, args.refresh
            )
        except Exception as exc:
            warnings.append(f"{item['name']}({item['code']}): {exc}")
            return None
        if series is None:
            warnings.append(f"{item['name']}({item['code']}): 데이터 부족")
            return None
        series["shares"] = float(item.get("shares") or 0.0)
        series["marcap_hint"] = float(item.get("marcap") or 0.0)
        series["preferred"] = bool(item.get("preferred"))
        return series

    if args.workers <= 1:
        for idx, item in enumerate(universe, 1):
            result = work(item)
            if result:
                stocks.append(result)
            if idx % 10 == 0 or idx == len(universe):
                _log(f"    {idx}/{len(universe)} … 수집 {len(stocks)}개")
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = {pool.submit(work, item): item for item in universe}
            for idx, future in enumerate(as_completed(futures), 1):
                result = future.result()
                if result:
                    stocks.append(result)
                if idx % 10 == 0 or idx == len(universe):
                    _log(f"    {idx}/{len(universe)} … 수집 {len(stocks)}개")
        order = {item["code"]: i for i, item in enumerate(universe)}
        stocks.sort(key=lambda s: order.get(s["code"], 10**6))

    if len(stocks) < 10:
        raise SystemExit(f"수집된 종목이 {len(stocks)}개뿐입니다. 네트워크/기간을 확인하세요.")
    stocks = _fill_missing_shares(stocks, benchmark)

    return {
        "schema": SCHEMA_VERSION,
        "source": "fdr",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "requested": {
            "start": start,
            "end": end,
            "top": args.top,
            "benchmark": BENCHMARK_CODE,
            "include_preferred": not args.no_preferred,
        },
        "benchmark": benchmark,
        "stocks": stocks,
        "warnings": warnings[:50],
    }


def _fill_missing_shares(stocks: list[dict[str, Any]], benchmark: dict[str, Any]) -> None:
    for stock in stocks:
        if stock.get("shares"):
            continue
        closes = stock.get("closes") or []
        hint = stock.pop("marcap_hint", 0.0)
        if closes and hint:
            stock["shares"] = hint / closes[-1]


# ---------------------------------------------------------------------------
# 데모(합성) 데이터
# ---------------------------------------------------------------------------
THEMES: list[tuple[str, tuple[str, ...]]] = [
    ("반도체", ("삼성전자", "SK하이닉스", "SK스퀘어", "삼성전기", "LG이노텍", "한미반도체", "DB하이텍", "HPSP", "이오테크닉스", "원익")),
    ("2차전지", ("LG에너지", "삼성SDI", "LG화학", "포스코퓨처엠", "에코프로", "엘앤에프", "코스모", "후성", "OCI", "금양")),
    ("바이오", ("삼성바이오", "셀트리온", "유한양행", "한미약품", "대웅", "종근당", "SK바이오", "녹십자", "보령", "동아")),
    ("금융", ("KB금융", "신한지주", "하나금융", "우리금융", "메리츠", "기업은행", "삼성생명", "삼성화재", "DB손해", "현대해상", "한화생명", "미래에셋", "한국금융", "NH투자", "삼성증권", "카카오뱅크", "카카오페이")),
    ("자동차", ("현대차", "기아", "현대모비스", "한온시스템", "HL만도", "현대위아", "금호타이어", "한국타이어", "KG모빌리티", "현대글로비스")),
    ("방산·조선", ("한화에어로", "한국항공우주", "현대로템", "한화시스템", "HD현대중공업", "HD한국조선해양", "삼성중공업", "한화오션", "HD현대마린", "두산에너빌리티")),
    ("에너지·화학", ("SK이노베이션", "S-Oil", "한국전력", "한국가스공사", "LG화학", "롯데케미칼", "한화솔루션", "금호석유", "고려아연", "POSCO", "현대제철", "동국", "세아")),
    ("플랫폼·소비", ("NAVER", "카카오", "엔씨", "넷마블", "크래프톤", "하이브", "CJ", "오리온", "농심", "삼양", "롯데", "이마트", "신세계", "아모레", "LG생활건강", "코웨이", "KT&G", "하이트")),
]


def theme_for(name: str) -> str:
    for theme, keywords in THEMES:
        if any(k in name for k in keywords):
            return theme
    return "기타"


def generate_demo(
    args: argparse.Namespace,
    seed_universe: list[dict[str, Any]] | None = None,
    days: int = 190,
) -> dict[str, Any]:
    """실제 종목명/코드/최근 종가에 맞춘 결정론적 합성 시계열."""
    universe = list(seed_universe or load_seed_universe())
    if args.no_preferred:
        universe = [s for s in universe if not s.get("preferred")]
    universe = universe[: args.top]

    end = date.fromisoformat(args.end) if args.end else date.fromisoformat(seed_as_of() or "2026-10-19")
    # 마지막 거래일이 주말이면 직전 금요일로 이동
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    if args.start:
        dates = trading_days(date.fromisoformat(args.start), end)[-400:]
    else:
        start = end - timedelta(days=int(days * 1.45))
        dates = trading_days(start, end)[-days:]
    date_strings = [d.isoformat() for d in dates]
    n = len(dates)

    rng = random.Random(20261020)
    theme_names = [t[0] for t in THEMES] + ["기타"]
    # 테마별 모멘텀 사이클(시장 대비) — 후반부에 주도주가 교체되는 그림을 만든다.
    phases = {t: rng.uniform(0, math.tau) for t in theme_names}
    cycles = {t: rng.choice([0.7, 0.9, 1.2, 1.5]) for t in theme_names}
    amp = {t: rng.uniform(0.0010, 0.0028) for t in theme_names}
    theme_vol = {t: rng.uniform(0.004, 0.011) for t in theme_names}

    market = _simulate_market(rng, n)
    bench_last = 89000.0
    bench_closes = _backcast(bench_last, market)
    bench_volumes = [
        max(100_000.0, 2_600_000 * (1 + 18 * abs(r)) * math.exp(rng.gauss(0, 0.28)))
        for r in market
    ]

    stocks: list[dict[str, Any]] = []
    for idx, item in enumerate(universe):
        name = item["name"]
        code = item["code"]
        last_close = float(item.get("close") or 0) or 10000.0
        shares = float(item.get("shares") or 0) or (float(item.get("marcap") or 0) / last_close)
        if shares <= 0:
            shares = 1_000_000
        theme = theme_for(name)
        beta = rng.uniform(0.65, 1.45)
        loading = rng.uniform(0.5, 1.3)
        idio = rng.uniform(0.006, 0.017)
        rets: list[float] = []
        for t in range(n):
            wave = amp[theme] * cycles[theme] * math.sin(t / 17.0 + phases[theme])
            r = (
                beta * market[t]
                + loading * wave
                + rng.gauss(0, theme_vol[theme] * 0.35)
                + rng.gauss(0, idio)
            )
            rets.append(max(-0.18, min(0.18, r)))
        rets[0] = 0.0
        closes = _backcast(last_close, rets)
        turnover = 0.0006 if item.get("preferred") else rng.uniform(0.0018, 0.0065)
        base_volume = max(3_000.0, shares * turnover)
        volumes = []
        for t in range(n):
            factor = (1 + 14 * min(abs(rets[t]), 0.08)) * math.exp(rng.gauss(0, 0.35))
            if item.get("preferred"):
                factor *= 0.35
            volumes.append(round(base_volume * factor, 0))
        stocks.append(
            {
                "code": code,
                "name": name,
                "theme": theme,
                "dates": date_strings,
                "closes": [_round(c, 2) for c in closes],
                "volumes": volumes,
                "shares": round(shares, 0),
                "preferred": bool(item.get("preferred")),
            }
        )
        if (idx + 1) % 50 == 0:
            _log(f"    {idx + 1}/{len(universe)} 합성 …")

    # 실제 상장 스냅샷과 시총 순서가 크게 어긋나지 않도록 마지막 종가를 맞춘다.
    return {
        "schema": SCHEMA_VERSION,
        "source": "demo",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "requested": {"start": date_strings[0], "end": date_strings[-1], "top": len(stocks)},
        "benchmark": {
            "code": BENCHMARK_CODE,
            "name": BENCHMARK_NAME,
            "dates": date_strings,
            "closes": [_round(c, 2) for c in bench_closes],
            "volumes": bench_volumes,
        },
        "stocks": stocks,
        "warnings": ["데모(합성) 데이터입니다. 실제 시세는 --fetch 모드로 수집하세요."],
    }


def _simulate_market(rng: random.Random, n: int) -> list[float]:
    """시장 요인: 상승 → 조정 → 횡보 → 재상승 국면."""
    regime_plan = [
        (0.0011, 0.0075, int(n * 0.22)),
        (-0.0009, 0.0110, int(n * 0.16)),
        (0.0001, 0.0060, int(n * 0.24)),
        (0.0014, 0.0085, int(n * 0.20)),
        (0.0004, 0.0070, n),
    ]
    out: list[float] = []
    for mu, sigma, length in regime_plan:
        for _ in range(length):
            if len(out) >= n:
                break
            shock = rng.gauss(0, sigma)
            if rng.random() < 0.02:
                shock += rng.choice([-1, 1]) * rng.uniform(0.012, 0.026)
            out.append(max(-0.08, min(0.08, mu + shock)))
    while len(out) < n:
        out.append(rng.gauss(0.0003, 0.007))
    return out[:n]


def _backcast(last_close: float, returns: list[float]) -> list[float]:
    """마지막 종가를 기준으로 과거 가격을 역산한다."""
    n = len(returns)
    closes = [0.0] * n
    closes[-1] = last_close
    for i in range(n - 2, -1, -1):
        closes[i] = closes[i + 1] / (1.0 + returns[i + 1])
    return closes


# ---------------------------------------------------------------------------
# 저장/CLI
# ---------------------------------------------------------------------------
def save_raw(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)
    size_mb = path.stat().st_size / 1024 / 1024
    _log(f"  · 저장: {path} ({size_mb:.2f} MB)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tsa.collect",
        description="KODEX 200 + 코스피 시총 상위 종목 일봉 수집기",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fetch", action="store_true", help="fdr로 실제 시세를 수집합니다.")
    mode.add_argument("--demo", action="store_true", help="네트워크 없이 합성 데모 데이터를 생성합니다.")

    today = date.today()
    default_start = (today - timedelta(days=420)).isoformat()
    parser.add_argument("--start", default=None, help=f"시작일 YYYY-MM-DD (기본 {default_start})")
    parser.add_argument("--end", default=None, help=f"종료일 YYYY-MM-DD (기본 {today.isoformat()})")
    parser.add_argument("--top", type=int, default=config.DEFAULT_STOCK_COUNT, help="종목 수 (기본 200)")
    parser.add_argument("--no-preferred", action="store_true", help="우선주 제외")
    parser.add_argument("--out", default=None, help="저장 경로 (기본 assets/data/latest.json)")
    parser.add_argument("--cache-dir", default=None, help="종목별 원본 캐시 폴더")
    parser.add_argument("--refresh", action="store_true", help="캐시를 무시하고 다시 받습니다.")
    parser.add_argument("--workers", type=int, default=1, help="동시 요청 수 (기본 1, 최대 8)")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.fetch:
        args.start = args.start or (date.today() - timedelta(days=420)).isoformat()
        args.end = args.end or date.today().isoformat()
    if args.top < 10 or args.top > 1200:
        parser.error("--top 은 10~1200 사이여야 합니다.")
    args.workers = max(1, min(8, args.workers))
    for label in ("start", "end"):
        value = getattr(args, label)
        if value:
            try:
                datetime.fromisoformat(value)
            except ValueError:
                parser.error(f"--{label} 는 YYYY-MM-DD 형식이어야 합니다.")
    out_path = Path(args.out).resolve() if args.out else config.latest_path()
    try:
        if args.fetch:
            payload = collect_live(args)
        else:
            _log(f"■ 데모 데이터 생성 ({args.top}종목)")
            payload = generate_demo(args)
    except KeyboardInterrupt:
        _log("\n중단되었습니다.")
        return 130
    save_raw(payload, out_path)
    _log("")
    _log(f"완료: {len(payload['stocks'])}종목 × {len(payload['benchmark']['dates'])}거래일")
    if payload.get("warnings"):
        _log(f"경고 {len(payload['warnings'])}건 (자세한 내용은 저장 파일의 warnings 참고)")
    _log("다음 단계: python -m tsa.server")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
