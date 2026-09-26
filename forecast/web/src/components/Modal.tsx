/** 視窗（對應 st.dialog）：原生 <dialog> 的 modal 模式，按 Esc、右上角 ×、點視窗外都會關閉。
一次只開一個視窗；關閉時呼叫 onClose，由呼叫端決定要不要保留內容。 */
import { useEffect, useRef, type ReactNode } from "react";

export function Modal({ title, size = "small", onClose, children }: {
  title: string; size?: "small" | "large"; onClose: () => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (typeof d.showModal === "function") d.showModal();
    else d.setAttribute("open", ""); // 測試環境（jsdom）沒有 showModal
    return () => {
      if (typeof d.close === "function" && d.open) d.close();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className={`modal modal-${size}`}
      aria-label={title}
      onCancel={(e) => { e.preventDefault(); onClose(); }} // Esc：交給呼叫端關閉（卸載元件）
      onClick={(e) => { if (e.target === ref.current) onClose(); }} // 點到視窗外（::backdrop 也算 dialog 本身）
    >
      <div className="modal-body">
        <header className="modal-header">
          <h2>{title}</h2>
          <button type="button" className="modal-close" aria-label="關閉" onClick={onClose}>✕</button>
        </header>
        {children}
      </div>
    </dialog>
  );
}
