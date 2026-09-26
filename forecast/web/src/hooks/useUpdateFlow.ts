/** 「立即更新」的流程狀態（對應 Python 的 views/header.py 的 Header.handle）。

- 載入頁面、按「重新載入資料」、倒數結束時都重新查 /api/update-status。
- 距上次更新不滿間隔：在剩餘時間 + 1 秒後自動再查一次，按鈕就會變成可按（倒數文字由 UpdateNotices 每秒更新）。
- 觸發成功：按鈕改為「更新中…」，倒數 REFRESH_AFTER_SECONDS 秒後重新載入資料與狀態，
  再以伺服器時間比對是否已有觸發之後的成功更新，顯示「已更新完成」或「尚未完成」。
*/
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchUpdateStatus, requestDispatch, type ClientUpdateStatus } from "../lib/updateApi";

export const REFRESH_AFTER_SECONDS = 60;

export type PendingResult = "done" | "waiting" | null;

export interface UpdateFlow {
  status: ClientUpdateStatus | null; // null = 查詢中
  /** 間隔倒數結束的時間（Date.now() 的毫秒）；沒有被間隔擋住為 null。 */
  waitUntil: number | null;
  /** 觸發後自動重新載入的時間；沒有在倒數為 null。 */
  refreshAt: number | null;
  dispatching: boolean;
  error: string | null;
  pending: PendingResult;
  trigger: () => void;
  /** 重新載入資料（onReloadData）並重新查更新狀態。 */
  reloadAll: () => void;
}

export function useUpdateFlow(onReloadData: () => void): UpdateFlow {
  const [status, setStatus] = useState<ClientUpdateStatus | null>(null);
  const [waitUntil, setWaitUntil] = useState<number | null>(null);
  const [refreshAt, setRefreshAt] = useState<number | null>(null);
  const [dispatching, setDispatching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingResult>(null);
  const pendingSince = useRef<Date | null>(null); // 觸發當下的伺服器時間
  const latest = useRef(0); // 只採用最後一次查詢的結果

  const apply = useCallback((s: ClientUpdateStatus) => {
    setStatus(s);
    setWaitUntil(s.waitSeconds !== null ? Date.now() + s.waitSeconds * 1000 : null);
    const since = pendingSince.current;
    if (since) {
      const done = s.lastSuccess !== null && s.lastSuccess >= since;
      setPending(done ? "done" : "waiting");
      if (done) pendingSince.current = null;
    }
  }, []);

  const loadStatus = useCallback(() => {
    const id = ++latest.current;
    fetchUpdateStatus().then((s) => id === latest.current && apply(s));
  }, [apply]);

  useEffect(loadStatus, [loadStatus]);

  const reloadAll = useCallback(() => {
    setError(null);
    if (!pendingSince.current) setPending(null);
    onReloadData();
    loadStatus();
  }, [onReloadData, loadStatus]);

  // 間隔倒數結束：多等 1 秒（確保伺服器判斷時已過門檻）再查一次
  useEffect(() => {
    if (waitUntil === null) return;
    const t = setTimeout(loadStatus, Math.max(waitUntil - Date.now(), 0) + 1000);
    return () => clearTimeout(t);
  }, [waitUntil, loadStatus]);

  // 觸發後倒數結束：重新載入資料與狀態
  useEffect(() => {
    if (refreshAt === null) return;
    const t = setTimeout(() => {
      setRefreshAt(null);
      reloadAll();
    }, Math.max(refreshAt - Date.now(), 0));
    return () => clearTimeout(t);
  }, [refreshAt, reloadAll]);

  const trigger = useCallback(() => {
    setDispatching(true);
    setError(null);
    setPending(null);
    requestDispatch().then((r) => {
      setDispatching(false);
      if (r.status) {
        setStatus(r.status);
        setWaitUntil(r.status.waitSeconds !== null ? Date.now() + r.status.waitSeconds * 1000 : null);
      }
      if (r.ok) {
        pendingSince.current = r.status?.checkedAt ?? new Date();
        setRefreshAt(Date.now() + REFRESH_AFTER_SECONDS * 1000);
      } else {
        setError(r.message);
      }
    });
  }, []);

  return { status, waitUntil, refreshAt, dispatching, error, pending, trigger, reloadAll };
}
