/**
 * Desktop PlatformAdapter (Tauri v2). Open/save go through native Rust commands
 * (see src-tauri/src/lib.rs) that show real file dialogs and read/write the
 * filesystem. Autosave uses the webview's localStorage, which works the same in
 * the desktop shell. This module is loaded lazily only when running under Tauri.
 */
import { invoke } from "@tauri-apps/api/core";
import type { OpenedProject, PlatformAdapter } from "../core/platform/PlatformAdapter";

export class DesktopPlatform implements PlatformAdapter {
  readonly kind = "desktop" as const;

  async openProject(): Promise<OpenedProject | null> {
    const res = await invoke<{ text: string; name: string } | null>("open_project");
    return res ? { text: res.text, name: res.name } : null;
  }

  async saveProject(text: string, suggestedName: string): Promise<void> {
    await invoke("save_project", { text, suggestedName });
  }

  async autosave(key: string, text: string): Promise<void> {
    try {
      localStorage.setItem(`circuitlab:${key}`, text);
    } catch {
      /* ignore */
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
