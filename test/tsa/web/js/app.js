import {
  api,
  initApi,
  getOverview,
  getUniverse,
  getTransitions,
  getStock,
  clearCaches,
} from "./api.js";
import * as charts from "./charts.js";
import {
  GROUP_LABEL,
  GROUP_ORDER,
  esc,
  fmtPct,
  fmtPp,
  fmtZ,
  fmtNum,
  fmtMcap,
  fmtValue,
  fmtPrice,
  fmtDateShort,
  fmtDateLong,
  groupBadge,
  signClass,
  clamp,
  debounce,
  downloadCsv,
} from "./utils.js";

const $ = (id) => document.getElementById(id);
const state = {
  meta: null,
  staticMode: false,
  window: 20,
  threshold: 0.5,
  lookback: 60,
  overview: null,
  days: [],
  universe: null,
  transitions: null,
  transitionsKey: null,
  detail: null,
  detailCode: null,
  date: null,
  group: "ALL",
  search: "",
  sort: { key: "score", dir: "desc" },
  tab: "overview",
  relayAll: false,
  loadingCount: 0,
};

const els = {
  lookback: $("lookback"),
  window: $("window"),
  threshold: $("threshold"),
  dateSlider: $("dateSlider"),
  dateLabel: $("dateLabel"),
  prevDate: $("prevDate"),
  nextDate: $("nextDate"),
  search: $("search"),
  groupFilter: $("groupFilter"),
  stockTable: $("stockTable"),
  tableCount: $("tableCount"),
  detailSelect: $("detailSelect"),
};

/* ------------------------------------------------------------------ */
/* 초기화                                                              */
/* ------------------------------------------------------------------ */
async function main() {
  bindEvents();
  try {
    const meta = await initApi();
    state.meta = meta;
    state.staticMode = api.mode === "static";
    state.window = meta.defaults?.window ?? 20;
    state.threshold = meta.defaults?.threshold ?? 0.5;
    state.lookback = state.staticMode ? meta.static?.lookback ?? 60 : 60;
    setupHeader(meta);
    setupControls(meta);
    await refreshAll({ silent: true });
  } catch (error) {
    console.error(error);
    toast(`초기화 실패: ${error.message}`, true);
    $("sourceBadge").textContent = "데이터 없음";
    $("sourceBadge").className = "badge badge-muted";
  }
}

function setupHeader(meta) {
  $("stockCount").textContent = fmtNum(meta.stock_count);
  const modeBadge = $("modeBadge");
  modeBadge.textContent = state.staticMode ? "GitHub Pages" : "로컬 서버";
  modeBadge.className = `badge ${state.staticMode ? "badge-static" : "badge-live"}`;

  const sourceBadge = $("sourceBadge");
  const isDemo = meta.source === "demo";
  sourceBadge.textContent = isDemo ? "DEMO · 합성 데이터" : "fdr 실데이터";
  sourceBadge.className = `badge ${isDemo ? "badge-demo" : "badge-live"}`;

  $("dataStamp").textContent = `${meta.date_end} 기준 · ${fmtNum(meta.trading_days)}거래일`;
  $("staticNotice").classList.toggle("hidden", !state.staticMode);
  $("demoNotice").classList.toggle("hidden", !isDemo);
  updateThresholdLabels();
}

function setupControls(meta) {
  const choices = state.staticMode
    ? [meta.static?.lookback ?? state.lookback]
    : meta.lookback_choices ?? [20, 40, 60, 90, 120, 250];
  els.lookback.innerHTML = choices
    .map((value) => `<option value="${value}">${value}거래일</option>`)
    .join("");
  els.lookback.value = String(state.lookback);
  els.window.value = String(state.window);
  els.threshold.value = String(state.threshold);

  if (state.staticMode) {
    els.lookback.disabled = true;
    els.window.disabled = true;
    els.threshold.disabled = true;
    els.lookback.title = "정적 페이지에서는 기본값으로 계산됩니다.";
    els.window.title = "정적 페이지에서는 기본값으로 계산됩니다.";
    els.threshold.title = "정적 페이지에서는 기본값으로 계산됩니다.";
  }
}

