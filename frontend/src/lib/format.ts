// 粗折算汇率，跟旧版 app/index.html 保持一致，仅用于展示估算，不做精确换算
export const USD_CNY_RATE = 7.14;

const PLACEHOLDERS = new Set([
  "",
  "未知",
  "unknown",
  "n/a",
  "na",
  "地点未知",
  "远程/未知",
  "confidential",
  "匿名",
]);

/** 抓取占位（未知 / n/a）不当公司名或地点展示，返回空串。 */
export function displayField(value: string | null | undefined): string {
  const text = (value || "").trim();
  return PLACEHOLDERS.has(text.toLowerCase()) ? "" : text;
}

export function formatUsdAsCny(usd: number): string {
  return `¥${Math.round(usd * USD_CNY_RATE).toLocaleString("zh-CN")}`;
}

/** 相对时间：列表新鲜度。 */
export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  return new Date(iso).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function formatSalaryUsd(min: number, max: number, bucket?: string): string {
  if (!max && !min) return bucket || "";
  const lo = min ? `$${Math.round(min / 1000)}k` : "";
  const hi = max ? `$${Math.round(max / 1000)}k` : "";
  const range = lo && hi ? (lo === hi ? hi : `${lo}–${hi}`) : hi || lo;
  return bucket ? `${range} · ${bucket}` : range;
}
