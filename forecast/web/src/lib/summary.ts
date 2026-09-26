/** 重點摘要的四張卡片：平均氣溫、最高／最低溫、溫差、降雨機率（Streamlit 版是平均、最高、最低、降雨四張）。

單一縣市顯示該縣市自己的數值；其他範圍顯示平均與極值，並標出是哪個縣市：
最高／最低溫在數值下方列出兩個縣市，溫差取「各縣市自己的高低溫差」中最大的一個。
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
  /** 有值時數值改為多段、各自上色並以「 / 」相接（最高／最低溫）；text 仍是整段的純文字。 */
  parts?: { text: string; color: string }[];
  /** 數值下方的小字（多縣市時最高／最低溫各是哪個縣市）。 */
  sub?: string;
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

/** 最高／最低溫合併成一張：「29 / 25 °C」兩個數字各依級距上色，邊框依最高溫發光；cities 為 [最高溫縣市, 最低溫縣市]。 */
function highLowCard(high: number | null, low: number | null, cities?: [string, string]): CardModel {
  const num = (v: number | null) => (isMissing(v) ? "—" : v.toFixed(0));
  const bothMissing = isMissing(high) && isMissing(low);
  return {
    label: "最高／最低溫",
    text: bothMissing ? "—" : `${num(high)} / ${num(low)} °C`,
    textColor: "",
    accent: isMissing(high) ? "" : tempColor(high),
    aside: "",
    meter: null,
    parts: bothMissing ? undefined : [
      { text: num(high), color: textColor(high) },
      { text: `${num(low)} °C`, color: textColor(low) },
    ],
    sub: cities && !bothMissing ? `${cities[0] || "—"} / ${cities[1] || "—"}` : undefined,
  };
}

/** 一個縣市的高低溫差（任一為空則為 null）。 */
export function tempRange(row: Pick<ScopedRow, "max_temp" | "min_temp">): number | null {
  return isMissing(row.max_temp) || isMissing(row.min_temp) ? null : row.max_temp - row.min_temp;
}

/** 各縣市自己的高低溫差中最大的一個 { 溫差, 縣市名 }；都沒有值時為 { null, "" }。同值取先出現的一筆。 */
export function widestRange(cur: ScopedRow[]): { value: number | null; city: string } {
  let best: { value: number; city: string } | null = null;
  for (const r of cur) {
    const d = tempRange(r);
    if (d !== null && (best === null || d > best.value)) best = { value: d, city: r.location_name };
  }
  return best ?? { value: null, city: "" };
}

/** 溫差卡片：數字不上色、一般玻璃邊框。 */
function rangeCard(label: string, value: number | null): CardModel {
  return { label, text: formatValue(value, "°C"), textColor: "", accent: "", aside: "", meter: null };
}

/** 多縣市摘要：標題列在指標名稱後接縣市名（「最高溫　臺中市」）。 */
const withCity = (label: string, city: string) => (city ? `${label}　${city}` : label);

/** cur 為範圍內的「目前時段」資料（含 avg）。 */
/** 輪播最上方的範圍名稱：選了縣市為縣市名，否則為地區（「全部地區」或被選的地區）。 */
export function summaryTitle(scope: Scope): string {
  return scope.city ?? scope.region;
}

export function summaryCards(cur: ScopedRow[], scope: Scope): CardModel[] {
  if (scope.city) {
    const row = cur.find((r) => r.location_name === scope.city);
    if (!row) return [];
    const weather = row.weather_condition ?? "—";
    const icon = weatherIcon(row.weather_condition, isNight(row.forecast_time_start, row.forecast_time_end));
    return [
      tempCard("平均氣溫", row.avg, 1, `${icon} ${weather}`.trim()), // 縣市名顯示在輪播最上方（summaryTitle）
      highLowCard(row.max_temp, row.min_temp),
      rangeCard("溫差", tempRange(row)),
      rainCard("降雨機率", row.rain_probability),
    ];
  }
  const avgs = cur.map((r) => r.avg).filter((v): v is number => !isMissing(v));
  const mean = avgs.length ? avgs.reduce((a, b) => a + b, 0) / avgs.length : null;
  const hot = extreme(cur, "max_temp", true);
  const cold = extreme(cur, "min_temp", false);
  const wet = extreme(cur, "rain_probability", true);
  const wide = widestRange(cur);
  return [
    tempCard("平均氣溫", mean, 1),
    highLowCard(hot.value, cold.value, [hot.city, cold.city]),
    rangeCard(withCity("最大溫差", wide.city), wide.value),
    rainCard(withCity("最高降雨機率", wet.city), wet.value),
  ];
}
