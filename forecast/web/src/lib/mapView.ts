/** 台灣氣溫地圖的內容（純函式，對應 Python 的 map_view.py）：標記、提示框、圖例的 HTML，以及地圖視野。

實際的 Leaflet 地圖在 components/TemperatureMap.tsx；這裡只決定「畫什麼、畫在哪」，方便單元測試。
*/
import { isNight, weatherIcon } from "./formatting";
import { rainColor } from "./rain";
import type { Level, ScopedRow } from "./scope";
import { BANDS, bandIndex, isMissing, tempColor, tempText, textColor } from "./temperature";

export const TAIWAN_CENTER: [number, number] = [23.7, 121.0];
export const GESTURE_TEXT = {
  touch: "請用兩指移動地圖",
  scroll: "按住 Ctrl 並滾動滾輪來縮放地圖",
  scrollMac: "按住 ⌘ 並滾動滾輪來縮放地圖",
};

export type MarkerState = "normal" | "selected" | "dim";

/** 資料庫的文字放進 HTML 前先跳脫。 */
export function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

/** 地圖縮放層級小於這個值（全台視野）時，標記縮小，北部縣市比較不會疊在一起。 */
export const COMPACT_BELOW_ZOOM = 8;
/** 降雨環的寬度（px），畫在圓圈外圍；標記的總大小 = 圓圈 + 兩側的環。 */
export const RAIN_RING_PX = 3;

/** 標記的 HTML（外觀在 global.css 的 .tm）：依級距色的放射漸層圓圈與同色柔光，外圍一圈降雨環
（長度＝降雨機率、顏色依降雨色階；降雨機率為 0% 或沒有值時不畫環）。

state：normal 一般／selected 被選中（放大）／dim 未被選中（淡化）；與「選地區」一樣只靠淡化區分，不加外框；
compact 為全台視野的縮小版。只帶入數字與固定的色碼，不含資料庫文字。
*/
export function markerHtml(temp: number, state: MarkerState = "normal", rain: number | null = null, compact = false): string {
  const fontColor = bandIndex(temp) === 2 ? "#222" : "#fff"; // 橙黃底用深色字才看得清楚
  const size = markerSize(state, compact);
  const hasRain = !isMissing(rain) && rain > 0; // 0% 不畫環，地圖上只留會下雨的縣市
  const pct = hasRain ? Math.min(Math.max(rain, 0), 100) : 0;
  const vars = [`--c:${tempColor(temp)}`, `--size:${size}px`, `--ring:${RAIN_RING_PX}px`, `--fg:${fontColor}`,
    ...(hasRain ? [`--rain:${pct}%`, `--rain-c:${rainColor(rain)}`] : [])].join(";");
  const cls = `tm tm-${state}${compact ? " tm-compact" : ""}${hasRain ? " tm-has-rain" : ""}`;
  return `<div class="${cls}" style="${vars}"><div class="tm-dot">${Math.round(temp)}°</div></div>`;
}

/** 標記的總大小（含降雨環）：一般 38px、被選中 46px；compact（全台視野）各小 6px。 */
export function markerSize(state: MarkerState, compact = false): number {
  return (state === "selected" ? 46 : 38) - (compact ? 6 : 0);
}

function colored(value: number | null, text: string): string {
  const color = textColor(value);
  return color ? `<span style="color:${color};font-weight:700">${text}</span>` : text;
}

/** 滑鼠移到標記上的提示：縣市、天氣、平均／最高／最低溫（依級距上色）與降雨機率。 */
export function tooltipHtml(row: ScopedRow, temp: number): string {
  const rain = isMissing(row.rain_probability) ? "—" : `${Math.round(row.rain_probability)}%`;
  const weather = row.weather_condition;
  const icon = weatherIcon(weather, isNight(row.forecast_time_start, row.forecast_time_end));
  return `<b>${escapeHtml(row.location_name)}</b><br>${icon} ${weather ? escapeHtml(weather) : "—"}<br>`
    + `平均 ${colored(temp, `${temp.toFixed(1)}°C`)}<br>`
    + `最高 ${colored(row.max_temp, tempText(row.max_temp))} ｜ 最低 ${colored(row.min_temp, tempText(row.min_temp))}<br>`
    + `降雨機率 ${rain}`;
}

/** 圖例的項目（顏色、文字）。 */
export const LEGEND = BANDS;

/** 圖例色條的刻度：級距的分界溫度。色條的範圍是 LEGEND_RANGE，每個級距佔一段、交界處柔和過渡。 */
export const LEGEND_TICKS = [20, 25, 30];
export const LEGEND_RANGE: [number, number] = [15, 35];

/** 圖例色條的 CSS 漸層：每個級距一段顏色，分界前後各 2% 過渡。 */
export function legendGradient(): string {
  const [lo, hi] = LEGEND_RANGE;
  const pos = (t: number) => ((t - lo) / (hi - lo)) * 100;
  const stops: string[] = [];
  BANDS.forEach(([color], i) => {
    const start = i === 0 ? 0 : pos(LEGEND_TICKS[i - 1]) + 2;
    const end = i === BANDS.length - 1 ? 100 : pos(LEGEND_TICKS[i]) - 2;
    stops.push(`${color} ${start}%`, `${color} ${end}%`);
  });
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

/** 刻度在色條上的位置（%）。 */
export const legendTickPos = (t: number) => ((t - LEGEND_RANGE[0]) / (LEGEND_RANGE[1] - LEGEND_RANGE[0])) * 100;

export interface MapPoint {
  city: string;
  lat: number;
  lng: number;
  temp: number;
  /** 降雨機率（0～100；沒有值為 null），畫成標記外圍的降雨環。 */
  rain: number | null;
  state: MarkerState;
}

/** 可畫在地圖上的縣市（有座標與平均溫才畫）；highlight 為被選的縣市（其餘淡化）。 */
export function mapPoints(cur: ScopedRow[], highlight: string | null): MapPoint[] {
  return cur.flatMap((r) => {
    if (isMissing(r.latitude) || isMissing(r.longitude) || isMissing(r.avg)) return [];
    const state: MarkerState = highlight === null ? "normal" : r.location_name === highlight ? "selected" : "dim";
    const rain = isMissing(r.rain_probability) ? null : r.rain_probability;
    return [{ city: r.location_name, lat: r.latitude, lng: r.longitude, temp: r.avg, rain, state }];
  });
}

export type MapViewport =
  | { kind: "center"; center: [number, number]; zoom: number }
  | { kind: "bounds"; bounds: [[number, number], [number, number]] };

/** 地圖視野：選了縣市 → 以該縣市為中心放大到 9；選了地區 → 框住範圍內的縣市；全台 → 台灣中心、縮放 7。 */
export function mapViewport(points: MapPoint[], level: Level): MapViewport {
  const selected = points.find((p) => p.state === "selected");
  if (selected) return { kind: "center", center: [selected.lat, selected.lng], zoom: 9 };
  if (level === "region" && points.length > 1) {
    const lats = points.map((p) => p.lat);
    const lngs = points.map((p) => p.lng);
    return { kind: "bounds", bounds: [[Math.min(...lats), Math.min(...lngs)], [Math.max(...lats), Math.max(...lngs)]] };
  }
  return { kind: "center", center: TAIWAN_CENTER, zoom: 7 };
}
