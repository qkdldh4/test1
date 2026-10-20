"""GitHub Pages용 정적 데이터 생성기.

서버 없이도 대시보드가 동작하도록 기본 파라미터(20일 창, ±0.5σ)로
최근 N거래일의 결과를 미리 계산해 ``web/data`` 에 저장한다.

    python -m tsa.build_static
    python -m tsa.build_static --days 90 --out ../docs
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config
from .dataset import Dataset, load_dataset


def _write(path: Path, payload: Any) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def _universe_rows(
    ds: Dataset, window: int, threshold: float, day_i: int, lookback: int
) -> dict[str, Any]:
    start_i = max(ds.first_valid_day, day_i - lookback + 1)
    snapshot = ds.snapshot(window, threshold, day_i)
    stats = {
        row["code"]: row
        for row in ds.range_stats(window, threshold, start_i, day_i)
    }
    rows = []
    for row in snapshot["rows"]:
        stat = stats.get(row["code"], {})
        rows.append(
            {
                **row,
                "score": stat.get("score"),
                "score_parts": stat.get("score_parts"),
                "streak": stat.get("streak"),
                "changes": stat.get("changes"),
                "up_share": stat.get("up_share"),
                "down_share": stat.get("down_share"),
                "avg_abs_z": stat.get("avg_abs_z"),
                "cum_contrib": stat.get("cum_contrib"),
            }
        )
    return {
        "date": snapshot["date"],
        "start": ds.dates[start_i],
        "end": ds.dates[day_i],
        "window": window,
        "threshold": threshold,
        "summary": snapshot["summary"],
        "rows": rows,
        "counts": {
            "all": len(rows),
            "up": sum(1 for r in rows if r["grp"] == "U"),
            "flat": sum(1 for r in rows if r["grp"] == "F"),
            "down": sum(1 for r in rows if r["grp"] == "D"),
        },
    }


def build(
    data_path: Path,
    out_dir: Path,
    days: int,
    window: int,
    threshold: float,
    lookback: int,
) -> dict[str, Any]:
    ds = load_dataset(data_path)
    end_i = ds.last_day
    start_i = max(ds.first_valid_day, end_i - days + 1)
    if start_i >= end_i:
        raise SystemExit("거래일이 부족합니다. 더 긴 기간으로 수집하세요.")

    out_dir = out_dir.resolve()
    if out_dir.exists():
        for child in ("universe", "stock"):
            shutil.rmtree(out_dir / child, ignore_errors=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.time()
    print(f"■ 정적 사이트 데이터 생성: {ds.dates[start_i]} ~ {ds.dates[end_i]} "
          f"({end_i - start_i + 1}거래일, 창 {window}, 밴드 ±{threshold}σ)")

    daily = [d for d in ds.daily(window, threshold) if start_i <= d["i"] <= end_i]
    if not daily:
        raise SystemExit("계산 가능한 날짜가 없습니다.")

    meta = ds.meta()
    meta["static"] = {
        "days": len(daily),
        "window": window,
        "threshold": threshold,
        "lookback": lookback,
        "built_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    meta["defaults"] = {"window": window, "threshold": threshold, "lookback": lookback}
    meta["lookback_choices"] = [lookback]
    size_total = _write(out_dir / "meta.json", meta)

    overview = {
        "meta": {k: v for k, v in meta.items() if k not in {"static", "lookback_choices", "warnings"}},
        "window": window,
        "threshold": threshold,
        "start": ds.dates[start_i],
        "end": ds.dates[end_i],
        "dates": [d["date"] for d in daily],
        "days": daily,
        "latest": daily[-1],
        "previous": daily[-2] if len(daily) > 1 else None,
        "totals": {
            "days": len(daily),
            "avg_up": round(sum(d["up"] for d in daily) / len(daily), 1),
            "avg_down": round(sum(d["down"] for d in daily) / len(daily), 1),
            "avg_net": round(sum((d["net"] or 0) for d in daily) / len(daily), 1),
        },
    }
    size_total += _write(out_dir / "overview.json", overview)

    transitions = ds.transitions(window, threshold, start_i, end_i, day_index=end_i)
    stats = ds.range_stats(window, threshold, start_i, end_i)
    transitions["leaders"] = sorted(
        (row for row in stats if row.get("changes")),
        key=lambda row: (row.get("changes") or 0, row.get("score") or 0),
        reverse=True,
    )[:25]
    transitions["window"] = window
    transitions["threshold"] = threshold
    transitions["start"] = ds.dates[start_i]
    transitions["end"] = ds.dates[end_i]
    size_total += _write(out_dir / "transitions.json", transitions)

    print(f"  · 기준일별 유니버스 {len(daily)}개 생성 …")
    for count, day in enumerate(daily, 1):
        payload = _universe_rows(ds, window, threshold, day["i"], lookback)
        size_total += _write(out_dir / "universe" / f"{day['date']}.json", payload)
        if count % 20 == 0 or count == len(daily):
            print(f"    {count}/{len(daily)}")

    print(f"  · 종목 상세 {len(ds.stocks)}개 생성 …")
    shared_stats = {row["code"]: row for row in stats}
    for count, stock in enumerate(ds.stocks, 1):
        detail = ds.stock_detail(stock.code, window, threshold, start_i, end_i)
        if detail is None:
            continue
        detail["window"] = window
        detail["threshold"] = threshold
        detail["start"] = ds.dates[start_i]
        detail["end"] = ds.dates[end_i]
        detail["stats"] = shared_stats.get(stock.code) or detail.get("stats")
        detail.pop("benchmark", None)
        size_total += _write(out_dir / "stock" / f"{stock.code}.json", detail)
        if count % 50 == 0 or count == len(ds.stocks):
            print(f"    {count}/{len(ds.stocks)}")

    elapsed = time.time() - started
    print(f"  · 완료: {out_dir} ({size_total / 1024 / 1024:.2f} MB, {elapsed:.1f}s)")
    return {"out_dir": str(out_dir), "bytes": size_total, "days": len(daily)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tsa.build_static",
        description="GitHub Pages용 정적 데이터(web/data) 생성",
    )
    parser.add_argument("--data", default=None, help="latest.json 경로")
    parser.add_argument("--out", default=None, help="출력 폴더 (기본 web/data)")
    parser.add_argument("--days", type=int, default=60, help="정적 페이지에 담을 거래일 수 (기본 60)")
    parser.add_argument("--window", type=int, default=config.DEFAULT_WINDOW, help="정규화 창")
    parser.add_argument("--threshold", type=float, default=config.DEFAULT_THRESHOLD, help="횡보 밴드(σ)")
    parser.add_argument("--lookback", type=int, default=60, help="종목 통계 기간(기본 60)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_path = Path(args.data).resolve() if args.data else config.latest_path()
    out_dir = Path(args.out).resolve() if args.out else config.WEB_DIR / "data"
    if not data_path.exists():
        print(f"데이터가 없습니다: {data_path}", file=sys.stderr)
        print("먼저 `python -m tsa.collect --fetch` 또는 `--demo`를 실행하세요.", file=sys.stderr)
        return 1
    build(data_path, out_dir, max(5, args.days), args.window, args.threshold, args.lookback)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