/* ------------------------------------------------------------------ */
/* 이벤트                                                              */
/* ------------------------------------------------------------------ */
function bindEvents() {
  els.lookback.addEventListener("change", () => {
    state.lookback = Number(els.lookback.value);
    invalidate();
    refreshAll({ silent: true });
  });

  const reloadParams = debounce(() => {
    invalidate();
    refreshAll({ silent: true });
  }, 420);

  els.window.addEventListener("change", () => {
    state.window = clamp(Number(els.window.value) || 20, 5, 120);
    els.window.value = String(state.window);
    updateThresholdLabels();
    reloadParams();
  });
  els.threshold.addEventListener("change", () => {
    state.threshold = clamp(Number(els.threshold.value) || 0.5, 0, 3);
    els.threshold.value = String(state.threshold);
    updateThresholdLabels();
    reloadParams();
  });

  els.dateSlider.addEventListener("input", () => onSliderMove(false));
  els.dateSlider.addEventListener("change", () => onSliderMove(true));
  $("prevDate").addEventListener("click", () => stepDate(-1));
  $("nextDate").addEventListener("click", () => stepDate(1));

  $("groupFilter").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-group]");
    if (!button) return;
    state.group = button.dataset.group;
    [...$("groupFilter").querySelectorAll("button")].forEach((item) =>
      item.classList.toggle("active", item === button)
    );
    if (state.universe) {
      renderTable();
      charts.renderScatter($("chartScatter"), filteredRows(), state.threshold);
      charts.renderScoreBar($("chartScore"), filteredRows());
    }
  });

  $("search").addEventListener(
    "input",
    debounce(() => {
      state.search = $("search").value.trim().toLowerCase();
      if (state.universe) {
        renderTable();
        charts.renderScatter($("chartScatter"), filteredRows(), state.threshold);
        charts.renderScoreBar($("chartScore"), filteredRows());
      }
    }, 120)
  );

  $("csvBtn").addEventListener("click", exportCsv);
  $("reloadBtn").addEventListener("click", () => {
    invalidate();
    refreshAll({ silent: false });
  });

  $("tabs").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) switchTab(button.dataset.tab);
  });

  $("relayMore").addEventListener("click", () => {
    state.relayAll = !state.relayAll;
    $("relayMore").textContent = state.relayAll ? "최근 12일" : "전체 보기";
    renderRelay();
  });

  $("leaderRelay").addEventListener("click", (event) => {
    const row = event.target.closest(".relay-row");
    if (row?.dataset.date) setDate(row.dataset.date);
  });

  $("overviewMovers").addEventListener("click", (event) => {
    const row = event.target.closest(".mini-row");
    if (row?.dataset.code) openDetail(row.dataset.code);
  });

  $("stockTable").querySelector("tbody").addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-code]");
    if (row) openDetail(row.dataset.code);
  });

  $("stockTable").querySelector("thead").addEventListener("click", (event) => {
    const th = event.target.closest("th[data-sort]");
    if (!th) return;
    const key = th.dataset.sort;
    if (state.sort.key === key) {
      state.sort.dir = state.sort.dir === "desc" ? "asc" : "desc";
    } else {
      state.sort.key = key;
      state.sort.dir = key === "name" || key === "grp" ? "asc" : "desc";
    }
    renderTable();
  });

  els.detailSelect.addEventListener("change", () => {
    openDetail(els.detailSelect.value);
  });

  $("changeList").addEventListener("click", (event) => {
    const row = event.target.closest(".change-row");
    if (row?.dataset.code) openDetail(row.dataset.code);
  });

  $("changeLeaders").addEventListener("click", (event) => {
    const row = event.target.closest(".leader-row");
    if (row?.dataset.code) openDetail(row.dataset.code);
  });

  window.addEventListener("resize", debounce(charts.resizeAll, 150));
}

/* ------------------------------------------------------------------ */
/* 데이터 로딩                                                          */
/* ------------------------------------------------------------------ */
function invalidate() {
  clearCaches();
  state.overview = null;
  state.universe = null;
  state.transitions = null;
  state.transitionsKey = null;
  state.detail = null;
}

async function refreshAll({ silent = false } = {}) {
  setLoading(true);
  try {
    const overview = await getOverview({
      window: state.window,
      threshold: state.threshold,
      lookback: state.lookback,
    });
    state.overview = overview;
    state.days = overview.days || [];
    if (!state.days.length) throw new Error("선택한 조건에 표시할 데이터가 없습니다.");
    if (!state.date || !state.days.some((day) => day.date === state.date)) {
      state.date = state.days[state.days.length - 1].date;
    }
    updateDateControls();
    renderAll();
    await loadUniverse();
    updateDateParts();
    if (state.tab === "influence") await renderInfluence();
    if (state.tab === "transitions") await renderTransitions();
    if (state.tab === "detail") await renderDetail();
    if (!silent) toast("최신 데이터로 다시 계산했습니다.", false, true);
  } catch (error) {
    console.error(error);
    toast(error.message, true);
  } finally {
    setLoading(false);
  }
}

