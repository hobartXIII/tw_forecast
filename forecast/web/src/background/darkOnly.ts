/** 背景流場粒子只在深色主題播放：看 <html data-theme>（lib/theme.ts 寫入的實際淺色或深色）決定開關。

- 深色：顯示畫布並 start()。
- 淺色：stop() 並隱藏畫布（hidden），淺色模式完全不跑動畫、不耗效能，畫面與原本相同。
主題按鈕切換、或「自動」時系統改深淺色，data-theme 都會變，這裡用 MutationObserver 即時跟著開關。
回傳解除監聽的函式（不會 destroy 背景物件）。
*/
export interface Playable {
  start(): void;
  stop(): void;
}

export function playInDarkOnly(bg: Playable, canvas: HTMLElement, root: HTMLElement = document.documentElement): () => void {
  const sync = () => {
    const dark = root.getAttribute("data-theme") === "dark";
    canvas.hidden = !dark;
    if (dark) bg.start();
    else bg.stop();
  };
  sync();
  const observer = new MutationObserver(sync);
  observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}
