# KOSPI 상대강도 레이더

KODEX 200과 코스피 시가총액 상위 200종목(총 201개 종목)의 일봉을 수집해,
**KODEX 200 대비 상대강도**로 종목을 상향·횡보·하향으로 나누고,
**거래량·시가총액 기반 영향력**과 **그룹 전환(상향→하향 등)** 을 추적하는
시계열 분석 웹앱입니다.

- Python 표준 라이브러리만으로 도는 로컬 서버 + JSON API
- 실제 시세는 [FinanceDataReader(fdr)](https://github.com/FinanceData/FinanceDataReader)로 수집
- 네트워크가 없어도 동작하는 **데모(합성) 데이터** 내장
- 서버 없이 볼 수 있는 **정적 페이지**(GitHub Pages) 빌드 지원
- VS Code에서 실행/디버깅할 수 있는 `launch.json` 포함

## 바로 보기

| 구분 | 주소 |
| --- | --- |
| GitHub Pages (정적, HTTPS) | `https://qkdldh4.github.io/py311/test/tsa/web/` |
| 로컬 서버 | `http://127.0.0.1:8000/` |

> 정적 페이지는 `main` 브랜치에 반영된 뒤 열립니다. 로컬 서버는 파라미터를 바꿔
> 실시간으로 다시 계산할 수 있고, 정적 페이지는 빌드 시점의 기본값
> (20거래일 창 · ±0.5σ · 최근 60거래일)으로 계산된 결과를 보여줍니다.

## 화면

1. **개요** — 상향·횡보·하향 종목 수 추이와 KODEX 200 누적 흐름, 당일 영향력
   Top 12, 주도주 릴레이(일별 기여도 1~3위), 시장 내부 온도(상승 비율·거래대금
   유입), 기준일 그룹 전환 종목.
2. **종목 영향력** — 상대강도 z × 거래량비 산점도, 영향력 점수 구성(기여도 50% ·
   거래대금 30% · 시총 20%), 정렬·검색 가능한 200종목 랭킹.
3. **그룹 전환** — 전일→당일 그룹 이동 행렬(상향→하향 등 9개 조합), 일별 상향/하향
   전환 수, 기준일 전환 종목, 전환이 잦은 종목.
4. **종목 상세** — 주가와 z 타임라인, 60일 그룹 스트립, 일별 지수 기여도, 전환 이력.

## 빠른 시작 (VS Code)

```bash
# 저장소 루트에서
cd test

# 1) (선택) 가상환경
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate

# 2) 실데이터를 쓸 때만 fdr 설치 (데모/서버/정적 빌드는 설치 불필요)
python -m pip install -r tsa/requirements.txt

# 3) 데이터 준비
python -m tsa.collect --demo      # 네트워크 없이 합성 데모
# 또는
python -m tsa.collect --fetch     # fdr로 실제 일봉 수집

# 4) 서버 실행
python -m tsa.server
# → 브라우저에서 http://127.0.0.1:8000/ (자동으로 열립니다)
```

`test` 폴더를 VS Code로 열면 **실행 및 디버그** 패널에
`TSA · 로컬 서버`, `TSA · fdr 실데이터 수집`, `TSA · 테스트` 구성이 나타납니다
(`test/.vscode/launch.json`).

서버 옵션:

```bash
python -m tsa.server --port 9000 --no-browser
python -m tsa.server --data tsa/assets/data/latest.json
python -m tsa.server --host 0.0.0.0      # 다른 기기에서 접속할 때
```

`latest.json`이 없으면 서버가 데모 데이터를 자동 생성합니다.

## 실데이터 수집 (fdr)

```bash
python -m tsa.collect --fetch
python -m tsa.collect --fetch --start 2025-01-01 --top 200 --workers 2
python -m tsa.collect --fetch --no-preferred      # 우선주 제외
```

- **벤치마크**: `069500` KODEX 200. 수집에 실패하면 코스피200 지수(`KS200`)로 대체합니다.
- **유니버스**: `fdr.StockListing('KOSPI')` 시가총액 상위 200종목. 실패하면
  `tsa/assets/data/universe_seed.json`(2026-10-19 KRX 스냅샷)을 사용합니다.
- **캐시**: `tsa/assets/data/cache/<코드>.json`. 같은 기간은 다시 요청하지 않으며
  `--refresh`로 강제 갱신합니다.
- **출력**: `tsa/assets/data/latest.json` (스키마 `schema: 1`).
- 네이버 금융/KRX 접속이 필요하므로 국내 네트워크에서 실행하는 것을 권장합니다.
  요청이 많으면 `--workers 1`(기본값)로 두고 `--start` 범위를 줄이세요.

## 정적 페이지(GitHub Pages) 빌드

```bash
cd test
python -m tsa.build_static                 # tsa/web/data 에 생성
python -m tsa.build_static --days 90       # 더 긴 기간
```

`tsa/web/`에는 `index.html`, `styles.css`, `js/`, `vendor/echarts.min.js`,
`data/`가 함께 들어 있습니다. 이 폴더를 GitHub `main` 브랜치에 push하면
저장소 Pages 설정(브랜치 `main` / 루트)에 따라 아래 주소로 HTTPS 배포됩니다.

```
https://<사용자명>.github.io/py311/test/tsa/web/
```

웹앱은 먼저 `/api/meta`를 시도하고, 실패하면 자동으로 `data/meta.json`을 읽는
**정적 모드**로 전환합니다. 즉 같은 폴더가 로컬 서버와 GitHub Pages에서 모두
동작합니다.

## 계산 방식

| 항목 | 정의 |
| --- | --- |
| 당일 등락률 | `종가 / 전일 종가 − 1` |
| 초과 등락률 | `종목 등락률 − KODEX 200 등락률` |
| 상대강도 z | `초과 등락률 ÷ 최근 N거래일(기본 20) 표준편차` (현재 값 포함 이동 창) |
| 그룹 | `z ≥ +T` 상향, `z ≤ −T` 하향, 그 외 횡보 (기본 `T = 0.5σ`) |
| 시총 비중 | `종목 시총 ÷ 200종목 시총 합` |
| 지수 기여도 | `시총 비중 × 당일 등락률` (%p) — 200종목 가중 수익률과 동일 |
| 거래량비 | `당일 거래량 ÷ 직전 5일 평균 거래량` |
| 거래대금 유입 | `부호(z) × 거래대금`의 양수 합 ÷ 전체 합 × 100 |
| 영향력 점수 | `|기여도|`·거래대금·시총의 백분위를 50:30:20으로 합성한 0~100 값 |
| 전환 행렬 | 선택 기간의 `전일 그룹 → 당일 그룹` 횟수 (9개 조합) |

- z의 표준편차는 **모집단 표준편차**(`n`으로 나눔)이며, 표준편차가 0이면 z는
  계산하지 않습니다(결측).
- 기여도는 ETF 가격이 아닌 **시총 가중 수익률** 추정치입니다. KODEX 200의 실제
  추적오차·괴리율과는 다를 수 있습니다.
- 우선주는 기본 포함입니다(시총 상위 200 기준). 필요하면 `--no-preferred`.

## JSON API

로컬 서버 기준이며 모든 응답은 UTF-8 JSON입니다.

| 경로 | 설명 |
| --- | --- |
| `GET /api/health` | 상태·데이터 소스·종목 수 |
| `GET /api/meta` | 기준일, 거래일 수, 기본 파라미터, 경고 |
| `GET /api/overview?window=20&threshold=0.5&lookback=60` | 일별 그룹 수·시장 내부·주도주 |
| `GET /api/universe?date=2026-10-19&lookback=60` | 기준일 종목별 z·기여도·영향력 점수 |
| `GET /api/transitions?lookback=60&date=...` | 전환 행렬·일별 전환·전환 종목 |
| `GET /api/stock/005930` | 종목 시계열·기간 통계·전환 이력 |
| `GET /api/export.csv?date=...` | 기준일 종목 표 CSV |
| `GET /data/*`, `GET /js/*` | 정적 웹 자산 |

`window`(2~250), `threshold`(0~10), `lookback`(거래일), `start`/`end`(YYYY-MM-DD),
`date`(기준일)를 조합할 수 있습니다. 오류는 `{"error": "..."}`와 4xx로 응답합니다.

## 프로젝트 구조

```
test/
├─ .vscode/launch.json        # VS Code 실행 구성
├─ tsa/
│  ├─ config.py               # 경로·기본 파라미터
│  ├─ analytics.py            # 수익률·z·그룹·백분위 등 순수 계산
│  ├─ dataset.py              # 원본 → 일별/종목별 분석 데이터셋
│  ├─ collect.py              # fdr 실데이터 수집 + 데모 생성
│  ├─ universe.py             # 예비 유니버스(코스피 시총 상위 200)
│  ├─ server.py               # 표준 라이브러리 HTTP 서버 + JSON API
│  ├─ build_static.py         # GitHub Pages용 정적 데이터 빌드
│  ├─ assets/
│  │  ├─ data/universe_seed.json
│  │  └─ data/latest.json     # collect 산출물(깃 제외)
│  └─ web/                    # 웹앱 + 정적 데이터(Pages 배포 대상)
└─ tests/                     # unittest 60여 개
```

## 테스트

```bash
cd test
python -m unittest discover -s tests -v
```

- `test_analytics.py`: 수익률·z·베타·백분위·그룹 판정
- `test_dataset.py`: 스냅샷·기간 통계·전환 행렬·종목 상세
- `test_collect.py`: 데모 생성 결정성·실데이터 폴백·저장
- `test_api.py`: HTTP 엔드포인트·CSV·정적 파일·경로 보호
- `test_build_static.py`: 정적 산출물 구조

## 데이터에 대한 안내

- 저장소에 포함된 데모 데이터는 **실제 종목명·코드·시가총액**에 맞춰 만든
  **합성 가격/거래량**입니다. 투자 판단에 사용할 수 없습니다. 화면 상단의
  `DEMO · 합성 데이터` 배지로 구분됩니다.
- 실제 데이터를 수집하면 배지가 `fdr 실데이터`로 바뀝니다.
- 본 앱과 지표는 데이터 탐색·교육용이며 매매 권유가 아닙니다.
