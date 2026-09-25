/** 階段 0：確認 Vercel → Supabase 的整條路是通的（顯示資料筆數與最近一次成功更新時間）。 */
import { useEffect, useState } from "react";

import { FORECAST_TABLE, STATUS_TABLE } from "./lib/config";
import { supabase } from "./lib/supabase";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ok"; count: number; lastSuccess: string | null };

async function loadSummary(): Promise<State> {
  if (!supabase) return { kind: "error", message: "尚未設定 VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY" };
  const [rows, status] = await Promise.all([
    supabase.from(FORECAST_TABLE).select("*", { count: "exact", head: true }),
    supabase.from(STATUS_TABLE).select("last_success_at"),
  ]);
  const error = rows.error ?? status.error;
  if (error) return { kind: "error", message: `讀取資料庫失敗：${error.message}` };
  const times = (status.data ?? []).map((r) => r.last_success_at as string | null).filter((t) => t !== null);
  const lastSuccess = times.length ? times.reduce((a, b) => (new Date(a) > new Date(b) ? a : b)) : null;
  return { kind: "ok", count: rows.count ?? 0, lastSuccess };
}

function formatTaipei(iso: string): string {
  return new Date(iso).toLocaleString("zh-TW", { timeZone: "Asia/Taipei", hour12: false });
}

export default function App() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    loadSummary().then(setState, (e: unknown) => setState({ kind: "error", message: String(e) }));
  }, []);

  return (
    <main className="page">
      <h1>🌤️ 台灣天氣預報</h1>
      <p className="note">Vercel 版（建置中，階段 0：連線測試）</p>
      {state.kind === "loading" && <p>讀取中…</p>}
      {state.kind === "error" && <p className="error">{state.message}</p>}
      {state.kind === "ok" && (
        <ul>
          <li>資料表 <code>{FORECAST_TABLE}</code> 共 {state.count} 筆</li>
          <li>最近一次成功更新：{state.lastSuccess ? formatTaipei(state.lastSuccess) : "—"}（台灣時間）</li>
        </ul>
      )}
    </main>
  );
}
