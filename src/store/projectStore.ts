/**
 * Project store: the single source of truth for the schematic that both the EDA
 * and SIM views read. Mutations produce new immutable-ish objects so React
 * re-renders. Autosave runs after every change.
 */
import { create } from "zustand";
import { getComponentDef } from "../core/library/catalog";
import type { PlatformAdapter } from "../core/platform/PlatformAdapter";
import { createDemoProject } from "../core/project/demo";
import { pinKey } from "../core/project/geometry";
import { deserializeProject, newProject, serializeProject } from "../core/project/serialize";
import type { PinRef, Project, Rotation, SchematicComponent, Wire } from "../core/project/types";
import { nextRef, uid } from "../core/util/id";

export type ViewMode = "eda" | "sim";

interface ProjectState {
  project: Project;
  view: ViewMode;
  selectedId: string | null;
  dirty: boolean;
  platform: PlatformAdapter | null;

  init(platform: PlatformAdapter): void;
  setView(view: ViewMode): void;
  select(id: string | null): void;

  addComponent(defId: string, x: number, y: number): string;
  moveComponent(id: string, x: number, y: number): void;
  rotateComponent(id: string): void;
  deleteComponent(id: string): void;
  updateParam(id: string, key: string, value: string | number): void;
  renameRef(id: string, ref: string): void;

  addWire(a: PinRef, b: PinRef): void;
  deleteWire(id: string): void;

  setSketch(componentId: string, source: string | undefined, hex: string | undefined): void;

  rename(name: string): void;
  loadProject(project: Project): void;
  resetToNew(): void;
  loadDemo(): void;

  save(): Promise<void>;
  open(): Promise<void>;
}

const SNAP = 10;
const snap = (v: number) => Math.round(v / SNAP) * SNAP;

function touch(project: Project): Project {
  return { ...project, updatedAt: Date.now() };
}

export const useProjectStore = create<ProjectState>((set, get) => {
  function commit(project: Project, extra: Partial<ProjectState> = {}) {
    const next = touch(project);
    set({ project: next, dirty: true, ...extra });
    const platform = get().platform;
    if (platform) void platform.autosave("working", serializeProject(next));
  }

  return {
    project: createDemoProject(),
    view: "eda",
    selectedId: null,
    dirty: false,
    platform: null,

    init(platform) {
      set({ platform });
      // Restore autosaved working project if present.
      void platform.loadAutosave("working").then((text) => {
        if (!text) return;
        try {
          set({ project: deserializeProject(text) });
        } catch {
          /* ignore corrupt autosave */
        }
      });
    },

    setView(view) {
      set({ view });
    },

    select(id) {
      set({ selectedId: id });
    },

    addComponent(defId, x, y) {
      const def = getComponentDef(defId);
      const project = get().project;
      if (!def) return "";
      const id = uid("c");
      const ref = nextRef(def.refPrefix, project.schematic.components.map((c) => c.ref));
      const comp: SchematicComponent = { id, defId, ref, x: snap(x), y: snap(y), rotation: 0, params: {} };
      commit(
        {
          ...project,
          schematic: { ...project.schematic, components: [...project.schematic.components, comp] },
        },
        { selectedId: id },
      );
      return id;
    },

    moveComponent(id, x, y) {
      const project = get().project;
      commit({
        ...project,
        schematic: {
          ...project.schematic,
          components: project.schematic.components.map((c) =>
            c.id === id ? { ...c, x: snap(x), y: snap(y) } : c,
          ),
        },
      });
    },

    rotateComponent(id) {
      const project = get().project;
      commit({
        ...project,
        schematic: {
          ...project.schematic,
          components: project.schematic.components.map((c) =>
            c.id === id ? { ...c, rotation: (((c.rotation + 90) % 360) as Rotation) } : c,
          ),
        },
      });
    },

    deleteComponent(id) {
      const project = get().project;
      const wires = project.schematic.wires.filter(
        (w) => w.a.componentId !== id && w.b.componentId !== id,
      );
      const sketches = { ...project.simulation.sketches };
      delete sketches[id];
      commit(
        {
          ...project,
          schematic: {
            components: project.schematic.components.filter((c) => c.id !== id),
            wires,
          },
          simulation: { ...project.simulation, sketches },
        },
        { selectedId: null },
      );
    },

    updateParam(id, key, value) {
      const project = get().project;
      commit({
        ...project,
        schematic: {
          ...project.schematic,
          components: project.schematic.components.map((c) =>
            c.id === id ? { ...c, params: { ...c.params, [key]: value } } : c,
          ),
        },
      });
    },

    renameRef(id, ref) {
      const project = get().project;
      commit({
        ...project,
        schematic: {
          ...project.schematic,
          components: project.schematic.components.map((c) => (c.id === id ? { ...c, ref } : c)),
        },
      });
    },

    addWire(a, b) {
      if (a.componentId === b.componentId && a.pinId === b.pinId) return;
      const project = get().project;
      // Avoid duplicate wires between the same two pins.
      const exists = project.schematic.wires.some(
        (w) =>
          (pinKey(w.a.componentId, w.a.pinId) === pinKey(a.componentId, a.pinId) &&
            pinKey(w.b.componentId, w.b.pinId) === pinKey(b.componentId, b.pinId)) ||
          (pinKey(w.a.componentId, w.a.pinId) === pinKey(b.componentId, b.pinId) &&
            pinKey(w.b.componentId, w.b.pinId) === pinKey(a.componentId, a.pinId)),
      );
      if (exists) return;
      const wire: Wire = { id: uid("w"), a, b };
      commit({
        ...project,
        schematic: { ...project.schematic, wires: [...project.schematic.wires, wire] },
      });
    },

    deleteWire(id) {
      const project = get().project;
      commit({
        ...project,
        schematic: { ...project.schematic, wires: project.schematic.wires.filter((w) => w.id !== id) },
      });
    },

    setSketch(componentId, source, hex) {
      const project = get().project;
      commit({
        ...project,
        simulation: {
          ...project.simulation,
          sketches: { ...project.simulation.sketches, [componentId]: { source, hex, lang: "arduino" } },
        },
      });
    },

    rename(name) {
      commit({ ...get().project, name });
    },

    loadProject(project) {
      set({ project, selectedId: null, dirty: false });
      const platform = get().platform;
      if (platform) void platform.autosave("working", serializeProject(project));
    },

    resetToNew() {
      const project = newProject();
      set({ project, selectedId: null, dirty: false, view: "eda" });
      const platform = get().platform;
      if (platform) void platform.autosave("working", serializeProject(project));
    },

    loadDemo() {
      get().loadProject(createDemoProject());
    },

    async save() {
      const { platform, project } = get();
      if (!platform) return;
      await platform.saveProject(serializeProject(project), project.name);
      set({ dirty: false });
    },

    async open() {
      const { platform } = get();
      if (!platform) return;
      const opened = await platform.openProject();
      if (!opened) return;
      try {
        const project = deserializeProject(opened.text);
        if (opened.name) project.name = opened.name;
        get().loadProject(project);
      } catch (e) {
        alert(`Could not open project: ${(e as Error).message}`);
      }
    },
  };
});
