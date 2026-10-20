import {
  fmtPct,
  fmtZ,
  fmtPp,
  fmtMcap,
  fmtValue,
  fmtDateShort,
  fmtNum,
  GROUP_COLOR,
  GROUP_LABEL,
} from "./utils.js";

const UP = "#22c55e";
const FLAT = "#94a3b8";
const DOWN = "#f43f5e";
const ACCENT = "#38bdf8";
const VIOLET = "#a78bfa";
const AMBER = "#fbbf24";
const TEXT = "#94a3b8";
const DIM = "#64748b";
const GRID = "#1e293b";
const FG = "#dbe6f5";

const FONT =
  '-apple-system, BlinkMacSystemFont, "Segoe UI", "Malgun Gothic", "Noto Sans KR", sans-serif';

const tooltipBase = {
  backgroundColor: "rgba(8, 13, 26, 0.96)",
  borderColor: "#273449",
  borderWidth: 1,
  padding: [10, 12],
  textStyle: { color: FG, fontSize: 12, fontFamily: FONT },
  extraCssText:
    "box-shadow:0 14px 44px rgba(0,0,0,.5);border-radius:10px;backdrop-filter:blur(6px);",
};

const chartRegistry = new Set();

function getChart(el) {
  if (!window.echarts) throw new Error("ECharts를 불러오지 못했습니다.");
  let instance = window.echarts.getInstanceByDom(el);
  if (!instance) {
    instance = window.echarts.init(el, null, { renderer: "canvas" });
    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(() => instance.resize());
      observer.observe(el);
    }
    chartRegistry.add(instance);
  }
  return instance;
}

export function resizeAll() {
  chartRegistry.forEach((chart) => {
    try {
      chart.resize();
    } catch {
      /* disposed */
    }
  });
}

function categoryAxis(data, formatter = (value) => value) {
  return {
    type: "category",
    data,
    boundaryGap: true,
    axisLine: { lineStyle: { color: GRID } },
    axisTick: { show: false },
    axisLabel: { color: DIM, fontSize: 10.5, fontFamily: FONT, formatter },
    splitLine: { show: false },
  };
}

function valueAxis(extra = {}) {
  return {
    type: "value",
    axisLine: { show: false },
    axisTick: { show: false },
    axisLabel: { color: DIM, fontSize: 10.5, fontFamily: FONT },
    splitLine: { lineStyle: { color: "rgba(30,41,59,.65)" } },
    ...extra,
  };
}

function pctLabel(value) {
  return `${Math.round(value)}%`;
}

function benchCumulative(days) {
  const values = [];
  let base = null;
  for (const day of days) {
    if (day.bench_close) {
      if (base === null) base = day.bench_close;
      values.push((day.bench_close / base - 1) * 100);
    } else {
      values.push(null);
    }
  }
  return values;
}

