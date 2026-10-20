export const GROUP_LABEL = { U: "상향", F: "횡보", D: "하향" };
export const GROUP_COLOR = { U: "#22c55e", F: "#94a3b8", D: "#f43f5e" };
export const GROUP_ORDER = { U: 0, F: 1, D: 2 };
const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

export function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function isNum(value) {
  return typeof value === "number" && Number.isFinite(value);
}

export function fmtPct(value, digits = 2, withSign = true) {
  if (!isNum(value)) return "–";
  const sign = withSign && value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function fmtPp(value, digits = 3) {
  if (!isNum(value)) return "–";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%p`;
}

export function fmtZ(value, digits = 2) {
  if (!isNum(value)) return "–";
  return `${value > 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function fmtNum(value, digits = 0) {
  if (!isNum(value)) return "–";
  return value.toLocaleString("ko-KR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function fmtCompact(value) {
  if (!isNum(value)) return "–";
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(1)}조`;
  if (abs >= 1e8) return `${(value / 1e8).toFixed(0)}억`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(0)}만`;
  return fmtNum(value);
}

export function fmtMcap(value) {
  if (!isNum(value)) return "–";
  return `${value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })}조`;
}

export function fmtValue(value) {
  if (!isNum(value)) return "–";
  return `${Math.round(value).toLocaleString("ko-KR")}억`;
}

export function fmtWeight(value) {
  if (!isNum(value)) return "–";
  return `${value.toFixed(2)}%`;
}

export function fmtPrice(value) {
  if (!isNum(value)) return "–";
  return Math.round(value).toLocaleString("ko-KR");
}

export function fmtDateShort(iso) {
  if (!iso) return "–";
  const [, m, d] = String(iso).split("-");
  return `${Number(m)}/${Number(d)}`;
}

export function fmtDateLong(iso) {
  if (!iso) return "–";
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return `${iso} (${WEEKDAYS[date.getDay()]})`;
}

export function signClass(value) {
  if (!isNum(value) || value === 0) return "";
  return value > 0 ? "pos" : "neg";
}

export function groupBadge(group, extra = "") {
  if (!group) return `<span class="grp-F ${extra}">–</span>`;
  return `<span class="grp-${group} ${extra}">${GROUP_LABEL[group] ?? group}</span>`;
}

export function groupClass(group) {
  return group ? `grp-${group}` : "";
}

export function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

export function debounce(fn, wait = 300) {
  let timer = null;
  const wrapped = (...args) => {
    window.clearTimeout(timer);
    timer = window.setTimeout(() => fn(...args), wait);
  };
  wrapped.cancel = () => window.clearTimeout(timer);
  return wrapped;
}

export function sum(values) {
  return values.reduce((acc, value) => acc + (isNum(value) ? value : 0), 0);
}

export function downloadCsv(filename, rows, columns) {
  const escape = (value) => {
    if (value === null || value === undefined) return "";
    const text = String(value);
    if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
    return text;
  };
  const lines = [columns.map((c) => escape(c.label)).join(",")];
  for (const row of rows) {
    lines.push(columns.map((c) => escape(row[c.key])).join(","));
  }
  const blob = new Blob([`\ufeff${lines.join("\n")}`], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function formatSignedNumber(value, digits = 2) {
  if (!isNum(value)) return "–";
  return `${value > 0 ? "+" : ""}${value.toLocaleString("ko-KR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })}`;
}
