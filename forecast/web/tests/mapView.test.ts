/** 地圖內容：標記、提示框、圖例、視野。對應 tests/frontend/test_charts_and_map.py 的地圖部分。 */
import { describe, expect, it } from "vitest";

import {
  LEGEND, LEGEND_TICKS, TAIWAN_CENTER, escapeHtml, legendGradient, legendTickPos, mapPoints, mapViewport, markerHtml,
  markerSize, tooltipHtml,
} from "../src/lib/mapView";
import { rainColor } from "../src/lib/rain";
import { toForecastRow } from "../src/lib/repository";
import { addRegion, withAvg, type ScopedRow } from "../src/lib/scope";
import { forecastRows, tw } from "./fakes";

const cur = (): ScopedRow[] => {
  const rows = withAvg(addRegion(forecastRows(tw(2026, 9, 21, 6), 1).map(toForecastRow)));
  const first = rows[0].forecast_time_start.getTime();
  return rows.filter((r) => r.forecast_time_start.getTime() === first);
};

describe("mapPoints", () => {
  it("每個縣市一個標記", () => {
    expect(mapPoints(cur(), null)).toHaveLength(22);
    expect(mapPoints(cur(), null).every((p) => p.state === "normal")).toBe(true);
  });

  it("略過沒有座標或溫度的縣市", () => {
    const rows = cur();
    rows[0] = { ...rows[0], latitude: null };
    rows[1] = { ...rows[1], avg: null };
    expect(mapPoints(rows, null)).toHaveLength(20);
  });

  it("選了縣市時該縣市放大，其餘淡化", () => {
    const points = mapPoints(cur(), "臺中市");
    expect(points.filter((p) => p.state === "selected").map((p) => p.city)).toEqual(["臺中市"]);
    expect(points.filter((p) => p.state === "dim")).toHaveLength(21);
  });

  it("帶入降雨機率（沒有值為 null），畫成降雨環", () => {
    const rows = cur();
    rows[0] = { ...rows[0], rain_probability: null };
    const points = mapPoints(rows, null);
    expect(points[0].rain).toBeNull();
    expect(points[1].rain).toBe(rows[1].rain_probability);
  });
});

describe("mapViewport", () => {
  it("選了縣市：以該縣市為中心、縮放 9", () => {
    const rows = cur();
    const city = rows.find((r) => r.location_name === "臺中市")!;
    expect(mapViewport(mapPoints(rows, "臺中市"), "city")).toEqual({ kind: "center", center: [city.latitude, city.longitude], zoom: 9 });
  });

  it("選了地區：框住範圍內的縣市", () => {
    const east = cur().filter((r) => r.region === "東部地區");
    const view = mapViewport(mapPoints(east, null), "region");
    expect(view.kind).toBe("bounds");
    const lats = east.map((r) => r.latitude!);
    expect(view.kind === "bounds" && view.bounds[0][0]).toBe(Math.min(...lats));
  });

  it("全台：台灣中心、縮放 7", () => {
    expect(mapViewport(mapPoints(cur(), null), "all")).toEqual({ kind: "center", center: TAIWAN_CENTER, zoom: 7 });
  });
});

describe("HTML", () => {
  it("標記：級距色、橙黃底用深色字、選中與淡化的樣式", () => {
    expect(markerHtml(28)).toContain("--c:#f59f00");
    expect(markerHtml(28)).toContain("--fg:#222");
    expect(markerHtml(35)).toContain("--fg:#fff");
    expect(markerHtml(28.2)).toContain(">28°<");
    expect(markerHtml(28, "selected")).toContain("tm-selected");
    expect(markerHtml(28, "dim")).toContain("tm-dim");
  });

  it("降雨環：長度＝降雨機率（限制在 0～100）、顏色依降雨色階；0% 或沒有降雨機率不畫", () => {
    const html = markerHtml(25, "normal", 70);
    expect(html).toContain("tm-has-rain");
    expect(html).toContain("--rain:70%");
    expect(html).toContain(`--rain-c:${rainColor(70)}`);
    expect(markerHtml(25, "normal", 130)).toContain("--rain:100%");
    expect(markerHtml(25, "normal", null)).not.toContain("tm-has-rain");
    expect(markerHtml(25, "normal", null)).not.toContain("--rain");
    expect(markerHtml(25, "normal", 0)).not.toContain("tm-has-rain");
    expect(markerHtml(25, "normal", 1)).toContain("--rain:1%");
  });

  it("全台視野（compact）時標記縮小 6px", () => {
    expect([markerSize("normal"), markerSize("selected")]).toEqual([38, 46]);
    expect([markerSize("normal", true), markerSize("selected", true)]).toEqual([32, 40]);
    expect(markerHtml(25, "normal", null, true)).toContain("tm-compact");
    expect(markerHtml(25, "normal", null, true)).toContain("--size:32px");
  });

  it("提示框：縣市、降雨機率，沒有值顯示「—」", () => {
    const row = cur()[0];
    const tip = tooltipHtml(row, 22.5);
    expect(tip).toContain(row.location_name);
    expect(tip).toContain("平均 <span style=\"color:#2b8a3e;font-weight:700\">22.5°C</span>");
    expect(tooltipHtml({ ...row, rain_probability: null }, 22.5)).toContain("降雨機率 —");
  });

  it("資料庫文字會跳脫，不會被當成 HTML", () => {
    expect(escapeHtml(`<b>"x" & 'y'</b>`)).toBe("&lt;b&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/b&gt;");
    expect(tooltipHtml({ ...cur()[0], weather_condition: "<img src=x>" }, 22)).toContain("&lt;img src=x&gt;");
  });

  it("圖例：四個級距的連續色條與分界刻度", () => {
    expect(LEGEND).toHaveLength(4);
    const g = legendGradient();
    expect(g.startsWith("linear-gradient(90deg, ")).toBe(true);
    for (const [color] of LEGEND) expect(g).toContain(color);
    expect(LEGEND_TICKS.map(legendTickPos)).toEqual([25, 50, 75]); // 15～35 °C 的色條上
  });
});
