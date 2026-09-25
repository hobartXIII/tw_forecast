/** 一週趨勢圖的 Vega-Lite 規格：氣溫（最高／最低／平均）與降雨機率（對應 Python 的 charts.py）。

氣溫與降雨機率都用同一種折線圖：每個系列一種顏色，可點圖例強調單一系列；折線用 monotone 曲線
（柔和且不會超出資料範圍）。單一縣市的氣溫圖把最高／平均／最低三條線畫在一起，並在最低溫與最高溫之間
鋪一條由藍到橙的半透明溫度帶，一眼看出每個時段的溫差。
時間軸一律以台灣時間顯示（見 time.wallTime）。

輸入：多系列長表（SeriesPoint）、現在時間、配色（淺色／深色）。輸出：Vega-Lite 規格。
*/
import type { TopLevelSpec } from "vega-lite";

import type { SeriesPoint } from "./scope";
import { wallTime } from "./time";

/** Okabe-Ito 色盲友善色盤；一個地區最多 6 個縣市，全台則是 5 個地區。 */
export const PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9"];
/** 單一縣市合併圖的線條順序與對應欄位。 */
export const TEMP_LINE_COLUMNS = { 最高溫: "max_temp", 平均溫: "avg", 最低溫: "min_temp" } as const;
/** 暖色最高、綠色平均、冷色最低。 */
export const TEMP_LINE_COLORS = ["#D55E00", "#009E73", "#0072B2"];
export const MISSING_TIP = "0（氣象署未提供，以 0 顯示）";
export const CHART_HEIGHT = 440;
const BAND_OPACITY = 0.22;
const THRESHOLD_COLOR = "#c92a2a";
const HALF_DAY_MS = 12 * 3600_000;

/** 圖表文字與格線的顏色（Vega 讀不到頁面的 CSS 變數，由畫面依淺色／深色傳入）。 */
export interface ChartTheme {
  text: string;
  grid: string;
  nowRule: string;
  pointFill: string;
}

export const LIGHT_CHART: ChartTheme = { text: "#2B2620", grid: "#d5d0c8", nowRule: "#495057", pointFill: "white" };
export const DARK_CHART: ChartTheme = { text: "#ECEFF4", grid: "#3a4050", nowRule: "#adb5bd", pointFill: "#1B1F2B" };

export interface SeriesChartOptions {
  yTitle: string;
  /** 決定顏色與圖例順序。 */
  order: string[];
  zero?: boolean;
  /** 有值時（降雨機率）畫出門檻虛線，並把 >= 門檻的點放大加紅框；y 軸固定 0～100。 */
  threshold?: number;
  /** true 時，沒有值的時段補 0 並以空心點標示、提示「氣象署未提供」；否則這些時段不畫。 */
  fillZero?: boolean;
  /** 各系列顏色（與 order 對應），沒給就用 PALETTE。 */
  colors?: string[];
  /** (下緣系列, 上緣系列)：在兩系列之間畫漸層溫度帶（只畫兩者都有值的時段）。 */
  band?: [string, string];
}

export interface PreparedPoint {
  時段: string;
  系列: string;
  值: number;
  未提供: boolean;
  顯示: string;
}

export interface BandPoint {
  時段: string;
  下緣: number;
  上緣: number;
  溫差: number;
}

/** 繪圖用資料：時段轉成台灣牆上時間、標記未提供的值、準備提示框文字。 */
export function preparePoints(opts: SeriesChartOptions, data: SeriesPoint[]): PreparedPoint[] {
  const digits = opts.threshold !== undefined ? 0 : 1;
  return data
    .filter((p) => opts.fillZero || p.value !== null)
    .map((p) => {
      const missing = p.value === null;
      const value = p.value ?? 0;
      return { 時段: wallTime(p.start), 系列: p.series, 值: value, 未提供: missing, 顯示: missing ? MISSING_TIP : value.toFixed(digits) };
    });
}

/** 溫度帶：每個時段一列的下緣、上緣、溫差（兩系列都有值的時段）。 */
export function bandData(opts: SeriesChartOptions, points: PreparedPoint[]): BandPoint[] {
  if (!opts.band) return [];
  const [low, high] = opts.band;
  const byTime = new Map<string, { low?: number; high?: number }>();
  for (const p of points) {
    if (p.未提供 || (p.系列 !== low && p.系列 !== high)) continue;
    const entry = byTime.get(p.時段) ?? {};
    entry[p.系列 === low ? "low" : "high"] = p.值;
    byTime.set(p.時段, entry);
  }
  return [...byTime.entries()]
    .filter(([, e]) => e.low !== undefined && e.high !== undefined)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([t, e]) => ({ 時段: t, 下緣: e.low!, 上緣: e.high!, 溫差: Math.round((e.high! - e.low!) * 10) / 10 }));
}

/** 「現在」落在資料範圍（前後各 12 小時）內才畫虛線。 */
function showNow(data: SeriesPoint[], now: Date): boolean {
  if (!data.length) return false;
  const times = data.map((p) => p.start.getTime());
  return Math.min(...times) - HALF_DAY_MS <= now.getTime() && now.getTime() <= Math.max(...times) + HALF_DAY_MS;
}

