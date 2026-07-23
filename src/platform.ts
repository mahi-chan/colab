/**
 * Platform selection. Detects the Electron desktop shell (via the preload bridge
 * or the Electron user-agent) and loads the desktop adapter; otherwise uses the
 * web adapter. Both satisfy PlatformAdapter, so the rest of the app is identical
 * on web and desktop.
 */
import type { PlatformAdapter } from "./core/platform/PlatformAdapter";
import { WebPlatform } from "./platform-web/webPlatform";

function isDesktop(): boolean {
  if (typeof window === "undefined") return false;
  const hasBridge = "circuitlab" in window;
  const isElectronUa =
    typeof navigator !== "undefined" && /Electron/i.test(navigator.userAgent);
  return hasBridge || isElectronUa;
}

export async function getPlatform(): Promise<PlatformAdapter> {
  if (isDesktop()) {
    try {
      const mod = await import("./platform-desktop/desktopPlatform");
      return new mod.DesktopPlatform();
    } catch {
      // Fall back to web behaviour if the desktop adapter fails to load.
    }
  }
  return new WebPlatform();
}
