/** 明細相關分頁：一週預報／目前時段明細、後續時段。 */
import type { Scope, ScopedRow } from "../lib/scope";
import { makeTable, nextPeriods } from "../lib/tables";
import { ForecastTable } from "./ForecastTable";
import { Notice } from "./Notice";
import { STALE_FORECAST } from "./Trends";

/** 單一縣市：該縣市所有尚未結束的時段（一週預報）；其他範圍：目前時段的各縣市明細。 */
export function TableTab({ scope, cur, fc }: { scope: Scope; cur: ScopedRow[]; fc: ScopedRow[] | null }) {
  if (scope.city) {
    return (
      <>
        <p className="caption">{scope.city}｜未來一週的預報（每個時段約 12 小時）</p>
        {fc ? (
          <ForecastTable
            rows={makeTable([...fc].sort((a, b) => a.forecast_time_start.getTime() - b.forecast_time_start.getTime()), true)}
            drop={scope.tableDropColumns()}
          />
        ) : <Notice kind="info">{STALE_FORECAST}</Notice>}
      </>
    );
  }
  return <ForecastTable rows={makeTable(cur, false)} drop={scope.tableDropColumns()} />;
}

/** 每個縣市「目前時段」之後的 2 個時段（僅全台／地區有這個分頁）。 */
export function NextTab({ scope, fc, after }: { scope: Scope; fc: ScopedRow[] | null; after: Date }) {
  const later = fc ? nextPeriods(fc, after) : [];
  return (
    <>
      <p className="caption">每個縣市「目前時段」之後的 2 個時段（依縣市、時間排序）</p>
      {later.length ? (
        <ForecastTable rows={makeTable(later, true)} drop={scope.tableDropColumns()} />
      ) : (
        <Notice kind="info">沒有後續時段的預報資料（資料可能已過期），請等待下次排程更新（每 3 小時一次）。</Notice>
      )}
    </>
  );
}
