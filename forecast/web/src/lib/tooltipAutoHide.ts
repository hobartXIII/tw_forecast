/** 捲動時收起圖表提示框（手機用，對應 Streamlit 版 style.py 的 TOOLTIP_JS）。

手機上點折線圖的資料點會跳出 Vega 提示框（#vg-tooltip-element，出現時帶 visible class），
但手機沒有「滑鼠移開」，提示框會一直掛著。這裡在任何捲動或手指滑動時把它收起來，再點資料點仍會照常出現。
用 capture 監聽，表格等內部捲動區的 scroll 事件（不冒泡）也收得到。回傳解除監聽的函式。
*/
export const TOOLTIP_ID = "vg-tooltip-element";

export function installTooltipAutoHide(doc: Document = document): () => void {
  const hide = () => doc.getElementById(TOOLTIP_ID)?.classList.remove("visible");
  const options = { capture: true, passive: true } as const;
  doc.addEventListener("scroll", hide, options);
  doc.addEventListener("touchmove", hide, options);
  return () => {
    doc.removeEventListener("scroll", hide, options);
    doc.removeEventListener("touchmove", hide, options);
  };
}
