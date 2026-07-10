import { StrictMode } from "react";
import { createRoot, type Root } from "react-dom/client";
import { App } from "./App";
import "./styles/index.css";

const rootElement = document.getElementById("root") as HTMLElement & { dashboardRoot?: Root };
const root = rootElement.dashboardRoot ?? createRoot(rootElement);
rootElement.dashboardRoot = root;

root.render(
  <StrictMode>
    <App />
  </StrictMode>,
);
