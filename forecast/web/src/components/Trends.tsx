/** 「氣溫趨勢」與「降雨機率」兩個分頁。全台／地區／單一縣市都用同一種折線圖（lib/charts.ts）。 */
import { useMemo, useState } from "react";

import { useDarkMode, useNarrow } from "../hooks/useDarkMode";
import { DARK_CHART, LIGHT_CHART, TEMP_LINE_COLORS, TEMP_LINE_COLUMNS, seriesChartSpec } from "../lib/charts";
import { RAIN_ALERT } from "../lib/rain";
import type { Scope, ScopedRow, SeriesColumn } from "../lib/scope";
import { Notice } from "./Notice";
import { VegaChart } from "./VegaChart";

/** 手機上圖例每列最多幾項（全台 5 個地區、一個地區最多 6 個縣市，放不下一列）。 */
const NARROW_LEGEND_COLUMNS = 3;

/** 地區／全台的指標選項。 */
const TEMP_METRICS: Record<string, SeriesColumn> = { 最高溫: "max_temp", 最低溫: "min_temp", 平均溫: "avg" };

export const STALE_FORECAST = "沒有未來預報資料（資料可能已過期），請等待下次排程更新（每 3 小時一次）。";

export function TemperatureTab({ scope, fc, now }: { scope: Scope; fc: ScopedRow[] | null; now: Date }) {
  const dark = useDarkMode();
  const legendColumns = useNarrow() ? NARROW_LEGEND_COLUMNS : undefined;
  const [metric, setMetric] = useState("最高溫");
  const spec = useMemo(() => {
    if (!fc) return null;
    const theme = dark ? DARK_CHART : LIGHT_CHART;
    if (scope.level === "city") {
      const data = Object.entries(TEMP_LINE_COLUMNS).flatMap(([name, col]) =>
        scope.seriesData(fc, col).data.map((p) => ({ ...p, series: name })));
      if (data.every((p) => p.value === null)) return null;
      return seriesChartSpec({
        yTitle: "氣溫 (°C)", order: Object.keys(TEMP_LINE_COLUMNS), zero: true,
        colors: TEMP_LINE_COLORS, band: ["最低溫", "最高溫"], legendColumns,
      }, data, now, theme);
    }
    const { data, order } = scope.seriesData(fc, TEMP_METRICS[metric]);
    if (data.every((p) => p.value === null)) return null;
    return seriesChartSpec({ yTitle: `${metric} (°C)`, order, zero: true, legendColumns }, data, now, theme);
  }, [scope, fc, now, metric, dark, legendColumns]);

  if (!fc) return <Notice kind="info">{STALE_FORECAST}</Notice>;
  return (
    <>
      {scope.level === "city" ? (
        <p className="caption">{scope.label}｜最高溫、平均溫、最低溫｜色帶為最低～最高溫的範圍，點圖例可強調單一線條，虛線為現在</p>
      ) : (
        <>
          <div className="radio-row" role="radiogroup" aria-label="氣溫指標">
            {Object.keys(TEMP_METRICS).map((m) => (
              <label key={m}>
                <input type="radio" name="metric" checked={metric === m} onChange={() => setMetric(m)} /> {m}
              </label>
            ))}
          </div>
          <p className="caption">{scope.label}｜{metric}｜每種顏色一條線，點圖例可強調單一系列，虛線為現在</p>
        </>
      )}
      {spec ? <VegaChart spec={spec} dark={dark} /> : <Notice kind="info">沒有可繪製的氣溫資料。</Notice>}
    </>
  );
}

export function RainTab({ scope, fc, now }: { scope: Scope; fc: ScopedRow[] | null; now: Date }) {
  const dark = useDarkMode();
  const legendColumns = useNarrow() ? NARROW_LEGEND_COLUMNS : undefined;
  const hasData = !!fc && fc.some((r) => r.rain_probability !== null);
  const spec = useMemo(() => {
    if (!fc || !hasData) return null;
    const { data, order } = scope.seriesData(fc, "rain_probability");
    return seriesChartSpec({ yTitle: "降雨機率 (%)", order, zero: true, threshold: RAIN_ALERT, fillZero: true, legendColumns },
      data, now, dark ? DARK_CHART : LIGHT_CHART);
  }, [scope, fc, now, hasData, dark, legendColumns]);

  return (
    <>
      {spec ? (
        <>
          <p className="caption">{scope.label}｜12 小時降雨機率（紅色虛線為 {RAIN_ALERT}% 告警門檻，超過者的點放大並加紅框）</p>
          <VegaChart spec={spec} dark={dark} />
        </>
      ) : (
        <Notice kind="info">沒有降雨機率資料（遠期時段氣象署未提供）。</Notice>
      )}
      <p className="caption">空心點：氣象署未提供該時段的降雨機率（通常是遠期），圖上以 0 顯示，並非預報 0%；明細表格與摘要仍顯示為「—」。</p>
    </>
  );
}
