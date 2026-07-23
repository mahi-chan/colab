// Preload bridge. Exposes a minimal, safe surface (`window.circuitlab`) to the
// renderer with contextIsolation on — the desktop PlatformAdapter calls these.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("circuitlab", {
  isDesktop: true,
  openProject: () => ipcRenderer.invoke("open-project"),
  saveProject: (text, suggestedName) => ipcRenderer.invoke("save-project", { text, suggestedName }),
});
