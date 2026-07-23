/**
 * Web PlatformAdapter. Uses the File System Access API when available and falls
 * back to download/upload otherwise. Autosave uses localStorage. When running
 * inside the Tauri shell, the desktop adapter is used instead (see main.tsx).
 */
import type { OpenedProject, PlatformAdapter } from "../core/platform/PlatformAdapter";

interface FsWindow extends Window {
  showSaveFilePicker?: (opts: unknown) => Promise<FileSystemFileHandleLike>;
  showOpenFilePicker?: (opts: unknown) => Promise<FileSystemFileHandleLike[]>;
}
interface FileSystemFileHandleLike {
  getFile(): Promise<File>;
  createWritable(): Promise<{ write(data: string): Promise<void>; close(): Promise<void> }>;
  name?: string;
}

const PROJECT_PICKER_OPTS = {
  types: [{ description: "CircuitLab Project", accept: { "application/json": [".clab", ".json"] } }],
};

export class WebPlatform implements PlatformAdapter {
  readonly kind = "web" as const;

  async openProject(): Promise<OpenedProject | null> {
    const w = window as FsWindow;
    if (w.showOpenFilePicker) {
      try {
        const [handle] = await w.showOpenFilePicker(PROJECT_PICKER_OPTS);
        const file = await handle.getFile();
        return { text: await file.text(), name: file.name.replace(/\.[^.]+$/, "") };
      } catch (e) {
        if ((e as DOMException)?.name === "AbortError") return null;
        // fall through to input fallback
      }
    }
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = ".clab,.json,application/json";
      input.onchange = async () => {
        const file = input.files?.[0];
        if (!file) return resolve(null);
        resolve({ text: await file.text(), name: file.name.replace(/\.[^.]+$/, "") });
      };
      input.click();
    });
  }

  async saveProject(text: string, suggestedName: string): Promise<void> {
    const filename = `${suggestedName || "project"}.clab`;
    const w = window as FsWindow;
    if (w.showSaveFilePicker) {
      try {
        const handle = await w.showSaveFilePicker({ ...PROJECT_PICKER_OPTS, suggestedName: filename });
        const writable = await handle.createWritable();
        await writable.write(text);
        await writable.close();
        return;
      } catch (e) {
        if ((e as DOMException)?.name === "AbortError") return;
        // fall through to download fallback
      }
    }
    const blob = new Blob([text], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async autosave(key: string, text: string): Promise<void> {
    try {
      localStorage.setItem(`circuitlab:${key}`, text);
    } catch {
      // storage full / disabled — ignore
    }
  }

  async loadAutosave(key: string): Promise<string | null> {
    try {
      return localStorage.getItem(`circuitlab:${key}`);
    } catch {
      return null;
    }
  }
}
