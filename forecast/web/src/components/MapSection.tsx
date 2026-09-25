/** 平均氣溫地圖區塊（對應 Python 的 views/map_section.py）。單一縣市時放大並加外框，其餘縣市淡化作為對照。 */
import type { Scope, ScopedRow } from "../lib/scope";
import { TemperatureMap } from "./TemperatureMap";

export const MAP_HEIGHT = 520;

export function MapSection({ cur, scope }: { cur: ScopedRow[]; scope: Scope }) {
  return (
    <section className="panel map-panel">
      <h2>🗺️ 平均氣溫地圖</h2>
      <p className="caption">
        手機請用兩指移動或縮放地圖（單指滑動是捲動頁面），電腦按住 Ctrl 再滾動滾輪縮放，也可用左上角的 ＋／－ 按鈕；
        滑鼠移到標記上可看詳細資料。
        {scope.city && `被選的縣市已放大並加外框，其餘${scope.homeRegion ?? ""}縣市淡化作為對照。`}
      </p>
      <TemperatureMap cur={cur} level={scope.level} highlight={scope.city} height={MAP_HEIGHT} />
    </section>
  );
}
