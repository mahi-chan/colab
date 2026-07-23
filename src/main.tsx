import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./ui/App";
import { getPlatform } from "./platform";
import { useProjectStore } from "./store/projectStore";
import "./index.css";

// Choose the platform adapter (web today; desktop when running inside Tauri).
getPlatform().then((platform) => {
  useProjectStore.getState().init(platform);
  ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
      <App />
    </React.StrictMode>,
  );
});
