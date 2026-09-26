import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { installTooltipAutoHide } from "./lib/tooltipAutoHide";
import "./styles/global.css";

installTooltipAutoHide();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