/** 畫圖：（選擇性的溫度帶）+ 折線 + 資料點（可點圖例強調）+ 選擇性的門檻線與「現在」虛線。 */
export function seriesChartSpec(
  opts: SeriesChartOptions, data: SeriesPoint[], now: Date, theme: ChartTheme = LIGHT_CHART,
): TopLevelSpec {
  const points = preparePoints(opts, data);
  const real = points.filter((p) => !p.未提供);
  const missing = points.filter((p) => p.未提供);
  const hasThreshold = opts.threshold !== undefined;
  const scale = { domain: opts.order, range: opts.colors ?? PALETTE.slice(0, opts.order.length) };
  const x = { field: "時段", type: "temporal", title: null, axis: { format: "%m/%d %H:%M", labelAngle: -30 } } as const;
  const yScale = { zero: opts.zero ?? false, ...(hasThreshold ? { domain: [0, 100] } : {}) };
  const y = { field: "值", type: "quantitative", title: opts.yTitle, scale: yScale } as const;
  const opacity = { condition: { param: "select", value: 1 }, value: 0.15 };
  const seriesColor = { field: "系列", type: "nominal", scale } as const; // 與折線共用同一個比例尺，圖例會合併成一個
  const tooltip = [
    { field: "系列", type: "nominal" },
    { field: "時段", type: "temporal", format: "%m/%d %H:%M" },
    { field: "顯示", type: "nominal", title: opts.yTitle },
  ] as const;
  const over = `datum['值'] >= ${opts.threshold}`;

  const layers: unknown[] = [];
  const band = bandData(opts, points);
  if (band.length) { // 溫度帶放最底層，折線與資料點畫在上面
    const [cold, warm] = [TEMP_LINE_COLORS[2], TEMP_LINE_COLORS[0]];
    layers.push({
      data: { values: band },
      mark: {
        type: "area", interpolate: "monotone", opacity: BAND_OPACITY,
        color: { gradient: "linear", x1: 0, x2: 0, y1: 1, y2: 0, stops: [{ offset: 0, color: cold }, { offset: 1, color: warm }] },
      },
      encoding: {
        x, y: { field: "下緣", type: "quantitative", title: opts.yTitle, scale: yScale }, y2: { field: "上緣" },
        tooltip: [{ field: "時段", type: "temporal", format: "%m/%d %H:%M" },
          { field: "溫差", type: "quantitative", title: "溫差 (°C)", format: ".1f" }],
      },
    });
  }
  layers.push({
    data: { values: points },
    params: [{ name: "select", select: { type: "point", fields: ["系列"] }, bind: "legend" }],
    mark: { type: "line", strokeWidth: 2.5, strokeJoin: "round", interpolate: "monotone" },
    encoding: { x, y, opacity, color: { field: "系列", type: "nominal", scale, legend: { title: null, orient: "top" } } },
  });
  layers.push({
    data: { values: real },
    mark: { type: "point", filled: true, strokeWidth: 2 },
    encoding: {
      x, y, opacity, tooltip, color: seriesColor,
      size: hasThreshold ? { condition: { test: over, value: 160 }, value: 45 } : { value: 45 },
      stroke: hasThreshold ? { condition: { test: over, value: THRESHOLD_COLOR }, value: theme.pointFill } : { value: theme.pointFill },
    },
  });
  if (missing.length) { // 補值的點畫成空心（底色＋系列色外框），一眼看得出不是真的預報值
    layers.push({
      data: { values: missing },
      mark: { type: "point", filled: false, fill: theme.pointFill, size: 45, strokeWidth: 2 },
      encoding: { x, y, opacity, tooltip, color: seriesColor },
    });
  }
  if (hasThreshold) {
    layers.push({
      data: { values: [{ y: opts.threshold }] },
      mark: { type: "rule", strokeDash: [6, 4], color: THRESHOLD_COLOR, opacity: 0.6 },
      encoding: { y: { field: "y", type: "quantitative" } },
    });
  }
  if (showNow(data.filter((p) => opts.fillZero || p.value !== null), now)) {
    layers.push({
      data: { values: [{ 時段: wallTime(now) }] },
      mark: { type: "rule", strokeDash: [4, 4], color: theme.nowRule },
      encoding: { x: { field: "時段", type: "temporal" } },
    });
  }

  return {
    $schema: "https://vega.github.io/schema/vega-lite/v6.json",
    width: "container",
    height: CHART_HEIGHT,
    autosize: { type: "fit-x", contains: "padding" },
    background: "transparent",
    config: {
      font: "system-ui, 'Noto Sans TC', 'Microsoft JhengHei', sans-serif",
      axis: {
        gridDash: [2, 4], gridOpacity: 0.6, domain: false, gridColor: theme.grid, tickColor: theme.grid,
        labelColor: theme.text, titleColor: theme.text,
      },
      legend: { labelColor: theme.text },
      view: { strokeWidth: 0 },
    },
    layer: layers,
  } as TopLevelSpec;
}