async function loadUniverse() {
  if (!state.date) return;
  try {
    state.universe = await getUniverse({
      window: state.window,
      threshold: state.threshold,
      lookback: state.lookback,
      date: state.date,
    });
    populateDetailSelect();
  } catch (error) {
    console.error(error);
    state.universe = null;
    toast(`종목 데이터를 불러오지 못했습니다: ${error.message}`, true);
  }
}

async function loadTransitions() {
  const key = `${state.window}|${state.threshold}|${state.lookback}|${state.date}`;
  if (state.transitions && state.transitionsKey === key) return state.transitions;
  state.transitions = await getTransitions({
    window: state.window,
    threshold: state.threshold,
    lookback: state.lookback,
    date: state.date,
  });
  state.transitionsKey = key;
  return state.transitions;
}

/* ------------------------------------------------------------------ */
/* 날짜                                                                */
/* ------------------------------------------------------------------ */
function updateDateControls() {
  const index = Math.max(0, state.days.findIndex((day) => day.date === state.date));
  els.dateSlider.min = "0";
  els.dateSlider.max = String(Math.max(0, state.days.length - 1));
  els.dateSlider.value = String(index);
  els.dateLabel.textContent = fmtDateLong(state.date);
  $("prevDate").disabled = index <= 0;
  $("nextDate").disabled = index >= state.days.length - 1;
}

function onSliderMove(commit) {
  const index = Number(els.dateSlider.value);
  const day = state.days[index];
  if (!day) return;
  state.date = day.date;
  updateDateControls();
  renderKpis(day);
  charts.renderGroupTrend($("chartGroups"), state.days, state.date);
  renderRelay();
  scheduleDateLoad(commit);
}

const scheduleDateLoad = debounce(async () => {
  setLoading(true);
  try {
    await loadUniverse();
    updateDateParts();
    if (state.tab === "influence") await renderInfluence();
    if (state.tab === "transitions") await renderTransitions();
    if (state.tab === "detail") await renderDetail();
  } catch (error) {
    console.error(error);
    toast(error.message, true);
  } finally {
    setLoading(false);
  }
}, 160);

function setDate(date) {
  if (!date || date === state.date) return;
  state.date = date;
  updateDateControls();
  const day = currentDay();
  if (day) renderKpis(day);
  charts.renderGroupTrend($("chartGroups"), state.days, state.date);
  renderRelay();
  scheduleDateLoad(true);
}

function stepDate(step) {
  const index = state.days.findIndex((day) => day.date === state.date);
  const next = clamp(index + step, 0, state.days.length - 1);
  if (state.days[next]) setDate(state.days[next].date);
}

function currentDay() {
  return state.days.find((day) => day.date === state.date) || state.days[state.days.length - 1];
}

/* ------------------------------------------------------------------ */
/* 렌더링: 개요                                                        */
/* ------------------------------------------------------------------ */
function renderAll() {
  renderKpis(currentDay());
  charts.renderGroupTrend($("chartGroups"), state.days, state.date);
  charts.renderInternals($("chartInternals"), state.days);
  renderRelay();
}

function updateDateParts() {
  const day = currentDay();
  if (day) renderKpis(day);
  charts.renderGroupTrend($("chartGroups"), state.days, state.date);
  renderRelay();
  renderContribChart();
  renderMovers();
}

