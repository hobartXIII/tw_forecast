/** 圖表資料整理與 Vega-Lite 規格。對應 tests/frontend/test_charts_and_map.py 的 SeriesChart 部分。 */
import { describe, expect, it } from "vitest";

import { DARK_CHART, MISSING_TIP, bandData, preparePoints, seriesChartSpec, type SeriesChartOptions } from "../src/lib/charts";
import { RAIN_ALERT } from "../src/lib/rain";
import type { SeriesPoint } from "../src/lib/scope";
import { tw } from "./fakes";

const NOW = tw(2026, 9, 21, 10);

/** 從 2026-09-21 06:00 起每 12 小時一個值。 */
function series(values: (number | null)[], name = "臺北市"): SeriesPoint[] {
  return values.map((value, i) => ({ series: name, start: new Date(tw(2026, 9, 21, 6).getTime() + i * 12 * 3600_000), value }));
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Layer = any;
const layers = (opts: SeriesChartOptions, data: SeriesPoint[], now = NOW): Layer[] =>
  (seriesChartSpec(opts, data, now) as { layer: Layer[] }).layer;
const ofType = (ls: Layer[], type: string) => ls.filter((l) => l.mark.type === type);

describe("preparePoints", () => {
  it("預設略過沒有值的時段；時段轉成不帶時區的台灣時間", () => {
    const d = preparePoints({ yTitle: "氣溫", order: ["臺北市"] }, series([20, null, 22]));
    expect(d.map((p) => p.值)).toEqual([20, 22]);
    expect(d.map((p) => p.顯示)).toEqual(["20.0", "22.0"]);
    expect(d[0].時段).toBe("2026-09-21T06:00:00");
  });

  it("fillZero 時補 0 並標記未提供", () => {
    const d = preparePoints({ yTitle: "降雨", order: ["臺北市"], threshold: RAIN_ALERT, fillZero: true }, series([70, null]));
    expect(d.map((p) => [p.值, p.未提供, p.顯示])).toEqual([[70, false, "70"], [0, true, MISSING_TIP]]);
  });
});

describe("seriesChartSpec", () => {
  it("氣溫圖：monotone 曲線、高度、圖例可點選、現在虛線", () => {
    const spec = seriesChartSpec({ yTitle: "氣溫 (°C)", order: ["臺北市"], zero: true }, series([20, 22]), NOW) as Layer;
    const line = ofType(spec.layer, "line")[0];
    expect(line.mark.interpolate).toBe("monotone");
    expect(spec.height).toBe(440);
    expect(line.params[0].bind).toBe("legend");
    expect(ofType(spec.layer, "rule")).toHaveLength(1);
  });

  it("「現在」不在資料範圍內就不畫虛線", () => {
    expect(ofType(layers({ yTitle: "氣溫", order: ["臺北市"] }, series([20, 22]), tw(2026, 10, 30)), "rule")).toHaveLength(0);
  });

  it("使用指定的顏色", () => {
    const json = JSON.stringify(seriesChartSpec(
      { yTitle: "氣溫", order: ["最高溫", "最低溫"], colors: ["#111111", "#222222"] }, series([1, 2], "最高溫"), NOW));
    expect(json).toContain("#111111");
    expect(json).toContain("#222222");
  });

  it("降雨圖：門檻線、y 軸固定 0～100、未提供的點是空心", () => {
    const ls = layers({ yTitle: "降雨", order: ["臺北市"], zero: true, threshold: RAIN_ALERT, fillZero: true }, series([70, null]));
    expect(ofType(ls, "rule")).toHaveLength(2); // 門檻線 + 現在
    const points = ofType(ls, "point");
    expect(points).toHaveLength(2);
    expect(points[1].mark.filled).toBe(false);
    expect(ofType(ls, "line")[0].encoding.y.scale.domain).toEqual([0, 100]);
    expect(points[0].encoding.size.condition.test).toBe(`datum['值'] >= ${RAIN_ALERT}`);
  });

  it("深色配色套用到座標軸文字", () => {
    const spec = seriesChartSpec({ yTitle: "氣溫", order: ["臺北市"] }, series([20]), NOW, DARK_CHART) as Layer;
    expect(spec.config.axis.labelColor).toBe(DARK_CHART.text);
  });
});

describe("溫度帶", () => {
  const opts: SeriesChartOptions = { yTitle: "氣溫", order: ["最高溫", "最低溫"], band: ["最低溫", "最高溫"] };
  const lines = (highs: (number | null)[], lows: (number | null)[]) => [...series(highs, "最高溫"), ...series(lows, "最低溫")];

  it("配對最低溫與最高溫，略過缺值的時段", () => {
    const b = bandData(opts, preparePoints(opts, lines([30, null, 28], [22, 21, 20.5])));
    expect(b.map((p) => [p.下緣, p.上緣, p.溫差])).toEqual([[22, 30, 8], [20.5, 28, 7.5]]);
  });

  it("溫度帶畫在最底層並使用漸層", () => {
    const area = layers(opts, lines([30, 29], [22, 21]))[0];
    expect(area.mark.type).toBe("area");
    expect(area.mark.color.gradient).toBe("linear");
    expect(area.encoding.y2.field).toBe("上緣");
  });

  it("缺少其中一個系列時不畫溫度帶", () => {
    expect(ofType(layers({ ...opts, order: ["最高溫"] }, series([30, 29], "最高溫")), "area")).toHaveLength(0);
  });
});
