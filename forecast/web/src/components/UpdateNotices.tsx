/** 「立即更新」的提示訊息（對應 Python 的 views/header.py 與 countdown.py）。

優先順序：觸發失敗 → 觸發後的自動重新載入倒數 → 間隔倒數 → 其他不可更新的原因；
另外在觸發後重新載入時，顯示更新是否已完成。倒數的兩個數字都由同一個剩餘秒數推導（lib/countdown.ts），保證同步。
*/
import { useEffect, useState } from "react";

import type { UpdateFlow } from "../hooks/useUpdateFlow";
import { elapsedMinutes, formatMmss } from "../lib/countdown";
import { MIN_INTERVAL_MINUTES } from "../lib/updateGate";
import { Notice } from "./Notice";

/** 有 until 時每 250ms 重新渲染一次，回傳剩餘秒數。 */
function useSecondsLeft(until: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (until === null) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [until]);
  return until === null ? 0 : Math.max((until - now) / 1000, 0);
}

export function UpdateNotices({ flow }: { flow: UpdateFlow }) {
  const { status, waitUntil, refreshAt, error, pending } = flow;
  const refreshLeft = useSecondsLeft(refreshAt);
  const waitLeft = useSecondsLeft(refreshAt === null ? waitUntil : null);

  let main = null;
  if (error) {
    main = <Notice kind="error">{error}</Notice>;
  } else if (refreshAt !== null) {
    main = <Notice kind="info">已觸發更新，{Math.ceil(refreshLeft) || 1} 秒後自動重新載入資料…</Notice>;
  } else if (waitUntil !== null) {
    main = (
      <Notice kind="info">
        距上次更新僅 <b className="num">{elapsedMinutes(MIN_INTERVAL_MINUTES, waitLeft)}</b> 分鐘，需間隔 {MIN_INTERVAL_MINUTES} 分鐘，還需 <b className="num">{waitLeft > 0 ? formatMmss(waitLeft) : "重新確認中…"}</b> 才可更新
      </Notice>
    );
  } else if (status && !status.allowed) {
    main = <Notice kind="info">{status.message}</Notice>;
  }

  return (
    <>
      {main}
      {refreshAt === null && pending === "done" && <Notice kind="success">資料已更新完成</Notice>}
      {refreshAt === null && pending === "waiting" && <Notice kind="info">更新尚未完成，請稍後按「重新載入資料」</Notice>}
    </>
  );
}