function renderKpis(day) {
  if (!day) return;
  $("kpiDate").textContent = fmtDateShort(day.date);
  const bench = $("kpiBenchRet");
  bench.textContent = fmtPct(day.bench_ret, 2);
  bench.className = `kpi-value ${signClass(day.bench_ret)}`;
  $("kpiBenchClose").textContent = day.bench_close ? `${fmtNum(day.bench_close)}원` : "–";
  $("kpiUniverseRet").textContent =
    day.universe_ret === null || day.universe_ret === undefined
      ? ""
      : `200종합 ${fmtPct(day.universe_ret, 2)}`;
  $("kpiBenchBar").style.width = `${clamp(Math.abs(day.bench_ret || 0) * 32, 3, 100)}%`;
  $("kpiBenchBar").style.background = (day.bench_ret || 0) >= 0 ? "var(--up)" : "var(--down)";

  const total = day.up + day.flat + day.down || 1;
  const upShare = (100 * day.up) / total;
  const flatShare = (100 * day.flat) / total;
  const downShare = (100 * day.down) / total;
  $("kpiUp").textContent = fmtNum(day.up);
  $("kpiFlat").textContent = fmtNum(day.flat);
  $("kpiDown").textContent = fmtNum(day.down);
  $("kpiUpShare").textContent = `${upShare.toFixed(1)}%`;
  $("kpiFlatShare").textContent = `${flatShare.toFixed(1)}%`;
  $("kpiDownShare").textContent = `${downShare.toFixed(1)}%`;
  $("kpiUpBar").style.width = `${upShare}%`;
  $("kpiFlatBar").style.width = `${flatShare}%`;
  $("kpiDownBar").style.width = `${downShare}%`;

  $("kpiBreadth").textContent = fmtPct(day.breadth, 1, false);
  $("kpiBreadthSub").textContent =
    day.net === null || day.net === undefined
      ? ""
      : `상향-하향 ${day.net > 0 ? "+" : ""}${day.net}`;
  $("kpiBreadthBar").style.width = `${clamp(day.breadth || 0, 0, 100)}%`;
  $("kpiBreadthBar").style.background = (day.breadth || 0) >= 50 ? "var(--up)" : "var(--flat)";

  $("kpiInflow").textContent = fmtPct(day.inflow, 1, false);
  $("kpiInflowSub").textContent =
    day.top5_share === null || day.top5_share === undefined
      ? ""
      : `상위 5종목 ${day.top5_share.toFixed(1)}%`;
  $("kpiInflowShare").textContent = `${fmtNum(day.turnover)}억`;
  $("kpiInflowBar").style.width = `${clamp(day.inflow || 0, 0, 100)}%`;

  $("contribDate").textContent = fmtDateShort(day.date);
}

function renderRelay() {
  const container = $("leaderRelay");
  const index = state.days.findIndex((day) => day.date === state.date);
  const end = index >= 0 ? index + 1 : state.days.length;
  const start = state.relayAll ? Math.max(0, end - 60) : Math.max(0, end - 12);
  const subset = state.days.slice(start, end).reverse();
  if (!subset.length) {
    container.innerHTML = `<div class="empty">표시할 주도주 기록이 없습니다.</div>`;
    return;
  }
  container.innerHTML = subset
    .map((day) => {
      const first = day.leaders?.[0];
      if (!first) return "";
      const others = (day.leaders || [])
        .slice(1, 3)
        .map((item) => `${esc(item.name)} ${fmtPp(item.contrib, 2)}`)
        .join(" · ");
      return `
        <div class="relay-row ${day.date === state.date ? "selected" : ""}" data-date="${day.date}">
          <span class="relay-date">${fmtDateShort(day.date)}</span>
          <span class="relay-names">
            <span class="relay-name">${esc(first.name)}</span>
            <span class="relay-second">${others || "&nbsp;"}</span>
          </span>
          <span class="relay-contrib ${signClass(first.contrib)}">${fmtPp(first.contrib, 2)}</span>
          <span class="relay-group ${first.grp ? `grp-${first.grp}` : "grp-F"}">${GROUP_LABEL[first.grp] || "–"}</span>
        </div>`;
    })
    .join("");
}

function renderContribChart() {
  const rows = state.universe?.rows || [];
  if (!rows.length) return;
  charts.renderContribBar($("chartContrib"), rows, state.date);
  $("contribDate").textContent = fmtDateShort(state.date);
}

