/**
 * Unified project model. A single Project holds the schematic (the source of
 * truth shared by the EDA and SIM views), simulation settings, and — on the
 * roadmap — PCB data. The EDA view and the SIM view are two windows onto the
 * same `schematic` graph, mirroring how PCBX keys both views off one project id.
 */

export type Rotation = 0 | 90 | 180 | 270;

export interface SchematicComponent {
  /** Instance id (unique in the project). */
  id: string;
  /** Catalog component id (defId). */
  defId: string;
  /** Reference designator, e.g. "R1". */
  ref: string;
  x: number;
  y: number;
  rotation: Rotation;
  /** Parameter overrides (keyed by ParamDef.key). */
  params: Record<string, string | number>;
}

export interface PinRef {
  componentId: string;
  pinId: string;
}

export interface Wire {
  id: string;
  a: PinRef;
  b: PinRef;
}

export interface Probe {
  id: string;
  /** A pin the probe measures (its net voltage/level is displayed). */
  pin: PinRef;
  label: string;
}

export interface Project {
  id: string;
  name: string;
  createdAt: number;
  updatedAt: number;
  schematic: {
    components: SchematicComponent[];
    wires: Wire[];
  };
  simulation: {
    /** MCU firmware per component instance: source and/or precompiled hex. */
    sketches: Record<string, { source?: string; hex?: string; lang?: "arduino" }>;
    probes: Probe[];
  };
  /** Roadmap: pcb?: PcbData */
}

export const SCHEMA_VERSION = 1;

export interface ProjectFile {
  schemaVersion: number;
  app: "circuitlab";
  project: Project;
}
