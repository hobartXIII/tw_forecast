/** 台灣氣溫地圖的內容（純函式，對應 Python 的 map_view.py）：標記、提示框、圖例的 HTML，以及地圖視野。

實際的 Leaflet 地圖在 components/TemperatureMap.tsx；這裡只決定「畫什麼、畫在哪」，方便單元測試。
*/
import { isNight, weatherIcon } from "./formatting";
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

/** 標記的 HTML。state：normal 一般／selected 被選中（放大加外框）／dim 未被選中（淡化）。 */
export function markerHtml(temp: number, state: MarkerState = "normal"): string {
  const fontColor = bandIndex(temp) === 2 ? "#222" : "#fff"; // 橙黃底用深色字才看得清楚
  const size = markerSize(state);
  const ring = state === "selected" ? "0 0 0 4px #1c7ed6, 0 2px 6px rgba(0,0,0,.5)" : "0 1px 4px rgba(0,0,0,.45)";
  const opacity = state === "dim" ? 0.45 : 1;
  const font = state === "selected" ? 14 : 13;
  return `<div style="width:${size}px;height:${size}px;border-radius:50%;background:${tempColor(temp)};`
    + `border:2px solid #fff;box-shadow:${ring};opacity:${opacity};color:${fontColor};`
    + `font:700 ${font}px/${size - 4}px sans-serif;text-align:center">${Math.round(temp)}°</div>`;
}

export function markerSize(state: MarkerState): number {
  return state === "selected" ? 46 : 38;
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

export interface MapPoint {
  city: string;
  lat: number;
  lng: number;
  temp: number;
  state: MarkerState;
}

/** 可畫在地圖上的縣市（有座標與平均溫才畫）；highlight 為被選的縣市（其餘淡化）。 */
export function mapPoints(cur: ScopedRow[], highlight: string | null): MapPoint[] {
  return cur.flatMap((r) => {
    if (isMissing(r.latitude) || isMissing(r.longitude) || isMissing(r.avg)) return [];
    const state: MarkerState = highlight === null ? "normal" : r.location_name === highlight ? "selected" : "dim";
    return [{ city: r.location_name, lat: r.latitude, lng: r.longitude, temp: r.avg, state }];
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
