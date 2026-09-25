/** 明細表格：溫度欄依級距上色，降雨機率以進度條呈現，點欄位標題可排序（再點一次反向）。 */
import { useMemo, useState } from "react";

import type { TableColumnKey } from "../lib/scope";
import { visibleColumns, type TableRow } from "../lib/tables";
import { textColor } from "../lib/temperature";

type Key = keyof TableRow;
const TEMP_DIGITS: Partial<Record<Key, number>> = { min: 0, max: 0, avg: 1 };

function compare(a: TableRow[Key], b: TableRow[Key]): number {
  if (a === b) return 0;
  if (a === null) return 1; // 沒有值的排最後
  if (b === null) return -1;
  return typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), "zh-Hant");
}

function Cell({ column, value }: { column: Key; value: TableRow[Key] }) {
  if (column in TEMP_DIGITS) {
    const v = value as number | null;
    if (v === null) return <>—</>;
    const color = textColor(v);
    return <span className="temp" style={color ? { color } : undefined}>{v.toFixed(TEMP_DIGITS[column])}</span>;
  }
  if (column === "rain") {
    const v = value as number | null;
    if (v === null) return null; // 空白：氣象署該時段未提供
    return (
      <span className="rain-cell">
        <span className="rain-bar"><span style={{ width: `${Math.min(Math.max(v, 0), 100)}%` }} /></span>
        <span>{v}%</span>
      </span>
    );
  }
  return <>{value ?? "—"}</>;
}

export function ForecastTable({ rows, drop }: { rows: TableRow[]; drop: TableColumnKey[] }) {
  const columns = visibleColumns(drop);
  const [sort, setSort] = useState<{ key: Key; desc: boolean } | null>(null);
  const sorted = useMemo(() => {
    if (!sort) return rows;
    return [...rows].sort((a, b) => (sort.desc ? -1 : 1) * compare(a[sort.key], b[sort.key]));
  }, [rows, sort]);

  return (
    <>
      <div className="table-wrap">
        <table className="forecast-table">
          <thead>
            <tr>
              {columns.map((c) => (
                <th
                  key={c.key}
                  aria-sort={sort?.key === c.key ? (sort.desc ? "descending" : "ascending") : undefined}
                  onClick={() => setSort(sort?.key === c.key ? { key: c.key, desc: !sort.desc } : { key: c.key, desc: false })}
                >
                  {c.label}
                  {sort?.key === c.key && (sort.desc ? " ▼" : " ▲")}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sorted.map((r, i) => (
              <tr key={`${r.city}-${r.period}-${i}`}>
                {columns.map((c) => <td key={c.key}><Cell column={c.key} value={r[c.key]} /></td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">點欄位標題可排序；降雨機率為空白表示氣象署該時段未提供；天氣圖示依時段區分日間（☀️）與夜間（🌙）。</p>
    </>
  );
}
