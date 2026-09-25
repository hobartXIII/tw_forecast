/** 氣溫級距與顏色：地圖標記、圖例、表格與摘要卡片共用同一套級距。 */

type Num = number | null | undefined;

export const isMissing = (v: Num): v is null | undefined => v === null || v === undefined || Number.isNaN(v);

/** (顏色, 圖例文字)；規格 §8.1：<20 藍綠、20~25 綠、25~30 橙黃、>30 鮮紅 */
export const BANDS: [string, string][] = [
  ["#17a2b8", "< 20°C"],
  ["#2f9e44", "20 ~ 25°C"],
  ["#f59f00", "25 ~ 30°C"],
  ["#e03131", "> 30°C"],
];

/** 文字用的級距色：中等明度，在淺色與深色主題的底色上對比都約 3:1 以上（標記底色用 BANDS，較亮）。 */
export const TEXT_COLORS = ["#0b8ba0", "#2b8a3e", "#cc6a00", "#e03131"];

/** 溫度所屬級距：0（<20）、1（20~25）、2（25~30）、3（>30）；邊界值歸入較低級距。 */
export function bandIndex(temp: number): number {
  if (temp < 20) return 0;
  if (temp <= 25) return 1;
  if (temp <= 30) return 2;
  return 3;
}

/** 標記底色（較亮）。 */
export function tempColor(temp: number): string {
  return BANDS[bandIndex(temp)][0];
}

/** 文字用的級距色；沒有值回傳空字串（沿用預設文字色）。 */
export function textColor(value: Num): string {
  return isMissing(value) ? "" : TEXT_COLORS[bandIndex(value)];
}

/** 整數溫度；沒有值顯示「—」。 */
export function tempText(value: Num, unit = "°C"): string {
  return isMissing(value) ? "—" : `${Math.round(value)}${unit}`;
}

/** 平均溫；avg_temp 沒有值時退回 (min_temp + max_temp) / 2（兩者之一沒有值則為 null）。 */
export function displayTemp(row: { avg_temp: Num; min_temp: Num; max_temp: Num }): number | null {
  if (!isMissing(row.avg_temp)) return row.avg_temp;
  if (isMissing(row.min_temp) || isMissing(row.max_temp)) return null;
  return (row.min_temp + row.max_temp) / 2;
}
