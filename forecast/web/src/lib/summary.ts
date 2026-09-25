/** 重點摘要的四張卡片（對應 Python 的 views/summary.py）：平均氣溫、最高溫、最低溫、降雨機率。

單一縣市顯示該縣市自己的數值；其他範圍顯示平均與極值（並標出是哪個縣市）。
卡片邊框依級距色發光：溫度卡片依氣溫級距（與地圖標記同色），降雨卡片依降雨色階並附進度條。
*/
import { formatValue, isNight, weatherIcon } from "./formatting";
import { rainColor } from "./rain";
import type { Scope, ScopedRow } from "./scope";
import { isMissing, tempColor, textColor } from "./temperature";

export interface CardModel {
  label: string;
  /** 顯示文字，如「23.5 °C」或「—」。 */
  text: string;
  /** 數值文字的顏色（溫度依級距；降雨不上色）。 */
  textColor: string;
  /** 發光邊框的顏色，空字串代表一般玻璃邊框。 */
  accent: string;
  /** 顯示在數值右側的文字（單一縣市的天氣圖示與文字）。 */
  aside: string;
  /** 0～100 時畫進度條（降雨機率）；null 不畫。 */
  meter: number | null;
}

type Col = "max_temp" | "min_temp" | "rain_probability";

/** 回傳 { 數值, 縣市名 }；欄位全部沒有值時回傳 { null, "" }。同值取先出現的一筆。 */
export function extreme(cur: ScopedRow[], column: Col, largest: boolean): { value: number | null; city: string } {
  let best: ScopedRow | null = null;
  for (const r of cur) {
    const v = r[column];
    if (isMissing(v)) continue;
    if (best === null || (largest ? v > best[column]! : v < best[column]!)) best = r;
  }
  return best ? { value: best[column], city: best.location_name } : { value: null, city: "" };
}

function tempCard(label: string, value: number | null, digits = 0, aside = ""): CardModel {
  return {
    label, text: formatValue(value, "°C", digits), textColor: textColor(value),
    accent: isMissing(value) ? "" : tempColor(value), aside, meter: null,
  };
}

function rainCard(label: string, value: number | null): CardModel {
  return { label, text: formatValue(value, "%"), textColor: "", accent: rainColor(value), aside: "", meter: value };
}

/** 多縣市摘要：標題列在指標名稱後接縣市名（「最高溫　臺中市」）。 */
const withCity = (label: string, city: string) => (city ? `${label}　${city}` : label);

/** cur 為範圍內的「目前時段」資料（含 avg）。 */
export function summaryCards(cur: ScopedRow[], scope: Scope): CardModel[] {
  if (scope.city) {
    const row = cur.find((r) => r.location_name === scope.city);
    if (!row) return [];
    const weather = row.weather_condition ?? "—";
    const icon = weatherIcon(row.weather_condition, isNight(row.forecast_time_start, row.forecast_time_end));
    return [
      tempCard(`${scope.city} 平均氣溫`, row.avg, 1, `${icon} ${weather}`.trim()),
      tempCard("最高溫", row.max_temp),
      tempCard("最低溫", row.min_temp),
      rainCard("降雨機率", row.rain_probability),
    ];
  }
  const avgs = cur.map((r) => r.avg).filter((v): v is number => !isMissing(v));
  const mean = avgs.length ? avgs.reduce((a, b) => a + b, 0) / avgs.length : null;
  const hot = extreme(cur, "max_temp", true);
  const cold = extreme(cur, "min_temp", false);
  const wet = extreme(cur, "rain_probability", true);
  return [
    tempCard("平均氣溫", mean, 1),
    tempCard(withCity("最高溫", hot.city), hot.value),
    tempCard(withCity("最低溫", cold.city), cold.value),
    rainCard(withCity("最高降雨機率", wet.city), wet.value),
  ];
}
