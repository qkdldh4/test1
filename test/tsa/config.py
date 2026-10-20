"""프로젝트 경로와 분석 파라미터."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
TEST_DIR = PROJECT_DIR.parent
ASSETS_DIR = PROJECT_DIR / "assets"
WEB_DIR = PROJECT_DIR / "web"
STATIC_DIR = ASSETS_DIR / "static"
VENDOR_DIR = ASSETS_DIR / "vendor"
DATA_DIR = ASSETS_DIR / "data"
LATEST_FILE = DATA_DIR / "latest.json"

# 수집/샘플 산출물이 저장되는 곳. 서버는 읽기만 한다.
def data_dir() -> Path:
    override = os.environ.get("TSA_DATA_DIR")
    return Path(override).resolve() if override else DATA_DIR


def latest_path() -> Path:
    return data_dir() / "latest.json"


# ---- 분석 파라미터 ------------------------------------------------------
DEFAULT_WINDOW = 20          # 정규화(상대강도) 이동 표준편차 창
DEFAULT_THRESHOLD = 0.5      # |z| < 0.5 이면 횡보(중립)
DEFAULT_LOOKBACK = 40        # 사이드바 탐색 기본 기간(거래일)
DEFAULT_STOCK_COUNT = 200    # 코스피 시총 상위 종목 수
BENCHMARK_NAME = "KODEX 200"
PRICE_MIN = 100              # 이보다 싼 종목은 유동성/데이터 오류로 제외

GROUP_UP = "상향"
GROUP_FLAT = "횡보"
GROUP_DOWN = "하향"
GROUP_ORDER = (GROUP_UP, GROUP_FLAT, GROUP_DOWN)