/* ------------------------------------------------------------------ */
export function renderGroupTrend(el, days, selectedDate) {
  const chart = getChart(el);
  const dates = days.map((d) => d.date);
  const bench = benchCumulative(days);
  const lineCommon = { symbol: "none", smooth: 0.22, showSymbol: false };
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 44, right: 58, top: 18, bottom: 34 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "#475569", type: "dashed" } },
      ...tooltipBase,
      formatter(params) {
        const index = params[0]?.dataIndex ?? 0;
        const day = days[index];
        if (!day) return "";
        const total = day.up + day.flat + day.down;
        return `
          <div style="font-weight:700;margin-bottom:6px;color:#f1f5f9">${day.date}</div>
          <div style="display:grid;grid-template-columns:auto auto;gap:2px 16px;font-size:11.5px">
            <span><i style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${UP};margin-right:5px"></i>상향</span><b style="text-align:right">${day.up}</b>
            <span><i style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${FLAT};margin-right:5px"></i>횡보</span><b style="text-align:right">${day.flat}</b>
            <span><i style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${DOWN};margin-right:5px"></i>하향</span><b style="text-align:right">${day.down}</b>
            <span style="color:#94a3b8">KODEX 200</span><b style="text-align:right;color:#7dd3fc">${fmtPct(day.bench_ret, 2)}</b>
            <span style="color:#94a3b8">상승 비율</span><b style="text-align:right">${fmtPct(day.breadth, 1, false)}</b>
            <span style="color:#94a3b8">유효 종목</span><b style="text-align:right">${total}</b>
          </div>`;
      },
    },
    xAxis: categoryAxis(dates, (value) => fmtDateShort(value)),
    yAxis: [
      valueAxis({
        name: "종목 수",
        nameTextStyle: { color: DIM, fontSize: 10, padding: [0, 0, 4, 0] },
        minInterval: 10,
        max: (value) => Math.ceil((value.max + 20) / 50) * 50,
      }),
      valueAxis({
        name: "누적",
        nameTextStyle: { color: DIM, fontSize: 10 },
        splitLine: { show: false },
        axisLabel: { color: DIM, fontSize: 10.5, formatter: pctLabel },
      }),
    ],
    series: [
      {
        name: "상향",
        type: "line",
        stack: "group",
        ...lineCommon,
        data: days.map((d) => d.up),
        lineStyle: { width: 1.6, color: UP },
        itemStyle: { color: UP },
        areaStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(34,197,94,.42)" },
            { offset: 1, color: "rgba(34,197,94,.03)" },
          ]),
        },
        emphasis: { focus: "series" },
      },
      {
        name: "횡보",
        type: "line",
        stack: "group",
        ...lineCommon,
        data: days.map((d) => d.flat),
        lineStyle: { width: 1.2, color: FLAT },
        itemStyle: { color: FLAT },
        areaStyle: { color: "rgba(148,163,184,.16)" },
        emphasis: { focus: "series" },
      },
      {
        name: "하향",
        type: "line",
        stack: "group",
        ...lineCommon,
        data: days.map((d) => d.down),
        lineStyle: { width: 1.6, color: DOWN },
        itemStyle: { color: DOWN },
        areaStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(244,63,94,.4)" },
            { offset: 1, color: "rgba(244,63,94,.03)" },
          ]),
        },
        emphasis: { focus: "series" },
      },
      {
        name: "KODEX 200",
        type: "line",
        yAxisIndex: 1,
        symbol: "none",
        smooth: 0.18,
        data: bench,
        lineStyle: { width: 1.8, color: ACCENT },
        itemStyle: { color: ACCENT },
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: ACCENT, type: "dashed", opacity: 0.55 },
          data: selectedDate ? [{ xAxis: selectedDate }] : [],
        },
      },
    ],
  };
  chart.setOption(option, true);
}

/* ------------------------------------------------------------------ */
export function renderContribBar(el, rows, date) {
  const chart = getChart(el);
  const picked = [...rows]
    .filter((row) => Number.isFinite(row.contrib))
    .sort((a, b) => Math.abs(b.contrib) - Math.abs(a.contrib))
    .slice(0, 12)
    .sort((a, b) => (a.contrib ?? 0) - (b.contrib ?? 0));
  const names = picked.map((row) => row.name);
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 98, right: 62, top: 8, bottom: 24 },
    tooltip: {
      trigger: "item",
      ...tooltipBase,
      formatter(param) {
        const row = picked[param.dataIndex];
        if (!row) return "";
        return `
          <div style="font-weight:700;margin-bottom:5px">${row.name} <span style="color:#64748b;font-size:11px">${row.code}</span></div>
          <div style="font-size:11.5px;line-height:1.7">
            그룹 <b style="color:${GROUP_COLOR[row.grp] || FLAT}">${GROUP_LABEL[row.grp] || "–"}</b> · z ${fmtZ(row.z)}<br>
            기여도 <b>${fmtPp(row.contrib, 3)}</b><br>
            비중 ${row.weight?.toFixed(2)}% · 시총 ${fmtMcap(row.mcap)}
          </div>`;
      },
    },
    xAxis: valueAxis({
      axisLabel: { color: DIM, fontSize: 10, formatter: (value) => `${value}` },
      splitLine: { lineStyle: { color: "rgba(30,41,59,.6)" } },
    }),
    yAxis: {
      type: "category",
      data: names,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: TEXT, fontSize: 11, fontFamily: FONT },
    },
    series: [
      {
        type: "bar",
        data: picked.map((row) => ({
          value: row.contrib,
          itemStyle: {
            color: row.contrib >= 0 ? UP : DOWN,
            borderRadius: row.contrib >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4],
            opacity: 0.85,
          },
        })),
        barWidth: 13,
        label: {
          show: true,
          position: "right",
          color: TEXT,
          fontSize: 10,
          fontFamily: FONT,
          formatter: (param) => (param.value > 0 ? "+" : "") + Number(param.value).toFixed(2),
        },
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: "#475569", width: 1 },
          data: [{ xAxis: 0 }],
        },
      },
    ],
  };
  chart.setOption(option, true);
  return { count: picked.length, date };
}

