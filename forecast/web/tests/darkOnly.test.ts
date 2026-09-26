// @vitest-environment jsdom
/** 背景粒子只在深色主題播放：依 <html data-theme> 開關，淺色時停止並隱藏畫布。 */
import { describe, expect, it, vi } from "vitest";

import { playInDarkOnly } from "../src/background/darkOnly";

const tick = () => new Promise((r) => setTimeout(r, 0)); // MutationObserver 是非同步回呼

describe("playInDarkOnly", () => {
  it("淺色時停止並隱藏；切到深色時顯示並播放；再切回淺色又停止", async () => {
    const root = document.createElement("html");
    root.setAttribute("data-theme", "light");
    const canvas = document.createElement("canvas");
    const bg = { start: vi.fn(), stop: vi.fn() };
    const off = playInDarkOnly(bg, canvas, root);
    expect([canvas.hidden, bg.start.mock.calls.length, bg.stop.mock.calls.length]).toEqual([true, 0, 1]);

    root.setAttribute("data-theme", "dark");
    await tick();
    expect([canvas.hidden, bg.start.mock.calls.length]).toEqual([false, 1]);

    root.setAttribute("data-theme", "light");
    await tick();
    expect([canvas.hidden, bg.stop.mock.calls.length]).toEqual([true, 2]);

    off();
    root.setAttribute("data-theme", "dark");
    await tick();
    expect(bg.start.mock.calls.length).toBe(1); // 解除監聽後不再開關
  });

  it("一開始就是深色時直接播放", () => {
    const root = document.createElement("html");
    root.setAttribute("data-theme", "dark");
    const bg = { start: vi.fn(), stop: vi.fn() };
    const canvas = document.createElement("canvas");
    playInDarkOnly(bg, canvas, root)();
    expect([canvas.hidden, bg.start.mock.calls.length]).toEqual([false, 1]);
  });
});
