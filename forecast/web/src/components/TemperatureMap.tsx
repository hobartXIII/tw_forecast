/** 平均氣溫地圖（Leaflet）。標記、提示框、視野由 lib/mapView.ts 決定。

手勢（leaflet-gesture-handling）：手機單指滑動是捲動頁面、雙指才操作地圖，電腦滾輪要按 Ctrl 才縮放。
這個外掛依賴全域的 L，所以先載入 Leaflet、設定 window.L 再載入外掛；兩者都在第一次顯示地圖時才載入。
建立地圖時帶 gestureHandling: true 即啟用。
*/
import "leaflet/dist/leaflet.css";
import "leaflet-gesture-handling/dist/leaflet-gesture-handling.css";

import type * as Leaflet from "leaflet";
import { useEffect, useRef, useState } from "react";

import {
  GESTURE_TEXT, LEGEND, mapPoints, mapViewport, markerHtml, markerSize, tooltipHtml,
} from "../lib/mapView";
import type { Level, ScopedRow } from "../lib/scope";

let leafletReady: Promise<typeof Leaflet> | null = null;

function loadLeaflet(): Promise<typeof Leaflet> {
  leafletReady ??= (async () => {
    const L = (await import("leaflet")).default;
    (window as unknown as { L: typeof Leaflet }).L = L;
    await import("leaflet-gesture-handling"); // 載入時會自行向 L.Map 登記 gestureHandling
    return L;
  })();
  return leafletReady;
}

export function TemperatureMap({ cur, level, highlight, height }: {
  cur: ScopedRow[]; level: Level; highlight: string | null; height: number;
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<Leaflet.Map | null>(null);
  const markers = useRef<Leaflet.LayerGroup | null>(null);
  const [L, setL] = useState<typeof Leaflet | null>(null); // 地圖建立後才有值

  // 建立地圖（只做一次）
  useEffect(() => {
    let cancelled = false;
    loadLeaflet().then((L) => {
      if (cancelled || !container.current) return;
      map.current = L.map(container.current, {
        zoomControl: true,
        gestureHandling: true,
        // 要一併給 duration：這個物件會整個取代外掛的預設值，少了 duration 提示會一出現就消失
        gestureHandlingOptions: { text: GESTURE_TEXT, duration: 1000 },
      } as Leaflet.MapOptions);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18, attribution: "&copy; OpenStreetMap contributors",
      }).addTo(map.current);
      markers.current = L.layerGroup().addTo(map.current);
      setL(() => L);
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, []);

  // 依資料與範圍重畫標記、調整視野
  useEffect(() => {
    if (!L || !map.current || !markers.current) return;
    markers.current.clearLayers();
    const points = mapPoints(cur, highlight);
    const rows = new Map(cur.map((r) => [r.location_name, r]));
    for (const p of points) {
      const half = markerSize(p.state) / 2;
      L.marker([p.lat, p.lng], {
        icon: L.divIcon({
          html: markerHtml(p.temp, p.state), className: "temp-marker",
          iconSize: [half * 2, half * 2], iconAnchor: [half, half],
          tooltipAnchor: [half, 0], // 提示框貼在標記左右側（依位置自動選邊），不會被地圖上緣切掉
        }),
        zIndexOffset: p.state === "selected" ? 1000 : 0,
      })
        .bindTooltip(tooltipHtml(rows.get(p.city)!, p.temp), { className: "map-tooltip", direction: "auto" })
        .addTo(markers.current);
    }
    const view = mapViewport(points, level);
    if (view.kind === "center") map.current.setView(view.center, view.zoom);
    else map.current.fitBounds(view.bounds, { padding: [40, 40], maxZoom: 10 });
  }, [L, cur, level, highlight]);

  return (
    <div className="map-wrap" style={{ height }}>
      <div ref={container} className="map" />
      <div className="map-legend">
        <b>平均氣溫</b>
        {LEGEND.map(([color, label]) => (
          <div key={label}><span className="legend-dot" style={{ background: color }} />{label}</div>
        ))}
      </div>
    </div>
  );
}
