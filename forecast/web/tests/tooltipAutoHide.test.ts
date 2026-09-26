// @vitest-environment jsdom
/** 捲動時收起圖表提示框（對應 Streamlit 版 style.py 的 TOOLTIP_JS）。 */
import { afterEach, describe, expect, it } from "vitest";

import { TOOLTIP_ID, installTooltipAutoHide } from "../src/lib/tooltipAutoHide";

function tooltip(): HTMLElement {
  const el = document.createElement("div");
  el.id = TOOLTIP_ID;
  el.classList.add("visible");
  document.body.append(el);
  return el;
}

let uninstall: (() => void) | undefined;
afterEach(() => {
  uninstall?.();
  document.body.innerHTML = "";
});

describe("installTooltipAutoHide", () => {
  it("內部捲動區捲動（不冒泡）或手指滑動時收起提示框", () => {
    uninstall = installTooltipAutoHide();
    const tip = tooltip();
    const inner = document.createElement("div");
    document.body.append(inner);
    inner.dispatchEvent(new Event("scroll", { bubbles: false }));
    expect(tip.classList.contains("visible")).toBe(false);

    tip.classList.add("visible");
    document.body.dispatchEvent(new Event("touchmove", { bubbles: true }));
    expect(tip.classList.contains("visible")).toBe(false);
  });

  it("沒有提示框時不出錯；解除後不再收起", () => {
    uninstall = installTooltipAutoHide();
    document.dispatchEvent(new Event("scroll"));
    uninstall();
    uninstall = undefined;
    const tip = tooltip();
    document.dispatchEvent(new Event("scroll"));
    expect(tip.classList.contains("visible")).toBe(true);
  });
});