/* ------------------------------------------------------------------ */
export function renderScatter(el, rows, threshold) {
  const chart = getChart(el);
  const maxMcap = Math.max(...rows.map((r) => r.mcap || 0), 1);
  const size = (mcap) => {
    const base = Math.sqrt(Math.max(0, mcap || 0) / maxMcap);
    return 4 + base * 20;
  };
  const groups = ["U", "F", "D"];
  const series = groups.map((group) => ({
    name: GROUP_LABEL[group],
    type: "scatter",
    data: rows
      .filter((row) => row.grp === group && Number.isFinite(row.z) && Number.isFinite(row.vr))
      .map((row) => ({
        value: [Math.max(-4.5, Math.min(4.5, row.z)), Math.max(0, Math.min(4.5, row.vr))],
        name: row.name,
        code: row.code,
        z: row.z,
        vr: row.vr,
        contrib: row.contrib,
        mcap: row.mcap,
        score: row.score,
        grp: row.grp,
        symbolSize: size(row.mcap),
      })),
    itemStyle: { color: GROUP_COLOR[group], opacity: 0.75 },
    emphasis: { focus: "series", itemStyle: { opacity: 1 } },
  }));

  const topLabels = [...rows]
    .filter((row) => Number.isFinite(row.z) && Number.isFinite(row.vr))
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0))
    .slice(0, 8);
  series.push({
    name: "label",
    type: "scatter",
    symbolSize: 1,
    itemStyle: { color: "transparent" },
    label: {
      show: true,
      position: "right",
      color: "#cbd5e1",
      fontSize: 10,
      fontFamily: FONT,
      formatter: (param) => param.data.name,
    },
    data: topLabels.map((row) => ({
      value: [Math.max(-4.5, Math.min(4.5, row.z)), Math.max(0, Math.min(4.5, row.vr))],
      name: row.name,
    })),
    tooltip: { show: false },
    silent: true,
    z: 10,
  });

  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 48, right: 20, top: 40, bottom: 42 },
    legend: {
      top: 0,
      right: 4,
      itemWidth: 8,
      itemHeight: 8,
      icon: "circle",
      textStyle: { color: TEXT, fontSize: 11, fontFamily: FONT },
      data: ["상향", "횡보", "하향"],
    },
    tooltip: {
      trigger: "item",
      ...tooltipBase,
      formatter(param) {
        const row = param.data;
        if (!row || !row.code) return "";
        return `
          <div style="font-weight:700;margin-bottom:5px">${row.name} <span style="color:#64748b;font-size:11px">${row.code}</span></div>
          <div style="font-size:11.5px;line-height:1.7">
            상대강도 z <b>${fmtZ(row.z)}</b> · 거래량비 <b>${row.vr?.toFixed(2)}x</b><br>
            기여도 <b>${fmtPp(row.contrib, 2)}</b> · 시총 ${fmtMcap(row.mcap)}<br>
            영향력 점수 <b>${row.score?.toFixed(1) ?? "–"}</b>
          </div>`;
      },
    },
    xAxis: valueAxis({
      name: "상대강도 z",
      nameLocation: "middle",
      nameGap: 26,
      nameTextStyle: { color: DIM, fontSize: 10 },
      min: -4.5,
      max: 4.5,
      splitLine: { lineStyle: { color: "rgba(30,41,59,.55)" } },
      axisLabel: { color: DIM, fontSize: 10, formatter: (value) => value.toFixed(0) },
    }),
    yAxis: valueAxis({
      name: "거래량비",
      nameTextStyle: { color: DIM, fontSize: 10 },
      min: 0,
      max: 4.5,
      splitLine: { lineStyle: { color: "rgba(30,41,59,.55)" } },
      axisLabel: { color: DIM, fontSize: 10, formatter: (value) => `${value}x` },
    }),
    series,
  };

  option.series[0].markLine = {
    silent: true,
    symbol: "none",
    label: { color: DIM, fontSize: 9, fontFamily: FONT },
    lineStyle: { color: "rgba(148,163,184,.35)", type: "dashed", width: 1 },
    data: [
      { xAxis: threshold, label: { formatter: `+${threshold}σ` } },
      { xAxis: -threshold, label: { formatter: `-${threshold}σ` } },
      { yAxis: 1, label: { formatter: "거래량 1x" } },
    ],
  };
  chart.setOption(option, true);
}

