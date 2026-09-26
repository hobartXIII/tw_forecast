/** 告警設定的兩個視窗（對應 Python 的 admin_ui.AdminPanel.login_view／settings_view）。
狀態與資料庫呼叫在 hooks/useAdminSession.ts；這裡只負責畫面。 */
import { useState } from "react";

import type { AdminSession } from "../hooks/useAdminSession";
import {
  BOOL_LABELS, LIMITS, NUMBER_LABELS, SLOTS, setAllEnabled, type BoolField, type CitySetting, type NumberField,
} from "../lib/admin";
import { Modal } from "./Modal";
import { Notice } from "./Notice";

/** 表格欄位順序：每個條件的開關緊接著它的門檻。 */
const COLUMNS: ({ kind: "bool"; field: BoolField } | { kind: "number"; field: NumberField })[] = [
  { kind: "bool", field: "enabled" },
  { kind: "bool", field: "rain_enabled" }, { kind: "number", field: "rain_threshold" },
  { kind: "bool", field: "min_temp_enabled" }, { kind: "number", field: "min_temp_threshold" },
  { kind: "bool", field: "max_temp_enabled" }, { kind: "number", field: "max_temp_threshold" },
];

export function AdminDialogs({ session }: { session: AdminSession }) {
  if (session.view === "login") {
    return <Modal title="🔒 管理者登入" onClose={session.close}><LoginView session={session} /></Modal>;
  }
  if (session.view === "settings" && session.draft) {
    return <Modal title="⚙️ 告警設定" size="large" onClose={session.close}><SettingsView session={session} /></Modal>;
  }
  return null;
}

function LoginView({ session }: { session: AdminSession }) {
  const [password, setPassword] = useState("");
  return (
    <form
      className="admin-login"
      onSubmit={(e) => {
        e.preventDefault();
        const pw = password;
        setPassword(""); // 送出後清空輸入框
        void session.login(pw);
      }}
    >
      <label className="field">
        <span>管理者密碼</span>
        <input
          type="password" autoComplete="current-password" autoFocus value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </label>
      <p className="caption">輸入前請先把輸入法切成英文</p>
      {session.error && <Notice kind="error">{session.error}</Notice>}
      <button type="submit" className="primary wide" disabled={session.busy}>{session.busy ? "⏳ 驗證中…" : "登入"}</button>
    </form>
  );
}

function SettingsView({ session }: { session: AdminSession }) {
  const draft = session.draft!;
  const setCity = (i: number, patch: Partial<CitySetting>) =>
    session.edit({ ...draft, cities: draft.cities.map((c, j) => (j === i ? { ...c, ...patch } : c)) });

  return (
    <div className="admin-settings">
      <p className="caption">
        勾選「啟用」的縣市才會發送告警｜設定在下一個發送時段生效｜閒置超過 15 分鐘需重新登入｜關閉視窗會放棄未儲存的修改
      </p>
      {session.notice && <Notice kind="success">{session.notice}</Notice>}
      {session.error && <Notice kind="error">{session.error}</Notice>}
      {!draft.cities.some((c) => c.enabled) && <Notice kind="info">尚未啟用任何縣市，不會發送告警</Notice>}

      <h3>發送時段<span className="caption">（勾選的時段才會發送；視窗為「該時段到下一個勾選時段之前」）</span></h3>
      <div className="slot-row">
        {SLOTS.map((s) => (
          <label key={s}>
            <input
              type="checkbox" checked={draft.slots[s] ?? false}
              onChange={(e) => session.edit({ ...draft, slots: { ...draft.slots, [s]: e.target.checked } })}
            /> {s}
          </label>
        ))}
      </div>

      <h3>縣市設定<span className="caption">（降雨 ≥ 門檻、最低溫 ≤ 門檻、最高溫 ≥ 門檻，任一已勾選的條件符合就通知）</span></h3>
      <div className="table-wrap admin-table-wrap">
        <table className="forecast-table admin-table">
          <thead>
            <tr>
              <th>縣市</th>
              {COLUMNS.map((c) => <th key={c.field}>{c.kind === "bool" ? BOOL_LABELS[c.field] : NUMBER_LABELS[c.field]}</th>)}
            </tr>
          </thead>
          <tbody>
            {draft.cities.map((city, i) => (
              <tr key={city.location_name}>
                <td>{city.location_name}</td>
                {COLUMNS.map((c) => (
                  <td key={c.field}>
                    {c.kind === "bool" ? (
                      <input
                        type="checkbox" aria-label={`${city.location_name} ${BOOL_LABELS[c.field]}`} checked={city[c.field]}
                        onChange={(e) => setCity(i, { [c.field]: e.target.checked })}
                      />
                    ) : (
                      <input
                        type="number" className="num-input" aria-label={`${city.location_name} ${NUMBER_LABELS[c.field]}`}
                        min={LIMITS[c.field].min} max={LIMITS[c.field].max} step={LIMITS[c.field].step}
                        value={Number.isNaN(city[c.field]) ? "" : city[c.field]}
                        onChange={(e) => setCity(i, { [c.field]: e.target.value === "" ? NaN : Number(e.target.value) })}
                      />
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="admin-actions">
        <button type="button" className="primary" disabled={session.busy} onClick={() => void session.save()}>
          {session.busy ? "⏳ 處理中…" : "💾 儲存"}
        </button>
        <button type="button" disabled={session.busy} onClick={() => session.edit({ ...draft, cities: setAllEnabled(draft.cities, true) })}>
          全部啟用（尚未儲存）
        </button>
        <button type="button" disabled={session.busy} onClick={() => session.edit({ ...draft, cities: setAllEnabled(draft.cities, false) })}>
          全部關閉（尚未儲存）
        </button>
      </div>
      <div className="admin-actions">
        <button type="button" disabled={session.busy} onClick={() => void session.reload()}>重新載入（放棄未儲存的修改）</button>
        <button type="button" onClick={() => session.logout("已登出")}>登出</button>
      </div>
    </div>
  );
}
