import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { initTheme } from "./lib/theme";
import { installTooltipAutoHide } from "./lib/tooltipAutoHide";
import "./styles/global.css";

initTheme();
installTooltipAutoHide();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
