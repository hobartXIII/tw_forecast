import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { playInDarkOnly } from "./background/darkOnly";
import { ParticleBackground } from "./background/particle-background";
import { initTheme } from "./lib/theme";
import { installTooltipAutoHide } from "./lib/tooltipAutoHide";
import "./styles/global.css";

initTheme();

// 背景流場粒子（只在深色主題播放）：框架無關的類別，整頁只有一個，不隨 React 重新渲染。
// 畫布取不到 2D context（極少數環境）時略過，只剩靜態漸層
const canvas = document.querySelector<HTMLCanvasElement>(".pb-canvas");
if (canvas) {
  try {
    playInDarkOnly(new ParticleBackground(canvas), canvas);
  } catch {
    canvas.remove();
  }
}
installTooltipAutoHide();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
