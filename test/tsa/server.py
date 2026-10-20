"""로컬 개발 서버.

표준 라이브러리만으로 정적 웹앱과 JSON API를 함께 제공한다.

    python -m tsa.server                # http://127.0.0.1:8000
    python -m tsa.server --port 9000 --demo-if-missing

VS Code에서는 터미널에서 위 명령을 실행한 뒤 브라우저를 열면 된다.
(외부에서 접속해야 한다면 ``--host 0.0.0.0``)
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlparse

from . import config
from .dataset import Dataset, load_dataset

MEDIA_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".map": "application/json; charset=utf-8",
}

HOST = "127.0.0.1"
PORT = 8000
LOOKBACK_CHOICES = (20, 40, 60, 90, 120, 250)


def _json_default(value: Any) -> Any:  # pragma: no cover - 방어용
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"JSON 직렬화 불가: {type(value)}")


class State:
    """데이터셋 한 개를 mtime 기준으로 재사용한다."""

    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self._dataset: Dataset | None = None
        self._mtime: float | None = None
        self._lock = threading.Lock()
        self.started_at = time.time()

    def dataset(self) -> Dataset:
        try:
            mtime = self.data_path.stat().st_mtime
        except OSError as exc:
            raise FileNotFoundError(
                f"데이터 파일이 없습니다: {self.data_path}\n"
                "먼저 `python -m tsa.collect --demo` 또는 `--fetch` 를 실행하세요."
            ) from exc
        with self._lock:
            if self._dataset is None or self._mtime != mtime:
                self._dataset = load_dataset(self.data_path)
                self._mtime = mtime
                print(
                    f"  · 데이터 로드: {self.data_path.name} "
                    f"({self._dataset.source}, {len(self._dataset.stocks)}종목, "
                    f"{len(self._dataset.dates)}거래일)",
                    flush=True,
                )
            return self._dataset


class Handler(BaseHTTPRequestHandler):
    server_version = "TSA/1.0"
    protocol_version = "HTTP/1.1"
    state: State
    web_dir: Path

    # -- 공통 응답 ----------------------------------------------------
    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(
            f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} {fmt % args}\n"
        )

    def _send_bytes(
        self,
        body: bytes,
        status: int = 200,
        content_type: str = "application/octet-stream",
        cache: str = "no-store",
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        accept = self.headers.get("Accept-Encoding", "")
        use_gzip = "gzip" in accept and len(body) > 1024
        if use_gzip:
            body = gzip.compress(body, compresslevel=6)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        if use_gzip:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Content-Type-Options", "nosniff")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(
            payload, ensure_ascii=False, separators=(",", ":"), default=_json_default
        ).encode("utf-8")
        self._send_bytes(body, status=status, content_type="application/json; charset=utf-8")

    def _error(self, status: int, message: str) -> None:
        self._json({"error": message, "status": int(status)}, status=status)

    def _static(self, url_path: str) -> None:
        relative = unquote(url_path).lstrip("/") or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        target = (self.web_dir / relative).resolve()
        try:
            target.relative_to(self.web_dir.resolve())
        except ValueError:
            self._error(HTTPStatus.FORBIDDEN, "허용되지 않은 경로입니다.")
            return
        if not target.is_file():
            if "." not in Path(relative).name:
                target = self.web_dir / "index.html"  # SPA fallback
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, f"파일을 찾을 수 없습니다: {relative}")
                return
        suffix = target.suffix.lower()
        content_type = MEDIA_TYPES.get(suffix, "application/octet-stream")
        cache = "public, max-age=300" if suffix in {".js", ".css", ".png", ".svg", ".ico"} else "no-cache"
        if suffix == ".json":
            cache = "no-store"
        self._send_bytes(
            target.read_bytes(),
            content_type=content_type,
            cache=cache,
            extra_headers={"Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'"},
        )

    # -- 라우팅 -------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        started = time.perf_counter()
        try:
            if path.startswith("/api/"):
                self._handle_api(path, query)
            else:
                self._static(path)
        except FileNotFoundError as exc:
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        except ValueError as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except BrokenPipeError:
            return
        except Exception as exc:  # pragma: no cover - 예상치 못한 오류
            import traceback

            traceback.print_exc()
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"서버 오류: {exc}")
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            if elapsed > 50:
                sys.stderr.write(f"    ({elapsed:.0f} ms)\n")

    # -- 파라미터 -----------------------------------------------------
    @staticmethod
    def _q(query: Mapping[str, list[str]], key: str, default: str | None = None) -> str | None:
        values = query.get(key)
        if not values:
            return default
        return values[0]

    def _params(self, query: Mapping[str, list[str]]) -> dict[str, Any]:
        dataset = self.state.dataset()
        defaults = config
        window = dataset.validate_window(
            int(self._q(query, "window", str(defaults.DEFAULT_WINDOW)) or defaults.DEFAULT_WINDOW)
        )
        threshold = dataset.validate_threshold(
            float(self._q(query, "threshold", str(defaults.DEFAULT_THRESHOLD)) or defaults.DEFAULT_THRESHOLD)
        )
        start = self._q(query, "start")
        end = self._q(query, "end") or self._q(query, "date")
        lookback_raw = self._q(query, "lookback")
        lookback = int(lookback_raw) if lookback_raw else defaults.DEFAULT_LOOKBACK
        if self._q(query, "start") or self._q(query, "end"):
            start_i, end_i = dataset.date_range(start, end)
        else:
            start_i, end_i = dataset.date_range(None, end, lookback=lookback)
        return {
            "dataset": dataset,
            "window": window,
            "threshold": threshold,
            "start_i": start_i,
            "end_i": end_i,
            "start": dataset.dates[start_i],
            "end": dataset.dates[end_i],
            "lookback": lookback,
        }

    # -- API ----------------------------------------------------------
    def _handle_api(self, path: str, query: Mapping[str, list[str]]) -> None:
        if path == "/api/health":
            dataset = self.state.dataset()
            self._json(
                {
                    "status": "ok",
                    "uptime_sec": round(time.time() - self.state.started_at, 1),
                    "data": str(self.state.data_path),
                    "source": dataset.source,
                    "stocks": len(dataset.stocks),
                    "dates": [dataset.dates[0], dataset.dates[-1]],
                }
            )
            return
        if path == "/api/meta":
            dataset = self.state.dataset()
            meta = dataset.meta()
            meta["lookback_choices"] = list(LOOKBACK_CHOICES)
            self._json(meta)
            return
        if path == "/api/overview":
            self._json(self._overview(query))
            return
        if path == "/api/universe":
            self._json(self._universe(query))
            return
        if path == "/api/transitions":
            self._json(self._transitions(query))
            return
        if path.startswith("/api/stock/"):
            code = unquote(path[len("/api/stock/"):]).strip()
            self._json(self._stock(code, query))
            return
        if path == "/api/export.csv":
            self._export_csv(query)
            return
        if path == "/api/config":
            self._json(
                {
                    "window": config.DEFAULT_WINDOW,
                    "threshold": config.DEFAULT_THRESHOLD,
                    "lookback_choices": list(LOOKBACK_CHOICES),
                }
            )
            return
        self._error(HTTPStatus.NOT_FOUND, f"알 수 없는 API 경로입니다: {path}")

    def _overview(self, query: Mapping[str, list[str]]) -> dict[str, Any]:
        p = self._params(query)
        ds: Dataset = p["dataset"]
        days = [d for d in ds.daily(p["window"], p["threshold"]) if p["start_i"] <= d["i"] <= p["end_i"]]
        if not days:
            raise ValueError("선택한 기간에 계산 가능한 데이터가 없습니다. 기간을 늘려보세요.")
        latest = days[-1]
        prev = days[-2] if len(days) > 1 else None

        # 영향력 상위 종목 (선택 기간 누적 기여도 기준)
        stats = ds.range_stats(p["window"], p["threshold"], p["start_i"], p["end_i"])
        snap = ds.snapshot(p["window"], p["threshold"], p["end_i"])
        by_code = {row["code"]: row for row in snap["rows"]}
        contributors = []
        for row in stats:
            live = by_code.get(row["code"])
            if not live:
                continue
            contributors.append(
                {
                    **live,
                    "score": row.get("score"),
                    "score_parts": row.get("score_parts"),
                    "cum_contrib": row.get("cum_contrib"),
                    "abs_contrib": row.get("abs_contrib"),
                    "streak": row.get("streak"),
                    "changes": row.get("changes"),
                    "last_group": row.get("last_group"),
                }
            )
        contributors.sort(key=lambda r: abs(r.get("contrib") or 0), reverse=True)
        leaders = contributors[:12]

        movers = {"up": [], "down": []}
        trans = ds.transitions(p["window"], p["threshold"], p["start_i"], p["end_i"], day_index=p["end_i"])
        for item in trans["changes"]:
            key = "up" if item["upgrade"] else "down"
            if len(movers[key]) < 10:
                movers[key].append(item)

        return {
            "meta": ds.meta(),
            "window": p["window"],
            "threshold": p["threshold"],
            "start": p["start"],
            "end": p["end"],
            "dates": [d["date"] for d in days],
            "days": days,
            "latest": latest,
            "previous": prev,
            "contributors": leaders,
            "movers": movers,
            "totals": {
                "days": len(days),
                "avg_up": round(sum(d["up"] for d in days) / len(days), 1),
                "avg_down": round(sum(d["down"] for d in days) / len(days), 1),
                "avg_net": round(sum((d["net"] or 0) for d in days) / len(days), 1),
            },
        }

    def _universe(self, query: Mapping[str, list[str]]) -> dict[str, Any]:
        p = self._params(query)
        ds: Dataset = p["dataset"]
        day = self._q(query, "date")
        day_i = ds.day_index(day) if day else p["end_i"]
        snap = ds.snapshot(p["window"], p["threshold"], day_i)
        stats = {row["code"]: row for row in ds.range_stats(p["window"], p["threshold"], p["start_i"], day_i)}
        rows = []
        for row in snap["rows"]:
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
            "date": snap["date"],
            "start": p["start"],
            "end": ds.dates[day_i],
            "window": p["window"],
            "threshold": p["threshold"],
            "summary": snap["summary"],
            "rows": rows,
            "counts": {
                "all": len(rows),
                "up": sum(1 for r in rows if r["grp"] == "U"),
                "flat": sum(1 for r in rows if r["grp"] == "F"),
                "down": sum(1 for r in rows if r["grp"] == "D"),
            },
        }

    def _transitions(self, query: Mapping[str, list[str]]) -> dict[str, Any]:
        p = self._params(query)
        ds: Dataset = p["dataset"]
        day = self._q(query, "date")
        day_i = ds.day_index(day) if day else p["end_i"]
        payload = ds.transitions(p["window"], p["threshold"], p["start_i"], day_i, day_index=day_i)
        stats = {row["code"]: row for row in ds.range_stats(p["window"], p["threshold"], p["start_i"], day_i)}
        for item in payload["changes"]:
            stat = stats.get(item["code"], {})
            item["score"] = stat.get("score")
            item["streak"] = stat.get("streak")
            item["events"] = stat.get("events") or []
        payload["leaders"] = sorted(
            (row for row in stats.values() if row.get("changes")),
            key=lambda row: (row.get("changes") or 0, row.get("score") or 0),
            reverse=True,
        )[:25]
        payload["window"] = p["window"]
        payload["threshold"] = p["threshold"]
        payload["start"] = p["start"]
        payload["end"] = ds.dates[day_i]
        return payload

    def _stock(self, code: str, query: Mapping[str, list[str]]) -> dict[str, Any]:
        p = self._params(query)
        ds: Dataset = p["dataset"]
        day = self._q(query, "date")
        end_i = ds.day_index(day) if day else p["end_i"]
        detail = ds.stock_detail(code, p["window"], p["threshold"], p["start_i"], end_i)
        if detail is None:
            raise ValueError(f"종목을 찾을 수 없습니다: {code}")
        detail["window"] = p["window"]
        detail["threshold"] = p["threshold"]
        detail["start"] = p["start"]
        detail["end"] = ds.dates[end_i]
        return detail

    def _export_csv(self, query: Mapping[str, list[str]]) -> None:
        payload = self._universe(query)
        fields = [
            "code", "name", "close", "ret", "rel", "z", "grp", "vr", "mcap",
            "weight", "contrib", "value", "beta", "score", "streak", "changes",
            "up_share", "down_share",
        ]
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in payload["rows"]:
            writer.writerow(row)
        filename = f"kospi_universe_{payload['date'].replace('-', '')}.csv"
        body = ("\ufeff" + buffer.getvalue()).encode("utf-8")
        self._send_bytes(
            body,
            content_type="text/csv; charset=utf-8",
            extra_headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


def ensure_data(data_path: Path, generate_demo: bool) -> None:
    if data_path.exists():
        return
    if not generate_demo:
        raise SystemExit(
            f"데이터가 없습니다: {data_path}\n"
            "  python -m tsa.collect --demo   (합성 데이터)\n"
            "  python -m tsa.collect --fetch  (실데이터)"
        )
    print("데이터가 없어 데모 데이터를 생성합니다 …")
    from types import SimpleNamespace

    from . import collect

    args = SimpleNamespace(
        fetch=False, demo=True, start=None, end=None, top=config.DEFAULT_STOCK_COUNT,
        no_preferred=False, out=None, cache_dir=None, refresh=False, workers=1,
    )
    payload = collect.generate_demo(args)
    collect.save_raw(payload, data_path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tsa.server", description="코스피 상대강도 분석 로컬 서버"
    )
    parser.add_argument("--host", default=HOST, help=f"바인딩 주소 (기본 {HOST})")
    parser.add_argument("--port", type=int, default=PORT, help=f"포트 (기본 {PORT})")
    parser.add_argument("--data", default=None, help="분석할 latest.json 경로")
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않습니다.")
    parser.add_argument("--no-demo", action="store_true", help="데이터가 없을 때 데모를 생성하지 않습니다.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data_path = Path(args.data).resolve() if args.data else config.latest_path()
    ensure_data(data_path, generate_demo=not args.no_demo)

    state = State(data_path)
    state.dataset()  # 초기 로드(오류를 조기에 확인)

    handler = type("BoundHandler", (Handler,), {"state": state, "web_dir": config.WEB_DIR})
    server = ThreadingHTTPServer((args.host, args.port), handler)
    server.daemon_threads = True
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::", ""} else args.host
    url = f"http://{display_host}:{args.port}/"
    print("")
    print(f"  시계열 분석 서버 준비 완료 → {url}")
    print(f"  데이터: {data_path}")
    print("  종료: Ctrl+C")
    print("")
    if not args.no_browser and display_host in {"127.0.0.1", "localhost"}:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n서버를 종료합니다.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