function renderMovers() {
  const container = $("overviewMovers");
  const rows = state.universe?.rows || [];
  if (!rows.length) {
    container.innerHTML = `<div class="empty">종목 데이터를 불러오는 중입니다.</div>`;
    $("moversCount").textContent = "–";
    return;
  }
  const changed = rows
    .filter((row) => row.prev_grp && row.grp && row.prev_grp !== row.grp)
    .sort((a, b) => Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0));
  $("moversCount").textContent = `${changed.length}종목`;
  if (!changed.length) {
    container.innerHTML = `<div class="empty">이 날은 그룹이 바뀐 종목이 없습니다.</div>`;
    return;
  }
  container.innerHTML = changed
    .slice(0, 10)
    .map(
      (row) => `
      <div class="mini-row" data-code="${row.code}">
        <span class="mini-name">${esc(row.name)}</span>
        <span class="mini-arrow">→</span>
        <span class="grp-${row.prev_grp}">${GROUP_LABEL[row.prev_grp]}</span>
        <span class="mini-arrow">→</span>
        <span class="grp-${row.grp}">${GROUP_LABEL[row.grp]}</span>
        <span class="mini-spacer"></span>
        <span class="mini-meta">z ${fmtZ(row.z)}</span>
        <span class="mini-val ${signClass(row.ret)}">${fmtPct(row.ret, 1)}</span>
      </div>`
    )
    .join("");
}

/* ------------------------------------------------------------------ */
/* 렌더링: 영향력                                                      */
/* ------------------------------------------------------------------ */
function filteredRows() {
  let rows = state.universe?.rows || [];
  if (state.group !== "ALL") rows = rows.filter((row) => row.grp === state.group);
  if (state.search) {
    rows = rows.filter(
      (row) =>
        row.name.toLowerCase().includes(state.search) ||
        row.code.includes(state.search)
    );
  }
  return rows;
}

function sortRows(rows) {
  const { key, dir } = state.sort;
  const factor = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    if (key === "name") return a.name.localeCompare(b.name, "ko") * factor;
    if (key === "grp") {
      return ((GROUP_ORDER[a.grp] ?? 9) - (GROUP_ORDER[b.grp] ?? 9)) * factor;
    }
    const av = a[key];
    const bv = b[key];
    const aMissing = av === null || av === undefined;
    const bMissing = bv === null || bv === undefined;
    if (aMissing && bMissing) return 0;
    if (aMissing) return 1;
    if (bMissing) return -1;
    return (Number(av) - Number(bv)) * factor;
  });
}

async function renderInfluence() {
  if (!state.universe) {
    try {
      await loadUniverse();
    } catch (error) {
      toast(error.message, true);
      return;
    }
  }
  const rows = filteredRows();
  charts.renderScatter($("chartScatter"), rows, state.threshold);
  charts.renderScoreBar($("chartScore"), rows);
  renderTable();
}

function renderTable() {
  const rows = sortRows(filteredRows());
  const tbody = els.stockTable.querySelector("tbody");
  $("tableCount").textContent = `${fmtNum(rows.length)} / ${fmtNum(
    state.universe?.rows.length ?? 0
  )}종목 · ${state.date}`;

  if (!rows.length) {
    tbody.innerHTML = `<tr><td colspan="14"><div class="empty">조건에 맞는 종목이 없습니다.</div></td></tr>`;
    updateSortHeaders();
    return;
  }

  tbody.innerHTML = rows
    .map((row, index) => {
      const score = Number.isFinite(row.score) ? row.score : null;
      const selected = row.code === state.detailCode ? "selected" : "";
      return `
        <tr data-code="${row.code}" class="${selected}">
          <td class="num muted">${index + 1}</td>
          <td><span class="stock-name">${esc(row.name)}</span><span class="stock-code">${row.code}</span></td>
          <td>${groupBadge(row.grp)}</td>
          <td class="num">${fmtPrice(row.close)}</td>
          <td class="num ${signClass(row.ret)}">${fmtPct(row.ret, 2)}</td>
          <td class="num ${signClass(row.rel)}">${fmtPct(row.rel, 2)}</td>
          <td class="num ${signClass(row.z)}">${fmtZ(row.z)}</td>
          <td class="num">${row.vr === null || row.vr === undefined ? "–" : `${row.vr.toFixed(2)}x`}</td>
          <td class="num">${fmtMcap(row.mcap)}</td>
          <td class="num">${row.weight === null || row.weight === undefined ? "–" : `${row.weight.toFixed(2)}%`}</td>
          <td class="num ${signClass(row.contrib)}">${fmtPp(row.contrib, 3)}</td>
          <td class="num">
            <span class="score-cell">
              <span class="score-track"><i style="width:${score ?? 0}%"></i></span>
              ${score === null ? "–" : score.toFixed(1)}
            </span>
          </td>
          <td class="num"><span class="streak-chip"><b>${row.changes ?? 0}</b>회</span></td>
          <td class="num"><span class="streak-chip"><b>${row.streak ?? 0}</b>일</span></td>
        </tr>`;
    })
    .join("");
  updateSortHeaders();
}

