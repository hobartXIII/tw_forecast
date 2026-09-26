/** 告警設定的登入狀態與視窗流程（對應 Python 的 admin_ui.AdminPanel 與 views/admin_dialogs.py）。

- 密碼只放在這個頁面的記憶體（useRef），不寫入 localStorage、不顯示；閒置超過 15 分鐘、登出、
  關閉或重新整理分頁即清除（VERCEL_PLAN.md §6 選 A）。
- 按「⚙️ 告警設定」：未登入開登入視窗；已登入則從資料庫重讀設定再開設定視窗
  （關閉視窗後未儲存的修改不保留，也能反映在 SQL Editor 直接改過的值）。
- 連續登入失敗越多次，下次送出前等越久（最多 5 秒；資料庫端另有 1 秒延遲）。
*/
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  AdminError, AlertSettingsService, IDLE_TIMEOUT_MS, WrongPassword, type AlertSettings,
} from "../lib/admin";
import type { SupabaseClient } from "@supabase/supabase-js";

export type AdminView = "closed" | "login" | "settings";
const IDLE_CHECK_MS = 15_000;
const MAX_FAIL_DELAY_S = 5;

const message = (e: unknown) => (e instanceof AdminError ? e.message : "發生未預期的錯誤");
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export interface AdminSession {
  view: AdminView;
  /** 設定視窗裡正在編輯的內容（尚未儲存）。 */
  draft: AlertSettings | null;
  busy: boolean;
  /** 視窗內的提示：成功為 notice，失敗為 error。 */
  notice: string | null;
  error: string | null;
  open: () => void;
  close: () => void;
  login: (password: string) => Promise<void>;
  edit: (draft: AlertSettings) => void;
  save: () => Promise<void>;
  reload: () => Promise<void>;
  logout: (toast?: string) => void;
}

export function useAdminSession(sb: Pick<SupabaseClient, "rpc"> | null, toast: (text: string) => void): AdminSession {
  const service = useMemo(() => (sb ? new AlertSettingsService(sb) : null), [sb]);
  const password = useRef<string | null>(null);
  const lastSeen = useRef(0);
  const fails = useRef(0);
  const [view, setView] = useState<AdminView>("closed");
  const [draft, setDraft] = useState<AlertSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const feedback = (n: string | null, e: string | null) => { setNotice(n); setError(e); };
  const touch = () => { lastSeen.current = Date.now(); };

  const logout = useCallback((text?: string) => {
    password.current = null;
    setDraft(null);
    setView("closed");
    setNotice(null);
    setError(null);
    if (text) toast(text);
  }, [toast]);

  /** 已登入且沒有閒置逾時；逾時會登出並提示。 */
  const loggedIn = useCallback(() => {
    if (password.current === null) return false;
    if (Date.now() - lastSeen.current > IDLE_TIMEOUT_MS) {
      logout("已因閒置超過 15 分鐘登出，請重新登入");
      return false;
    }
    return true;
  }, [logout]);

  // 已登入時定期檢查閒置（視窗關著也會登出，下次按按鈕要重新登入）
  useEffect(() => {
    const t = setInterval(() => { if (password.current !== null) loggedIn(); }, IDLE_CHECK_MS);
    return () => clearInterval(t);
  }, [loggedIn]);

  const open = useCallback(() => {
    if (!service) return;
    feedback(null, null);
    if (!loggedIn()) {
      setView("login");
      return;
    }
    touch();
    setBusy(true);
    service.getSettings(password.current!).then(
      (s) => { setDraft(s); setView("settings"); },
      (e) => {
        if (e instanceof WrongPassword) logout("密碼已失效，請重新登入");
        else toast(message(e));
        setView("login");
      },
    ).finally(() => setBusy(false));
  }, [service, loggedIn, logout, toast]);

  const close = useCallback(() => {
    setView("closed");
    setDraft(null); // 放棄未儲存的修改
    feedback(null, null);
  }, []);

  const login = useCallback(async (pw: string) => {
    if (!service) return;
    if (!pw) {
      feedback(null, "請輸入密碼");
      return;
    }
    setBusy(true);
    feedback(null, null);
    try {
      const delay = Math.min(fails.current, MAX_FAIL_DELAY_S);
      if (delay) await sleep(delay * 1000);
      const s = await service.getSettings(pw);
      password.current = pw;
      fails.current = 0;
      touch();
      setDraft(s);
      setView("settings");
    } catch (e) {
      if (e instanceof WrongPassword) fails.current += 1;
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }, [service]);

  const edit = useCallback((d: AlertSettings) => {
    if (!loggedIn()) return;
    touch();
    setDraft(d);
  }, [loggedIn]);

  const reload = useCallback(async () => {
    if (!service || !loggedIn()) return;
    touch();
    setBusy(true);
    try {
      setDraft(await service.getSettings(password.current!));
      feedback("已重新載入", null);
    } catch (e) {
      logout(e instanceof WrongPassword ? "密碼已失效，請重新登入" : message(e));
    } finally {
      setBusy(false);
    }
  }, [service, loggedIn, logout]);

  const save = useCallback(async () => {
    if (!service || !draft || !loggedIn()) return;
    touch();
    setBusy(true);
    try {
      await service.saveSettings(password.current!, draft);
      setDraft(await service.getSettings(password.current!)); // 以資料庫實際存下的值為準
      feedback("已儲存，設定會在下一個發送時段生效", null);
    } catch (e) {
      if (e instanceof WrongPassword) logout("密碼已失效，請重新登入");
      else feedback(null, `儲存失敗：${message(e)}`);
    } finally {
      setBusy(false);
    }
  }, [service, draft, loggedIn, logout]);

  return { view, draft, busy, notice, error, open, close, login, edit, save, reload, logout };
}
