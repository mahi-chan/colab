/**
 * Simulation store: owns the imperative SimulationEngine and the animation loop,
 * and publishes a snapshot the SIM view renders. The engine and rAF handle live
 * outside the store (module scope) so only plain data is kept in React state.
 */
import { create } from "zustand";
import { SimulationEngine, type SimState } from "../core/sim/engine";
import type { Project } from "../core/project/types";
import { getComponentDef } from "../core/library/catalog";

let engine: SimulationEngine | null = null;
let rafId = 0;
let lastTime = 0;

const SERIAL_CAP = 8000;

interface SimStoreState {
  running: boolean;
  snapshot: SimState | null;
  serial: Record<string, string>;
  pressed: Record<string, boolean>; // momentary buttons held
  toggles: Record<string, boolean>; // latching switches

  start(project: Project): void;
  stop(): void;
  reset(project: Project): void;

  pressButton(id: string): void;
  releaseButton(id: string): void;
  toggleSwitch(id: string): void;
  sendSerial(componentId: string, text: string): void;
}

export const useSimStore = create<SimStoreState>((set, get) => {
  function applySwitches() {
    if (!engine) return;
    for (const [id, on] of Object.entries(get().pressed)) engine.setSwitchClosed(id, on);
    for (const [id, on] of Object.entries(get().toggles)) engine.setSwitchClosed(id, on);
  }

  function loop() {
    if (!engine) return;
    const now = performance.now();
    const dt = (now - lastTime) / 1000;
    lastTime = now;
    const snapshot = engine.step(dt);
    set({ snapshot });
    rafId = requestAnimationFrame(loop);
  }

  return {
    running: false,
    snapshot: null,
    serial: {},
    pressed: {},
    toggles: {},

    start(project) {
      get().stop();
      engine = new SimulationEngine(project);
      engine.onSerial = (componentId, text) => {
        set((s) => {
          const prev = s.serial[componentId] ?? "";
          const combined = (prev + text).slice(-SERIAL_CAP);
          return { serial: { ...s.serial, [componentId]: combined } };
        });
      };
      applySwitches();
      lastTime = performance.now();
      set({ running: true, serial: {} });
      rafId = requestAnimationFrame(loop);
    },

    stop() {
      if (rafId) cancelAnimationFrame(rafId);
      rafId = 0;
      engine = null;
      set({ running: false });
    },

    reset(project) {
      const wasRunning = get().running;
      get().stop();
      set({ snapshot: null, serial: {} });
      if (wasRunning) get().start(project);
    },

    pressButton(id) {
      set((s) => ({ pressed: { ...s.pressed, [id]: true } }));
      engine?.setSwitchClosed(id, true);
    },

    releaseButton(id) {
      set((s) => ({ pressed: { ...s.pressed, [id]: false } }));
      engine?.setSwitchClosed(id, false);
    },

    toggleSwitch(id) {
      const next = !get().toggles[id];
      set((s) => ({ toggles: { ...s.toggles, [id]: next } }));
      engine?.setSwitchClosed(id, next);
    },

    sendSerial(componentId, text) {
      engine?.serialInput(componentId, text);
    },
  };
});

/** Helper: is a component a momentary push button (vs a latching switch)? */
export function isMomentary(defId: string): boolean {
  const def = getComponentDef(defId);
  return def?.model.kind === "switch" && def.model.momentary === true;
}