/* ------------------------------------------------------------------ */
export function renderScoreBar(el, rows) {
  const chart = getChart(el);
  const picked = [...rows]
    .filter((row) => Number.isFinite(row.score) && row.score_parts)
    .sort((a, b) => b.score - a.score)
    .slice(0, 15)
    .sort((a, b) => a.score - b.score);
  const parts = [
    { key: "contrib", name: "기여도 50%", color: ACCENT, weight: 0.5 },
    { key: "turnover", name: "거래대금 30%", color: AMBER, weight: 0.3 },
    { key: "mcap", name: "시총 20%", color: VIOLET, weight: 0.2 },
  ];
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 100, right: 46, top: 34, bottom: 26 },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 8,
      itemHeight: 8,
      icon: "roundRect",
      textStyle: { color: TEXT, fontSize: 10.5, fontFamily: FONT },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(148,163,184,.06)" } },
      ...tooltipBase,
      formatter(params) {
        const idx = params[0]?.dataIndex ?? 0;
        const row = picked[idx];
        if (!row) return "";
        const p = row.score_parts;
        return `
          <div style="font-weight:700;margin-bottom:5px">${row.name}</div>
          <div style="font-size:11.5px;line-height:1.75">
            기여도 ${p.contrib.toFixed(1)} × 0.5 = <b>${(p.contrib * 0.5).toFixed(1)}</b><br>
            거래대금 ${p.turnover.toFixed(1)} × 0.3 = <b>${(p.turnover * 0.3).toFixed(1)}</b><br>
            시총 ${p.mcap.toFixed(1)} × 0.2 = <b>${(p.mcap * 0.2).toFixed(1)}</b><br>
            <span style="color:#7dd3fc">합계 ${row.score.toFixed(1)}</span>
          </div>`;
      },
    },
    xAxis: valueAxis({ max: 100, axisLabel: { color: DIM, fontSize: 10 } }),
    yAxis: {
      type: "category",
      data: picked.map((row) => row.name),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: TEXT, fontSize: 11, fontFamily: FONT },
    },
    series: parts.map((part, index) => ({
      name: part.name,
      type: "bar",
      stack: "score",
      barWidth: 12,
      data: picked.map((row) => ({
        value: (row.score_parts[part.key] ?? 0) * part.weight,
        score: row.score,
      })),
      itemStyle: {
        color: part.color,
        borderRadius:
          index === parts.length - 1 ? [0, 4, 4, 0] : [0, 0, 0, 0],
        opacity: 0.88,
      },
      label:
        index === parts.length - 1
          ? {
              show: true,
              position: "right",
              color: "#cbd5e1",
              fontSize: 10,
              fontFamily: FONT,
              formatter: (param) => param.data.score?.toFixed(0) ?? "",
            }
          : { show: false },
    })),
  };
  chart.setOption(option, true);
}

