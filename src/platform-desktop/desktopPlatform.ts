/**
 * Desktop PlatformAdapter (Electron). Open/save go through the preload bridge
 * (`window.circuitlab`), which the main process backs with native dialogs +
 * filesystem access. Autosave uses the renderer's localStorage (available in the
 * Electron webview). Loaded lazily only when running inside the desktop shell.
 */
import type { OpenedProject, PlatformAdapter } from "../core/platform/PlatformAdapter";

interface DesktopBridge {
  isDesktop: boolean;
  openProject(): Promise<{ text: string; name: string } | null>;
  saveProject(text: string, suggestedName: string): Promise<boolean>;
}

function bridge(): DesktopBridge {
  const b = (window as unknown as { circuitlab?: DesktopBridge }).circuitlab;
  if (!b) throw new Error("Desktop bridge unavailable");
  return b;
}

export class DesktopPlatform implements PlatformAdapter {
  readonly kind = "desktop" as const;

  async openProject(): Promise<OpenedProject | null> {
    const res = await bridge().openProject();
    return res ? { text: res.text, name: res.name } : null;
  }

  async saveProject(text: string, suggestedName: string): Promise<void> {
    await bridge().saveProject(text, suggestedName);
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
