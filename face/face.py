"""로컬 웹캠 사진의 얼굴 기준점을 측정해 전통 관상 정보를 제공합니다."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from face_analysis import analyze_photo, close_analyzer



HOST = "127.0.0.1"
PORT = 8000
MAX_IMAGE_BYTES = 8 * 1024 * 1024
PAGE_PATH = Path(__file__).with_name("index.html")


class FaceHandler(BaseHTTPRequestHandler):
	def _send(self, status: int, body: bytes, content_type: str) -> None:
		self.send_response(status)
		self.send_header("Content-Type", content_type)
		self.send_header("Content-Length", str(len(body)))
		self.send_header("X-Content-Type-Options", "nosniff")
		self.end_headers()
		self.wfile.write(body)

	def _send_json(self, status: int, payload: dict[str, object]) -> None:
		body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
		self._send(status, body, "application/json; charset=utf-8")

	def do_GET(self) -> None:
		if urlparse(self.path).path not in {"/", "/index.html"}:
			self._send_json(404, {"error": "페이지를 찾을 수 없습니다."})
			return
		try:
			body = PAGE_PATH.read_bytes()
		except OSError:
			self._send_json(500, {"error": "index.html 파일을 읽을 수 없습니다."})
			return
		self._send(200, body, "text/html; charset=utf-8")

	def do_POST(self) -> None:
		if urlparse(self.path).path != "/analyze":
			self._send_json(404, {"error": "요청 경로를 찾을 수 없습니다."})
			return

		try:
			content_length = int(self.headers.get("Content-Length", "0"))
		except ValueError:
			self._send_json(400, {"error": "잘못된 이미지 요청입니다."})
			return
		if not 0 < content_length <= MAX_IMAGE_BYTES:
			self._send_json(413, {"error": "사진은 8MB 이하로 촬영해 주세요."})
			return

		image_bytes = self.rfile.read(content_length)
		if len(image_bytes) != content_length:
			self._send_json(400, {"error": "사진을 끝까지 읽지 못했습니다. 다시 시도해 주세요."})
			return
		try:
			self._send_json(200, analyze_photo(image_bytes))
		except ValueError as error:
			self._send_json(422, {"error": str(error)})

	def log_message(self, format: str, *args: object) -> None:
		print(f"[{self.log_date_time_string()}] {format % args}")


def main() -> None:
	parser = argparse.ArgumentParser(description="로컬 웹캠 관상 카드")
	parser.add_argument("--host", default=HOST, help="서버 주소 (기본값: 127.0.0.1)")
	parser.add_argument("--port", type=int, default=PORT, help="포트 번호 (기본값: 8000)")
	args = parser.parse_args()

	server = ThreadingHTTPServer((args.host, args.port), FaceHandler)
	print(f"브라우저에서 http://{args.host}:{args.port} 를 여세요. 종료: Ctrl+C")
	try:
		server.serve_forever()
	except KeyboardInterrupt:
		print("\n서버를 종료합니다.")
	finally:
		server.server_close()
		close_analyzer()


if __name__ == "__main__":
	main()
