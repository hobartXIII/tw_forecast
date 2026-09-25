/** 「日期查詢」分頁：選一天，只列該天的表格（範圍跟著上方的地區／縣市）；沒有折線圖。 */
import { useEffect, useState } from "react";

import { CITY_ORDER } from "../lib/regions";
import type { ForecastQuery } from "../lib/repository";
import { addRegion, withAvg, type Scope } from "../lib/scope";
import { makeTable, type TableRow } from "../lib/tables";
import { dateKey, dateLabel } from "../lib/time";
import { ForecastTable } from "./ForecastTable";
import { Notice } from "./Notice";

type Dates = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; dates: string[] };
type Day = { kind: "idle" } | { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; rows: TableRow[] };

export function DateQueryTab({ scope, query, now }: { scope: Scope; query: ForecastQuery; now: Date }) {
  const [dates, setDates] = useState<Dates>({ kind: "loading" });
  const [picked, setPicked] = useState<string>("");
  const [day, setDay] = useState<Day>({ kind: "idle" });

  useEffect(() => {
    let cancelled = false;
    query.availableDates(now, CITY_ORDER[0]).then(
      (list) => !cancelled && setDates({ kind: "ok", dates: list }),
      (e: unknown) => !cancelled && setDates({ kind: "error", message: `讀取可選日期失敗：${e instanceof Error ? e.message : e}` }),
    );
    return () => { cancelled = true; };
  }, [query, now]);

  useEffect(() => {
    if (!picked) {
      setDay({ kind: "idle" });
      return;
    }
    let cancelled = false;
    setDay({ kind: "loading" });
    query.day(picked, scope.cities).then(
      (rows) => {
        if (cancelled) return;
        const sorted = withAvg(addRegion(rows)).sort(
          (a, b) => a.order - b.order || a.forecast_time_start.getTime() - b.forecast_time_start.getTime());
        setDay({ kind: "ok", rows: makeTable(sorted, true) });
      },
      (e: unknown) => !cancelled && setDay({ kind: "error", message: `讀取 ${picked} 的資料失敗：${e instanceof Error ? e.message : e}` }),
    );
    return () => { cancelled = true; };
  }, [query, picked, scope]);

  if (dates.kind === "loading") return <p className="caption">讀取可選日期中…</p>;
  if (dates.kind === "error") return <Notice kind="error">{dates.message}</Notice>;
  if (!dates.dates.length) return <Notice kind="info">資料庫沒有可查詢的日期。</Notice>;

  const today = dateKey(now);
  return (
    <>
      <label className="field">
        <span>日期（今天前 3 天到後 7 天內、資料庫有資料的日期）</span>
        <select value={picked} onChange={(e) => setPicked(e.target.value)}>
          <option value="" disabled>請選擇日期</option>
          {dates.dates.map((d) => <option key={d} value={d}>{dateLabel(d, today)}</option>)}
        </select>
      </label>
      {day.kind === "loading" && <p className="caption">讀取中…</p>}
      {day.kind === "error" && <Notice kind="error">{day.message}</Notice>}
      {day.kind === "ok" && (day.rows.length ? (
        <>
          <p className="caption">
            {scope.label}｜{picked} 的預報存檔（僅含完整 12 小時時段，不含被縮短的時段；預報值，非實測值；夜間時段以起點日期歸屬）
          </p>
          <ForecastTable rows={day.rows} drop={scope.tableDropColumns()} />
        </>
      ) : <Notice kind="info">{picked} 在此範圍沒有資料。</Notice>)}
    </>
  );
}