function updateSortHeaders() {
  els.stockTable.querySelectorAll("th[data-sort]").forEach((th) => {
    th.querySelector(".sort-mark")?.remove();
    th.classList.toggle("sorted", th.dataset.sort === state.sort.key);
    if (th.dataset.sort === state.sort.key) {
      const mark = document.createElement("span");
      mark.className = "sort-mark";
      mark.textContent = state.sort.dir === "desc" ? " ↓" : " ↑";
      th.appendChild(mark);
    }
  });
}

/* ------------------------------------------------------------------ */
/* 렌더링: 그룹 전환                                                    */
/* ------------------------------------------------------------------ */
async function renderTransitions() {
  if (!state.universe && state.date) {
    try {
      await loadUniverse();
    } catch (error) {
      toast(error.message, true);
    }
  }
  let payload = state.transitions;
  try {
    payload = await loadTransitions();
  } catch (error) {
    toast(error.message, true);
    return;
  }
  charts.renderMatrix($("chartMatrix"), payload.matrix, payload.matrix_labels);
  charts.renderTransDaily($("chartTransDaily"), payload.daily || []);
  if (payload.start && payload.end) {
    $("matrixSub").textContent = `${payload.start} ~ ${payload.end} · 창 ${state.window}일 · ±${state.threshold}σ`;
  }
  renderChangeList();
  renderChangeLeaders(payload.leaders || []);
}

function dayChanges() {
  const rows = state.universe?.rows || [];
  return rows
    .filter((row) => row.prev_grp && row.grp && row.prev_grp !== row.grp)
    .sort((a, b) => Math.abs(b.z ?? 0) - Math.abs(a.z ?? 0));
}

function renderChangeList() {
  const container = $("changeList");
  const changes = dayChanges();
  $("changeCount").textContent = `${changes.length}종목`;
  $("changeSub").textContent = `${fmtDateLong(state.date)} · 전일 대비 그룹 이동`;
  if (!changes.length) {
    container.innerHTML = `<div class="empty">이 날은 그룹이 바뀐 종목이 없습니다.</div>`;
    return;
  }
  container.innerHTML = changes
    .map(
      (row) => `
      <div class="change-row" data-code="${row.code}">
        <span class="change-transition">
          <span class="grp-${row.prev_grp}">${GROUP_LABEL[row.prev_grp]}</span>
          <span class="arrow-badge">→</span>
          <span class="grp-${row.grp}">${GROUP_LABEL[row.grp]}</span>
        </span>
        <span class="change-name">${esc(row.name)}</span>
        <span class="change-spacer"></span>
        <span class="change-meta">z ${fmtZ(row.z)} · ${fmtMcap(row.mcap)}</span>
        <span class="change-meta ${signClass(row.ret)}">${fmtPct(row.ret, 1)}</span>
      </div>`
    )
    .join("");
}

function renderChangeLeaders(leaders) {
  const container = $("changeLeaders");
  if (!leaders.length) {
    container.innerHTML = `<div class="empty">표시할 전환 이력이 없습니다.</div>`;
    return;
  }
  const max = Math.max(...leaders.map((row) => row.changes || 0), 1);
  container.innerHTML = leaders
    .slice(0, 25)
    .map(
      (row, index) => `
      <div class="leader-row" data-code="${row.code}">
        <span class="leader-rank">${index + 1}</span>
        <span class="leader-name">${esc(row.name)}</span>
        ${groupBadge(row.last_group)}
        <span class="leader-spacer"></span>
        <span class="leader-bar"><i style="width:${((row.changes || 0) / max) * 100}%"></i></span>
        <span class="leader-meta"><b>${row.changes ?? 0}</b>회</span>
        <span class="leader-meta">점수 ${row.score?.toFixed(0) ?? "–"}</span>
      </div>`
    )
    .join("");
}

