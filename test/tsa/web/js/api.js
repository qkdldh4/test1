/**
 * 서버 API와 정적(GitHub Pages) 데이터 파일을 같은 인터페이스로 감싼다.
 * 서버가 없으면 자동으로 data/*.json 으로 폴백한다.
 */
export const api = {
  mode: "unknown",
  meta: null,
  base: "",
};

const overviewCache = new Map();
const universeCache = new Map();
const stockCache = new Map();
let transitionsCache = null;

function buildQuery(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function fetchJson(url, options = {}, timeoutMs = 15000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      cache: "no-store",
      signal: controller.signal,
      ...options,
    });
    if (!response.ok) {
      let detail = "";
      try {
        const payload = await response.json();
        detail = payload.error || payload.message || "";
      } catch {
        /* not json */
      }
      throw new Error(detail || `요청 실패 (${response.status})`);
    }
    return await response.json();
  } finally {
    window.clearTimeout(timer);
  }
}

export async function initApi() {
  try {
    const meta = await fetchJson(`${api.base}api/meta`, {}, 2500);
    api.mode = "server";
    api.meta = meta;
    return meta;
  } catch {
    /* 서버가 없으면 정적 데이터로 폴백 */
  }
  const meta = await fetchJson(`${api.base}data/meta.json`, {}, 15000);
  api.mode = "static";
  api.meta = meta;
  return meta;
}

export function clearCaches() {
  overviewCache.clear();
  universeCache.clear();
  stockCache.clear();
  transitionsCache = null;
}

function staticSliceOverview(payload, lookback) {
  if (!payload || !Array.isArray(payload.days)) return payload;
  const days = payload.days.slice(-Math.max(1, lookback));
  const latest = days[days.length - 1] || null;
  const previous = days.length > 1 ? days[days.length - 2] : null;
  return {
    ...payload,
    days,
    latest,
    previous,
    start: days[0]?.date ?? payload.start,
    end: days[days.length - 1]?.date ?? payload.end,
    totals: {
      days: days.length,
      avg_up: days.reduce((acc, d) => acc + d.up, 0) / (days.length || 1),
      avg_down: days.reduce((acc, d) => acc + d.down, 0) / (days.length || 1),
      avg_net: days.reduce((acc, d) => acc + (d.net || 0), 0) / (days.length || 1),
    },
  };
}

export async function getOverview({ window, threshold, lookback }) {
  if (api.mode === "server") {
    return fetchJson(
      `${api.base}api/overview${buildQuery({ window, threshold, lookback })}`
    );
  }
  const key = "overview";
  if (!overviewCache.has(key)) {
    overviewCache.set(key, await fetchJson(`${api.base}data/overview.json`));
  }
  return staticSliceOverview(overviewCache.get(key), lookback);
}

export async function getUniverse({ window, threshold, lookback, date }) {
  if (api.mode === "server") {
    return fetchJson(
      `${api.base}api/universe${buildQuery({ window, threshold, lookback, date })}`
    );
  }
  if (!date) throw new Error("정적 모드에서는 기준일이 필요합니다.");
  if (universeCache.has(date)) return universeCache.get(date);
  const payload = await fetchJson(`${api.base}data/universe/${encodeURIComponent(date)}.json`);
  universeCache.set(date, payload);
  return payload;
}

export async function getTransitions({ window, threshold, lookback, date }) {
  if (api.mode === "server") {
    return fetchJson(
      `${api.base}api/transitions${buildQuery({ window, threshold, lookback, date })}`
    );
  }
  if (!transitionsCache) {
    transitionsCache = await fetchJson(`${api.base}data/transitions.json`);
  }
  return transitionsCache;
}

export async function getStock(code, { window, threshold, lookback, date }) {
  if (api.mode === "server") {
    return fetchJson(
      `${api.base}api/stock/${encodeURIComponent(code)}${buildQuery({
        window,
        threshold,
        lookback,
        date,
      })}`
    );
  }
  if (stockCache.has(code)) return stockCache.get(code);
  const payload = await fetchJson(
    `${api.base}data/stock/${encodeURIComponent(code)}.json`
  );
  stockCache.set(code, payload);
  return payload;
}
