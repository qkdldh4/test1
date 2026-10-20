"""순수 계산 계층: 수익률, 정규화(상대강도), 그룹 판정, 영향력 지표.

외부 라이브러리 없이 동작하며 ``test/tests``에서 직접 검증한다.
모든 함수는 결측치(``None``)를 허용하고 같은 길이의 리스트를 돌려준다.
"""

from __future__ import annotations

from typing import Iterable, Sequence

Number = float | int
MaybeNumber = float | None
Series = Sequence[MaybeNumber]

UP = "상향"
FLAT = "횡보"
DOWN = "하향"
GROUPS = (UP, FLAT, DOWN)
GROUP_CODES = {UP: "U", FLAT: "F", DOWN: "D"}

VOLUME_WINDOW = 5          # 거래량 비율(vr)의 기준 이동평균 일수
MAX_VOLUME_RATIO = 50.0    # 극단값 방어용 상한


def _clean(values: Iterable[MaybeNumber]) -> list[MaybeNumber]:
    out: list[MaybeNumber] = []
    for v in values:
        if v is None or v != v:  # NaN
            out.append(None)
        else:
            out.append(float(v))
    return out


def pct_returns(closes: Series) -> list[MaybeNumber]:
    """전일 종가 대비 당일 종가 등락률(소수). 첫 값은 ``None``."""
    cleaned = _clean(closes)
    result: list[MaybeNumber] = [None]
    for prev, cur in zip(cleaned, cleaned[1:]):
        if prev is None or cur is None or prev <= 0:
            result.append(None)
        else:
            result.append(cur / prev - 1.0)
    return result


def relative_returns(returns: Series, benchmark_returns: Series) -> list[MaybeNumber]:
    """코스피200(KODEX 200) 기준 초과 등락률."""
    if len(returns) != len(benchmark_returns):
        raise ValueError("수익률 시계열 길이가 다릅니다.")
    out: list[MaybeNumber] = []
    for r, b in zip(_clean(returns), _clean(benchmark_returns)):
        out.append(None if r is None or b is None else r - b)
    return out


def rolling_zscore(values: Series, window: int) -> list[MaybeNumber]:
    """직전 ``window``개 값의 평균/표준편차로 정규화한 z 점수.

    오늘 값을 포함한 창(rolling)을 사용하며, 창이 가득 차기 전 구간은 ``None``.
    표준편차가 0이면 ``None``으로 둔다.
    """
    if window < 2:
        raise ValueError("window는 2 이상이어야 합니다.")
    cleaned = _clean(values)
    n = len(cleaned)
    z: list[MaybeNumber] = [None] * n
    s = 0.0
    sq = 0.0
    count = 0
    queue: list[float] = []
    for i, v in enumerate(cleaned):
        if v is None:
            # 결측이 끼면 창을 비워 계산을 보수적으로 끊는다.
            queue.clear()
            s = sq = 0.0
            count = 0
            continue
        queue.append(v)
        s += v
        sq += v * v
        count += 1
        if count > window:
            old = queue.pop(0)
            s -= old
            sq -= old * old
            count -= 1
        if count == window:
            mean = s / window
            var = max(sq / window - mean * mean, 0.0)
            std = var ** 0.5
            if std > 1e-12:
                z[i] = (v - mean) / std
    return z


def rolling_volume_ratio(volumes: Series, window: int = VOLUME_WINDOW) -> list[MaybeNumber]:
    """직전 ``window``일 평균 거래량 대비 당일 거래량 배율."""
    if window < 1:
        raise ValueError("window는 1 이상이어야 합니다.")
    cleaned = _clean(volumes)
    out: list[MaybeNumber] = [None] * len(cleaned)
    for i in range(window, len(cleaned)):
        cur = cleaned[i]
        prior = cleaned[i - window:i]
        if cur is None or any(p is None for p in prior):
            continue
        avg = sum(prior) / window  # type: ignore[arg-type]
        if avg <= 0:
            continue
        out[i] = min(cur / avg, MAX_VOLUME_RATIO)
    return out


def rolling_beta(returns: Series, benchmark_returns: Series, window: int) -> list[MaybeNumber]:
    """코스피200 수익률에 대한 단순 회귀 베타(롤링)."""
    if window < 2:
        raise ValueError("window는 2 이상이어야 합니다.")
    r = _clean(returns)
    b = _clean(benchmark_returns)
    if len(r) != len(b):
        raise ValueError("수익률 시계열 길이가 다릅니다.")
    out: list[MaybeNumber] = [None] * len(r)
    for i in range(window - 1, len(r)):
        xs: list[float] = []
        ys: list[float] = []
        valid = True
        for j in range(i - window + 1, i + 1):
            if r[j] is None or b[j] is None:
                valid = False
                break
            xs.append(b[j])  # type: ignore[arg-type]
            ys.append(r[j])  # type: ignore[arg-type]
        if not valid:
            continue
        mx = sum(xs) / window
        my = sum(ys) / window
        var = sum((x - mx) ** 2 for x in xs) / window
        if var <= 1e-18:
            continue
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / window
        out[i] = cov / var
    return out


def classify(z: MaybeNumber, threshold: float) -> str | None:
    """정규화 값 → 상향/횡보/하향. 값이 없으면 ``None``."""
    if z is None:
        return None
    if z >= threshold:
        return UP
    if z <= -threshold:
        return DOWN
    return FLAT


def percentile_ranks(values: Iterable[MaybeNumber]) -> list[MaybeNumber]:
    """0~1 백분위 순위(동순위는 평균). 결측치는 ``None``."""
    items = list(values)
    valid = sorted((v, i) for i, v in enumerate(items) if v is not None)
    n = len(valid)
    out: list[MaybeNumber] = [None] * len(items)
    if n == 0:
        return out
    if n == 1:
        out[valid[0][1]] = 1.0
        return out
    pos = 0
    while pos < n:
        end = pos
        while end + 1 < n and valid[end + 1][0] == valid[pos][0]:
            end += 1
        avg_rank = (pos + end) / 2.0
        pct = avg_rank / (n - 1)
        for k in range(pos, end + 1):
            out[valid[k][1]] = pct
        pos = end + 1
    return out


def first_valid_index(z: Series) -> int | None:
    for i, v in enumerate(z):
        if v is not None:
            return i
    return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_div(num: float, den: float, default: float = 0.0) -> float:
    return num / den if den else default


def mean(values: Iterable[MaybeNumber]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)  # type: ignore[arg-type]


def contribution(weight: float, stock_return: MaybeNumber) -> MaybeNumber:
    """시총 비중 × 등락률(%p). 200종목 합은 유니버스 가중 수익률이 된다."""
    if stock_return is None:
        return None
    return weight * stock_return * 100.0


def flow_score(z: MaybeNumber, value_traded: MaybeNumber) -> MaybeNumber:
    """상대강도 부호 × 거래대금. 양수면 유입, 음수면 유출로 해석."""
    if z is None or value_traded is None:
        return None
    return (1.0 if z >= 0 else -1.0) * value_traded