/* ------------------------------------------------------------------ */
export function renderInternals(el, days) {
  const chart = getChart(el);
  const dates = days.map((d) => d.date);
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 40, right: 18, top: 26, bottom: 28 },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 12,
      itemHeight: 2,
      textStyle: { color: TEXT, fontSize: 10.5, fontFamily: FONT },
    },
    tooltip: {
      trigger: "axis",
      ...tooltipBase,
      formatter(params) {
        const day = days[params[0]?.dataIndex ?? 0];
        if (!day) return "";
        return `
          <div style="font-weight:700;margin-bottom:4px">${day.date}</div>
          <div style="font-size:11.5px;line-height:1.7">
            상승 비율 <b>${fmtPct(day.breadth, 1, false)}</b><br>
            거래대금 유입 <b>${fmtPct(day.inflow, 1, false)}</b><br>
            KODEX 200 <b>${fmtPct(day.bench_ret, 2)}</b><br>
            상위 5종목 집중도 <b>${fmtPct(day.top5_share, 1, false)}</b>
          </div>`;
      },
    },
    xAxis: categoryAxis(dates, (value) => fmtDateShort(value)),
    yAxis: valueAxis({
      min: 0,
      max: 100,
      axisLabel: { color: DIM, fontSize: 10, formatter: (value) => `${value}%` },
    }),
    series: [
      {
        name: "상승 비율",
        type: "line",
        symbol: "none",
        smooth: 0.25,
        data: days.map((d) => d.breadth),
        lineStyle: { width: 1.8, color: ACCENT },
        itemStyle: { color: ACCENT },
        areaStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(56,189,248,.25)" },
            { offset: 1, color: "rgba(56,189,248,.01)" },
          ]),
        },
        markLine: {
          silent: true,
          symbol: "none",
          label: { color: DIM, fontSize: 9, formatter: "50%" },
          lineStyle: { color: "rgba(148,163,184,.3)", type: "dashed" },
          data: [{ yAxis: 50 }],
        },
      },
      {
        name: "거래대금 유입",
        type: "line",
        symbol: "none",
        smooth: 0.25,
        data: days.map((d) => d.inflow),
        lineStyle: { width: 1.5, color: VIOLET },
        itemStyle: { color: VIOLET },
      },
    ],
  };
  chart.setOption(option, true);
}

/* ------------------------------------------------------------------ */
export function renderMatrix(el, matrix, labels) {
  const chart = getChart(el);
  const data = [];
  let max = 1;
  matrix.forEach((row, from) => {
    row.forEach((value, to) => {
      data.push([to, from, value]);
      max = Math.max(max, value);
    });
  });
  const rowTotals = matrix.map((row) => row.reduce((a, b) => a + b, 0) || 1);
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 58, right: 22, top: 18, bottom: 42 },
    tooltip: {
      trigger: "item",
      ...tooltipBase,
      formatter(param) {
        const [to, from, value] = param.data;
        return `<b>${labels[from]} → ${labels[to]}</b><br>
          <span style="font-size:11.5px">${fmtNum(value)}건 · 행 기준 ${((value / rowTotals[from]) * 100).toFixed(1)}%</span>`;
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      position: "bottom",
      axisLine: { lineStyle: { color: GRID } },
      axisTick: { show: false },
      axisLabel: { color: TEXT, fontSize: 11, fontFamily: FONT },
      splitLine: { show: false },
    },
    yAxis: {
      type: "category",
      data: labels,
      inverse: true,
      axisLine: { lineStyle: { color: GRID } },
      axisTick: { show: false },
      axisLabel: { color: TEXT, fontSize: 11, fontFamily: FONT },
    },
    visualMap: {
      show: false,
      min: 0,
      max,
      inRange: { color: ["#0d1729", "#10465c", "#0e7490", "#38bdf8"] },
    },
    series: [
      {
        type: "heatmap",
        data,
        label: {
          show: true,
          color: "#e2e8f0",
          fontSize: 12,
          fontFamily: FONT,
          formatter: (param) => fmtNum(param.data[2]),
        },
        itemStyle: { borderColor: "#0b1120", borderWidth: 2, borderRadius: 6 },
        emphasis: { itemStyle: { shadowBlur: 12, shadowColor: "rgba(56,189,248,.4)" } },
      },
    ],
  };
  chart.setOption(option, true);
}