/* ------------------------------------------------------------------ */
/* 렌더링: 종목 상세                                                    */
/* ------------------------------------------------------------------ */
function populateDetailSelect() {
  const rows = state.universe?.rows || [];
  if (!rows.length) return;
  const sorted = [...rows].sort((a, b) => (b.mcap ?? 0) - (a.mcap ?? 0));
  const current = state.detailCode || els.detailSelect.value;
  els.detailSelect.innerHTML = sorted
    .map(
      (row) =>
        `<option value="${row.code}">${esc(row.name)} · ${row.code}</option>`
    )
    .join("");
  if (current && sorted.some((row) => row.code === current)) {
    els.detailSelect.value = current;
  } else {
    els.detailSelect.value = sorted[0].code;
  }
}

async function openDetail(code) {
  if (!code) return;
  state.detailCode = code;
  els.detailSelect.value = code;
  await switchTab("detail");
}

async function renderDetail() {
  if (!state.detailCode) {
    const rows = state.universe?.rows || [];
    const best = [...rows].sort((a, b) => (b.score ?? 0) - (a.score ?? 0))[0];
    if (!best) {
      $("detailName").textContent = "종목 데이터를 불러오는 중입니다.";
      return;
    }
    state.detailCode = best.code;
  }
  els.detailSelect.value = state.detailCode;
  setLoading(true);
  try {
    const detail = await getStock(state.detailCode, {
      window: state.window,
      threshold: state.threshold,
      lookback: state.lookback,
      date: state.date,
    });
    state.detail = detail;
    drawDetail(detail);
    const row = els.stockTable.querySelector(`tr[data-code="${state.detailCode}"]`);
    if (row) row.classList.add("selected");
  } finally {
    setLoading(false);
  }
}

function drawDetail(detail) {
  const series = detail.series || [];
  const stats = detail.stats || {};
  const last = series[series.length - 1] || {};
  $("detailName").innerHTML = `${esc(detail.name)}
    <span style="color:#64748b;font-family:var(--mono);font-size:13px;font-weight:500">${detail.code}</span>
    ${detail.preferred ? '<span class="pill" style="margin-left:6px">우선주</span>' : ""}`;
  $("detailMeta").textContent = `시총 ${fmtMcap(stats.mcap)} · 비중 ${stats.weight?.toFixed(2) ?? "–"}% · ${fmtDateLong(
    state.date
  )} 기준`;

  const cards = [
    { label: "현재가", value: fmtPrice(last.close), cls: "" },
    { label: "당일 등락", value: fmtPct(last.ret, 2), cls: signClass(last.ret) },
    { label: "상대강도 z", value: fmtZ(last.z), cls: signClass(last.z) },
    { label: "영향력 점수", value: stats.score?.toFixed(1) ?? "–", cls: "" },
    { label: "누적 기여도", value: fmtPp(stats.cum_contrib, 2), cls: signClass(stats.cum_contrib) },
  ];
  $("detailKpis").innerHTML = cards
    .map(
      (card) => `<div class="detail-kpi"><span>${card.label}</span><b class="${card.cls}">${card.value}</b></div>`
    )
    .join("");

  charts.renderDetailPrice($("chartDetail"), series, state.threshold);
  charts.renderDetailContrib($("chartDetailContrib"), series);

  $("groupStrip").innerHTML = series
    .map(
      (row) =>
        `<span class="strip-cell ${row.grp || "N"}" title="${row.date} · ${
          GROUP_LABEL[row.grp] || "계산 전"
        } · z ${fmtZ(row.z)}"></span>`
    )
    .join("");

  const statCards = [
    { label: "상향 일수", value: `${stats.up ?? "–"}일` },
    { label: "횡보 일수", value: `${stats.flat ?? "–"}일` },
    { label: "하향 일수", value: `${stats.down ?? "–"}일` },
    { label: "평균 |z|", value: stats.avg_abs_z?.toFixed(2) ?? "–" },
    { label: "평균 거래량비", value: stats.avg_vr ? `${stats.avg_vr.toFixed(2)}x` : "–" },
    { label: "그룹 전환", value: `${stats.changes ?? 0}회` },
    { label: "현재 연속", value: `${stats.streak ?? 0}일` },
    { label: "평균 거래대금", value: fmtValue(stats.value) },
  ];
  $("detailStats").innerHTML = statCards
    .map(
      (card) => `<div class="detail-stat"><span>${card.label}</span><b>${card.value}</b></div>`
    )
    .join("");

  const chips = Object.entries(stats.transitions || {})
    .sort((a, b) => b[1] - a[1])
    .map(([key, value]) => {
      const [from, to] = key.split(">");
      return `<span class="chip">${GROUP_LABEL[from]}→${GROUP_LABEL[to]} <b>${value}</b></span>`;
    })
    .join("");
  $("detailStats").insertAdjacentHTML(
    "beforeend",
    chips ? `<div class="transition-chips" style="grid-column:1/-1">${chips}</div>` : ""
  );

  const events = stats.events || [];
  $("detailEvents").innerHTML = events.length
    ? [...events]
        .reverse()
        .map(
          (event) => `
          <div class="event-row">
            <span class="event-date">${event.date}</span>
            <span class="grp-${event.from}">${GROUP_LABEL[event.from]}</span>
            <span class="arrow-badge">→</span>
            <span class="grp-${event.to}">${GROUP_LABEL[event.to]}</span>
          </div>`
        )
        .join("")
    : `<div class="empty">선택 기간에 그룹 전환이 없습니다.</div>`;

  if (state.detail) {
    $("detailMeta").textContent += ` · ${series.length}거래일 표시`;
  }
}

