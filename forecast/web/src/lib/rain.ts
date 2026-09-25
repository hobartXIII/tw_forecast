/** 降雨機率的門檻與色階：摘要卡片（發光邊框與進度條）與趨勢圖共用。 */
import { isMissing } from "./temperature";

/** 與後端告警預設降雨門檻一致；圖上以紅色虛線標示，卡片轉為最深的雨藍。 */
export const RAIN_ALERT = 60;

/** (下限 %, 顏色)：由淺到深的雨藍，機率越高越像烏雲壓頂的靛藍。 */
export const RAIN_BANDS: [number, string][] = [
  [0, "#74c0fc"], // < 30%：淡天藍
  [30, "#339af0"], // 30 ~ 59%：雨藍
  [RAIN_ALERT, "#3b5bdb"], // >= 60%：靛藍（達告警門檻）
];

/** 降雨機率所屬色階的顏色；沒有值回傳空字串（不上色）。 */
export function rainColor(value: number | null | undefined): string {
  if (isMissing(value)) return "";
  return [...RAIN_BANDS].reverse().find(([low]) => value >= low)?.[1] ?? RAIN_BANDS[0][1];
}
