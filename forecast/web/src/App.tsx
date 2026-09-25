/** 儀表板（對應 Streamlit 版的 streamlit_app/app.py）。

由上而下：[A] 標題與按鈕、[C] 最近更新時間、[D] 地區／縣市篩選、[E] 預報時段與過期警示、
[F] 摘要卡片、[H] 分頁。[G] 地圖在階段 3 加入。
資料在載入頁面與按「重新載入資料」時從 Supabase 重新查詢（不快取）；篩選只在瀏覽器端重新整理資料，不重新查詢。
*/
import { useCallback, useEffect, useMemo, useState } from "react";

import { DateQueryTab } from "./components/DateQueryTab";
import { Filters } from "./components/Filters";
import { Notice } from "./components/Notice";
import { SummaryCards } from "./components/SummaryCards";
import { NextTab, TableTab } from "./components/TableTabs";
import { Tabs, type TabItem } from "./components/Tabs";
import { RainTab, TemperatureTab } from "./components/Trends";
import { formatLastUpdate, formatRange } from "./lib/formatting";
import { ForecastQuery, type StatusRow } from "./lib/repository";
import { addRegion, withAvg, type CityRow, type Scope } from "./lib/scope";
import { summaryCards } from "./lib/summary";
import { supabase } from "./lib/supabase";
import { formatMDHM } from "./lib/time";
import { scopeFromSearch, searchFromScope } from "./lib/urlState";

interface Loaded {
  now: Date;
  status: StatusRow[] | null; // 讀不到為 null（不影響其他區塊）
  current: CityRow[];
  forecast: CityRow[];
}

type Data = { kind: "loading" } | { kind: "error"; message: string } | { kind: "ok"; loaded: Loaded };

async function load(query: ForecastQuery): Promise<Loaded> {
  const now = new Date();
  const [status, current, forecast] = await Promise.all([
    query.updateStatus().catch(() => null),
    query.current(now),
    query.forecast(now),
  ]);
  return { now, status, current: addRegion(current), forecast: addRegion(forecast) };
}

export default function App() {
  const query = useMemo(() => (supabase ? new ForecastQuery(supabase) : null), []);
  const [data, setData] = useState<Data>({ kind: "loading" });
  const [reloading, setReloading] = useState(false);
  const [scope, setScope] = useState<Scope>(() => scopeFromSearch(window.location.search));

  const reload = useCallback(() => {
    if (!query) return;
    setReloading(true);
    load(query)
      .then((loaded) => setData({ kind: "ok", loaded }))
      .catch((e: unknown) => setData({ kind: "error", message: `讀取資料庫失敗：${e instanceof Error ? e.message : e}` }))
      .finally(() => setReloading(false));
  }, [query]);

  useEffect(reload, [reload]);

  const changeScope = (next: Scope) => {
    setScope(next);
    window.history.replaceState(null, "", `${window.location.pathname}${searchFromScope(next)}`);
  };

  return (
    <main className="page">
      {/* [A] 標題、[B] 按鈕 */}
      <header className="page-header">
        <h1>🌤️ 台灣天氣預報</h1>
        <div className="header-actions">
          <button type="button" onClick={reload} disabled={!query || reloading}>
            {reloading ? "⏳ 載入中…" : "♻️ 重新載入資料"}
          </button>
        </div>
      </header>

      {!query ? (
        <Notice kind="error">尚未設定 VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY（見 web/.env.example）</Notice>
      ) : data.kind === "loading" ? (
        <p className="caption">讀取預報資料中…</p>
      ) : data.kind === "error" ? (
        <Notice kind="error">{data.message}</Notice>
      ) : (
        <Dashboard loaded={data.loaded} scope={scope} onScopeChange={changeScope} query={query} />
      )}
    </main>
  );
}

function Dashboard({ loaded, scope, onScopeChange, query }: {
  loaded: Loaded; scope: Scope; onScopeChange: (s: Scope) => void; query: ForecastQuery;
}) {
  const { now, status, current, forecast } = loaded;
  const cur = useMemo(() => withAvg(scope.filterCurrent(current)), [scope, current]);
  const fc = useMemo(() => scope.filterForecast(forecast), [scope, forecast]);

  const statusLine = status && (
    <p className="caption">
      最近排程更新 {formatLastUpdate(status, "schedule")}　｜　最近手動更新 {formatLastUpdate(status, "manual")}
    </p>
  );

  if (!current.length) {
    return <>{statusLine}<Notice kind="warning">資料庫目前沒有預報資料，請先執行流程一（GitHub Actions）。</Notice></>;
  }

  const body = () => {
    if (!cur.length) return <Notice kind="warning">此範圍目前沒有資料。</Notice>;
    const start = cur[0].forecast_time_start;
    const end = cur[0].forecast_time_end;
    const updated = new Date(Math.max(...cur.map((r) => r.updated_at.getTime())));
    const tabs: TabItem[] = [
      { label: "📈 氣溫趨勢", render: () => <TemperatureTab scope={scope} fc={fc} now={now} /> },
      { label: "🌧️ 降雨機率", render: () => <RainTab scope={scope} fc={fc} now={now} /> },
      { label: scope.city ? "📋 一週預報" : "📋 目前時段明細", render: () => <TableTab scope={scope} cur={cur} fc={fc} /> },
      ...(scope.city ? [] : [{ label: "🕒 後續時段", render: () => <NextTab scope={scope} fc={fc} after={start} /> }]),
      { label: "📅 日期查詢", render: () => <DateQueryTab scope={scope} query={query} now={now} /> },
    ];
    return (
      <>
        {/* [E] 預報時段與資料更新時間；目前時間不在該時段內時顯示過期警示 */}
        <p className="caption">
          預報時段 <b>{formatRange(start, end)}</b>　｜　資料更新 <b>{formatMDHM(updated)}</b>　｜　時間皆為台灣時間
        </p>
        {!(start <= now && now < end) && (
          <Notice kind="warning">
            目前沒有涵蓋此刻的預報時段，顯示的是最接近的時段。資料可能已過期，請等待下次排程更新（每 3 小時一次）。
          </Notice>
        )}
        <SummaryCards cards={summaryCards(cur, scope)} />{/* [F] */}
        <section className="panel"><Tabs items={tabs} /></section>{/* [H] */}
      </>
    );
  };

  return (
    <>
      {statusLine}{/* [C] */}
      <Filters scope={scope} onChange={onScopeChange} />{/* [D] */}
      {body()}
    </>
  );
}
