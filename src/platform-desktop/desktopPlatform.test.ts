import { afterEach, describe, expect, it, vi } from "vitest";
import { DesktopPlatform } from "./desktopPlatform";

// Minimal window + bridge + localStorage stubs (vitest runs in a node env).
function installStubs(bridge: unknown) {
  const store = new Map<string, string>();
  (globalThis as unknown as { window: unknown }).window = { circuitlab: bridge };
  (globalThis as unknown as { localStorage: unknown }).localStorage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
  };
  return store;
}

afterEach(() => {
  delete (globalThis as { window?: unknown }).window;
  delete (globalThis as { localStorage?: unknown }).localStorage;
  vi.restoreAllMocks();
});

describe("DesktopPlatform (Electron bridge)", () => {
  it("opens a project through the bridge", async () => {
    const openProject = vi.fn().mockResolvedValue({ text: "{}", name: "board" });
    installStubs({ isDesktop: true, openProject, saveProject: vi.fn() });
    const p = new DesktopPlatform();
    expect(await p.openProject()).toEqual({ text: "{}", name: "board" });
    expect(openProject).toHaveBeenCalledOnce();
  });

  it("returns null when the open dialog is cancelled", async () => {
    installStubs({ isDesktop: true, openProject: vi.fn().mockResolvedValue(null), saveProject: vi.fn() });
    expect(await new DesktopPlatform().openProject()).toBeNull();
  });

  it("saves a project through the bridge", async () => {
    const saveProject = vi.fn().mockResolvedValue(true);
    installStubs({ isDesktop: true, openProject: vi.fn(), saveProject });
    await new DesktopPlatform().saveProject('{"a":1}', "myboard");
    expect(saveProject).toHaveBeenCalledWith('{"a":1}', "myboard");
  });

  it("round-trips autosave via localStorage", async () => {
    installStubs({ isDesktop: true, openProject: vi.fn(), saveProject: vi.fn() });
    const p = new DesktopPlatform();
    await p.autosave("working", "payload");
    expect(await p.loadAutosave("working")).toBe("payload");
  });
});
