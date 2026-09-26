/** 摘要輪播的換頁規則：頁碼循環、手指滑動方向。 */
import { describe, expect, it } from "vitest";

import { SWIPE_THRESHOLD_PX, swipeStep, wrapIndex } from "../src/lib/carousel";

describe("wrapIndex", () => {
  it.each([[0, 4, 0], [3, 4, 3], [4, 4, 0], [-1, 4, 3], [9, 4, 1], [2, 0, 0]])("wrapIndex(%i, %i) = %i", (i, n, want) => {
    expect(wrapIndex(i, n)).toBe(want);
  });
});

describe("swipeStep", () => {
  it("往左滑看下一張、往右滑看上一張", () => {
    expect(swipeStep(-SWIPE_THRESHOLD_PX)).toBe(1);
    expect(swipeStep(80)).toBe(-1);
  });

  it("位移不夠遠或以垂直為主（捲動頁面）不換頁", () => {
    expect(swipeStep(-(SWIPE_THRESHOLD_PX - 1))).toBe(0);
    expect(swipeStep(-60, 90)).toBe(0);
  });
});
