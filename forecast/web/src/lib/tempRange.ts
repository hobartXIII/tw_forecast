/** 溫差（最高溫 − 最低溫）的色階：摘要卡片的發光邊框用。
紫色系，與氣溫級距（藍綠／綠／橙／紅）和降雨色階（藍）區隔，顏色越深代表溫差越大。 */
import { isMissing } from "./temperature";

/** 溫差達這麼多度視為「溫差大」（氣象署常以「溫差 10 度以上」提醒注意），卡片轉為最深的紫。 */
export const RANGE_WIDE = 10;

/** (下限 °C, 顏色)：由淺到深。 */
export const RANGE_BANDS: [number, string][] = [
  [0, "#b197fc"], // < 6 °C：淡紫（溫差小）
  [6, "#845ef7"], // 6 ~ 9 °C：紫（溫差明顯）
  [RANGE_WIDE, "#6741d9"], // >= 10 °C：深紫（溫差大）
];

/** 溫差所屬色階的顏色；沒有值回傳空字串（一般玻璃邊框）。 */
export function rangeColor(value: number | null | undefined): string {
  if (isMissing(value)) return "";
  return [...RANGE_BANDS].reverse().find(([low]) => value >= low)?.[1] ?? RANGE_BANDS[0][1];
}
