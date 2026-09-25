/** 地圖內容：標記、提示框、圖例、視野。對應 tests/frontend/test_charts_and_map.py 的地圖部分。 */
import { describe, expect, it } from "vitest";

import { LEGEND, TAIWAN_CENTER, escapeHtml, mapPoints, mapViewport, markerHtml, tooltipHtml } from "../src/lib/mapView";
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
  it("標記：級距底色、橙黃底用深色字、選中時加外框、淡化", () => {
    expect(markerHtml(28)).toContain("background:#f59f00");
    expect(markerHtml(28)).toContain("color:#222");
    expect(markerHtml(35)).toContain("color:#fff");
    expect(markerHtml(28.2)).toContain(">28°<");
    expect(markerHtml(28, "selected")).toContain("0 0 0 4px #1c7ed6");
    expect(markerHtml(28, "dim")).toContain("opacity:0.45");
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

  it("圖例列出四個級距", () => {
    expect(LEGEND).toHaveLength(4);
  });
});
