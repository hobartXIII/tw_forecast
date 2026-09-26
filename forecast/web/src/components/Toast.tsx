/** 右下角的浮動提示（對應 st.toast），幾秒後自動消失。 */
import { useCallback, useEffect, useState } from "react";

export const TOAST_MS = 4000;

export function useToast() {
  const [toast, setToast] = useState<{ text: string; id: number } | null>(null);
  const show = useCallback((text: string) => setToast({ text, id: Date.now() + Math.random() }), []);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), TOAST_MS);
    return () => clearTimeout(t);
  }, [toast]);
  const node = toast && <div key={toast.id} className="toast" role="status">{toast.text}</div>;
  return { show, node };
}
