/**
 * Platform selection. Detects the Tauri desktop shell and loads the desktop
 * adapter; otherwise uses the web adapter. Both satisfy PlatformAdapter, so the
 * rest of the app is identical on web and desktop.
 */
import type { PlatformAdapter } from "./core/platform/PlatformAdapter";
import { WebPlatform } from "./platform-web/webPlatform";

function isTauri(): boolean {
  return typeof window !== "undefined" && ("__TAURI_INTERNALS__" in window || "__TAURI__" in window);
}

export async function getPlatform(): Promise<PlatformAdapter> {
  if (isTauri()) {
    try {
      const mod = await import("./platform-desktop/desktopPlatform");
      return new mod.DesktopPlatform();
    } catch {
      // Fall back to web behaviour if the desktop adapter fails to load.
    }
  }
  return new WebPlatform();
}
