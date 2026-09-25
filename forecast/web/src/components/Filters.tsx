/** 地區與縣市篩選（互斥：選其一會把另一個清回「全部」）。

選了縣市時，地區選單顯示「— 已選縣市 —」而不是「全部地區」，這樣使用者再選「全部地區」才會觸發切換。
原生 <select> 在手機上是系統的選單，不會跳出鍵盤。
*/
import { ALL_CITIES, ALL_REGIONS, CITY_ORDER, REGION_NAMES } from "../lib/regions";
import { Scope } from "../lib/scope";

export function Filters({ scope, onChange }: { scope: Scope; onChange: (scope: Scope) => void }) {
  return (
    <div className="filters">
      <label>
        <span>地區</span>
        <select
          value={scope.city ? "" : scope.region}
          onChange={(e) => onChange(new Scope(e.target.value))}
        >
          {scope.city && <option value="" disabled>— 已選縣市 —</option>}
          {[ALL_REGIONS, ...REGION_NAMES].map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </label>
      <label>
        <span>縣市</span>
        <select
          value={scope.city ?? ALL_CITIES}
          onChange={(e) => onChange(e.target.value === ALL_CITIES ? new Scope() : new Scope(ALL_REGIONS, e.target.value))}
        >
          {[ALL_CITIES, ...CITY_ORDER].map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
    </div>
  );
}