/* ------------------------------------------------------------------ */
/* 탭                                                                  */
/* ------------------------------------------------------------------ */
const TAB_HINTS = {
  overview: "z = KODEX 200 대비 초과등락률 ÷ 롤링 표준편차",
  influence: "기여도 = 시총 비중 × 등락률 · 점수는 상대 순위",
  transitions: "전일 그룹 → 당일 그룹 이동 이력",
  detail: "종목별 시계열과 전환 타임라인",
};

async function switchTab(tab) {
  state.tab = tab;
  $("tabs").querySelectorAll("button[data-tab]").forEach((button) => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== `panel-${tab}`;
  });
  $("tabHint").textContent = TAB_HINTS[tab] || "";
  requestAnimationFrame(() => charts.resizeAll());

  try {
    if (tab === "influence") {
      if (!state.universe) await loadUniverse();
      await renderInfluence();
    } else if (tab === "transitions") {
      if (!state.universe) await loadUniverse();
      await renderTransitions();
    } else if (tab === "detail") {
      if (!state.universe) await loadUniverse();
      await renderDetail();
    }
  } catch (error) {
    console.error(error);
    toast(error.message, true);
  }
}

/* ------------------------------------------------------------------ */
/* 보조                                                                */
/* ------------------------------------------------------------------ */
function updateThresholdLabels() {
  document.querySelectorAll(".threshold-label").forEach((node) => {
    node.textContent = Number(state.threshold).toFixed(1).replace(/\.0$/, "");
  });
  $("footWindow").textContent = state.window;
  $("footThreshold").textContent = state.threshold;
}

function exportCsv() {
  const rows = sortRows(filteredRows());
  if (!rows.length) {
    toast("내보낼 종목이 없습니다.", true);
    return;
  }
  const columns = [
    { key: "code", label: "종목코드" },
    { key: "name", label: "종목명" },
    { key: "grp", label: "그룹" },
    { key: "close", label: "종가" },
    { key: "ret", label: "등락률(%)" },
    { key: "rel", label: "상대등락(%p)" },
    { key: "z", label: "상대강도z" },
    { key: "vr", label: "거래량비" },
    { key: "mcap", label: "시가총액(조원)" },
    { key: "weight", label: "시총비중(%)" },
    { key: "contrib", label: "지수기여도(%p)" },
    { key: "value", label: "거래대금(억원)" },
    { key: "beta", label: "베타" },
    { key: "score", label: "영향력점수" },
    { key: "changes", label: "그룹전환횟수" },
    { key: "streak", label: "현재연속일" },
  ];
  const payload = rows.map((row) => ({ ...row, grp: GROUP_LABEL[row.grp] || row.grp }));
  downloadCsv(`kospi_${state.date}_${state.group}.csv`, payload, columns);
  toast(`${rows.length}종목을 CSV로 저장했습니다.`, false, true);
}

function setLoading(on) {
  state.loadingCount = Math.max(0, state.loadingCount + (on ? 1 : -1));
  $("loading").classList.toggle("hidden", state.loadingCount === 0);
}

let toastTimer = null;
function toast(message, isError = false, ok = false) {
  const node = $("toast");
  node.textContent = message;
  node.classList.toggle("ok", ok && !isError);
  node.classList.add("show");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => node.classList.remove("show"), isError ? 5200 : 2600);
}

window.addEventListener("error", (event) => {
  if (event.message) console.error(event.message);
});

main();