/* ------------------------------------------------------------------ */
export function renderTransDaily(el, daily) {
  const chart = getChart(el);
  const dates = daily.map((row) => row.date);
  const up = daily.map(
    (row) => (row.counts["F>U"] || 0) + (row.counts["D>U"] || 0) + (row.counts["D>F"] || 0)
  );
  const down = daily.map(
    (row) => (row.counts["U>F"] || 0) + (row.counts["U>D"] || 0) + (row.counts["F>D"] || 0)
  );
  const net = up.map((value, index) => value - down[index]);
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 40, right: 44, top: 30, bottom: 30 },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 9,
      itemHeight: 9,
      icon: "roundRect",
      textStyle: { color: TEXT, fontSize: 10.5, fontFamily: FONT },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(148,163,184,.06)" } },
      ...tooltipBase,
      formatter(params) {
        const index = params[0]?.dataIndex ?? 0;
        const row = daily[index];
        if (!row) return "";
        const parts = Object.entries(row.counts || {})
          .filter(([, value]) => value > 0)
          .map(([key, value]) => {
            const [from, to] = key.split(">");
            return `<span style="color:#94a3b8">${GROUP_LABEL[from]}→${GROUP_LABEL[to]}</span><b style="float:right;margin-left:12px">${value}</b>`;
          })
          .join("<br>");
        return `<div style="font-weight:700;margin-bottom:5px">${row.date}</div>
          <div style="font-size:11.5px;line-height:1.65;min-width:170px">${parts}</div>`;
      },
    },
    xAxis: categoryAxis(dates, (value) => fmtDateShort(value)),
    yAxis: [
      valueAxis({ minInterval: 5 }),
      valueAxis({
        splitLine: { show: false },
        axisLabel: { color: DIM, fontSize: 10, formatter: (value) => `${value}` },
      }),
    ],
    series: [
      {
        name: "상향 전환",
        type: "bar",
        stack: "change",
        data: up,
        barMaxWidth: 9,
        itemStyle: { color: "rgba(34,197,94,.75)", borderRadius: [3, 3, 0, 0] },
      },
      {
        name: "하향 전환",
        type: "bar",
        stack: "change",
        data: down.map((value) => -value),
        barMaxWidth: 9,
        itemStyle: { color: "rgba(244,63,94,.75)", borderRadius: [0, 0, 3, 3] },
      },
      {
        name: "순 전환",
        type: "line",
        yAxisIndex: 1,
        data: net,
        symbol: "none",
        smooth: 0.2,
        lineStyle: { width: 1.5, color: AMBER },
        itemStyle: { color: AMBER },
      },
    ],
  };
  chart.setOption(option, true);
}

