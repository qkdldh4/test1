"""Serve the static Face Note app locally for camera testing."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "127.0.0.1"
PORT = 8000


def main() -> None:
	parser = argparse.ArgumentParser(description="로컬 웹캠 관상 카드")
	parser.add_argument("--host", default=HOST, help="서버 주소 (기본값: 127.0.0.1)")
	parser.add_argument("--port", type=int, default=PORT, help="포트 번호 (기본값: 8000)")
	args = parser.parse_args()

	handler = partial(
		SimpleHTTPRequestHandler,
		directory=str(Path(__file__).resolve().parent),
	)
	server = ThreadingHTTPServer((args.host, args.port), handler)
	print(f"브라우저에서 http://{args.host}:{args.port} 를 여세요. 종료: Ctrl+C")
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		print("\n서버를 종료합니다.")
	finally:
		server.server_close()


if __name__ == "__main__":
	main()
