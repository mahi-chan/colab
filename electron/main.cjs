// CircuitLab desktop main process (Electron). Loads the identical web frontend
// (dev server in development, bundled dist/ in production) inside a native
// window, and exposes native Open/Save through IPC handlers the renderer calls
// via the preload bridge. The frontend is unchanged across web and desktop.

const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const path = require("node:path");
const fs = require("node:fs/promises");

const isDev = !app.isPackaged && process.env.NODE_ENV !== "production";
const DEV_URL = process.env.VITE_DEV_URL || "http://localhost:5173";

// Running as root (containers/CI) requires disabling the sandbox to launch.
if (process.getuid && process.getuid() === 0) {
  app.commandLine.appendSwitch("no-sandbox");
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: "#0e1116",
    title: "CircuitLab — EDA & Simulation",
    icon: path.join(__dirname, "..", "build", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  win.removeMenu();

  if (isDev) {
    win.loadURL(DEV_URL);
  } else {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

// ---- Native file dialogs (called from the renderer via preload) ----
ipcMain.handle("open-project", async () => {
  const { canceled, filePaths } = await dialog.showOpenDialog({
    title: "Open CircuitLab Project",
    filters: [{ name: "CircuitLab Project", extensions: ["clab", "json"] }],
    properties: ["openFile"],
  });
  if (canceled || filePaths.length === 0) return null;
  const filePath = filePaths[0];
  const text = await fs.readFile(filePath, "utf8");
  const name = path.basename(filePath).replace(/\.[^.]+$/, "");
  return { text, name };
});

ipcMain.handle("save-project", async (_evt, { text, suggestedName }) => {
  const { canceled, filePath } = await dialog.showSaveDialog({
    title: "Save CircuitLab Project",
    defaultPath: `${suggestedName || "project"}.clab`,
    filters: [{ name: "CircuitLab Project", extensions: ["clab", "json"] }],
  });
  if (canceled || !filePath) return false;
  await fs.writeFile(filePath, text, "utf8");
  return true;
});

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