/* ------------------------------------------------------------------ */
export function renderDetailPrice(el, series, threshold) {
  const chart = getChart(el);
  const dates = series.map((row) => row.date);
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 62, right: 50, top: 22, bottom: 30 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "line", lineStyle: { color: "#475569", type: "dashed" } },
      ...tooltipBase,
      formatter(params) {
        const row = series[params[0]?.dataIndex ?? 0];
        if (!row) return "";
        return `
          <div style="font-weight:700;margin-bottom:5px">${row.date}</div>
          <div style="font-size:11.5px;line-height:1.75">
            종가 <b>${fmtNum(row.close)}</b> · 등락 <b style="color:${(row.ret || 0) >= 0 ? UP : DOWN}">${fmtPct(row.ret, 2)}</b><br>
            z <b>${fmtZ(row.z)}</b> · 그룹 <b style="color:${GROUP_COLOR[row.grp] || FLAT}">${GROUP_LABEL[row.grp] || "–"}</b><br>
            거래량비 ${row.vr?.toFixed(2) ?? "–"}x · 기여도 ${fmtPp(row.contrib, 3)}
          </div>`;
      },
    },
    xAxis: categoryAxis(dates, (value) => fmtDateShort(value)),
    yAxis: [
      valueAxis({
        scale: true,
        splitNumber: 4,
        axisLabel: { color: DIM, fontSize: 10, formatter: (value) => fmtNum(value) },
      }),
      valueAxis({
        min: -4,
        max: 4,
        splitLine: { show: false },
        axisLabel: { color: DIM, fontSize: 10, formatter: (value) => `${value}` },
      }),
    ],
    series: [
      {
        name: "종가",
        type: "line",
        data: series.map((row) => row.close),
        symbol: "none",
        smooth: 0.15,
        lineStyle: { width: 1.9, color: "#e2e8f0" },
        itemStyle: { color: "#e2e8f0" },
        areaStyle: {
          color: new window.echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: "rgba(226,232,240,.16)" },
            { offset: 1, color: "rgba(226,232,240,.01)" },
          ]),
        },
      },
      {
        name: "z",
        type: "line",
        yAxisIndex: 1,
        data: series.map((row) => row.z),
        symbol: "none",
        smooth: 0.15,
        lineStyle: { width: 1.5, color: ACCENT },
        itemStyle: { color: ACCENT },
        areaStyle: { color: "rgba(56,189,248,.12)" },
        markLine: {
          silent: true,
          symbol: "none",
          label: { color: DIM, fontSize: 9, fontFamily: FONT },
          data: [
            {
              yAxis: threshold,
              lineStyle: { color: "rgba(34,197,94,.55)", type: "dashed" },
              label: { formatter: `+${threshold}σ` },
            },
            {
              yAxis: -threshold,
              lineStyle: { color: "rgba(244,63,94,.55)", type: "dashed" },
              label: { formatter: `-${threshold}σ` },
            },
            { yAxis: 0, lineStyle: { color: "rgba(148,163,184,.25)", type: "solid" }, label: { show: false } },
          ],
        },
      },
    ],
  };
  chart.setOption(option, true);
}

/* ------------------------------------------------------------------ */
export function renderDetailContrib(el, series) {
  const chart = getChart(el);
  const dates = series.map((row) => row.date);
  const option = {
    animationDuration: 400,
    textStyle: { fontFamily: FONT, color: TEXT },
    grid: { left: 46, right: 16, top: 18, bottom: 30 },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow", shadowStyle: { color: "rgba(148,163,184,.06)" } },
      ...tooltipBase,
      formatter(params) {
        const row = series[params[0]?.dataIndex ?? 0];
        if (!row) return "";
        return `<div style="font-weight:700;margin-bottom:4px">${row.date}</div>
          <div style="font-size:11.5px;line-height:1.7">
            기여도 <b>${fmtPp(row.contrib, 3)}</b><br>
            등락 ${fmtPct(row.ret, 2)} · z ${fmtZ(row.z)}<br>
            그룹 <b style="color:${GROUP_COLOR[row.grp] || FLAT}">${GROUP_LABEL[row.grp] || "–"}</b> · 거래대금 ${fmtValue(row.value)}
          </div>`;
      },
    },
    xAxis: categoryAxis(dates, (value) => fmtDateShort(value)),
    yAxis: valueAxis({
      axisLabel: { color: DIM, fontSize: 10, formatter: (value) => `${value}` },
      splitLine: { lineStyle: { color: "rgba(30,41,59,.6)" } },
    }),
    series: [
      {
        type: "bar",
        data: series.map((row) => ({
          value: row.contrib,
          itemStyle: {
            color: (row.contrib || 0) >= 0 ? "rgba(34,197,94,.75)" : "rgba(244,63,94,.75)",
            borderRadius: (row.contrib || 0) >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2],
          },
        })),
        barMaxWidth: 10,
        markLine: {
          silent: true,
          symbol: "none",
          label: { show: false },
          lineStyle: { color: "rgba(148,163,184,.3)", width: 1 },
          data: [{ yAxis: 0 }],
        },
      },
    ],
  };
  chart.setOption(option, true);
}
