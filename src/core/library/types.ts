/**
 * Component library type system.
 *
 * A component in the catalog is *data* — a symbol (SVG + pin coordinates),
 * a set of editable parameters, and a simulation model that tells the engine
 * how the part behaves. New parts are added by describing them, not by writing
 * bespoke rendering/simulation code. This is what lets the library scale to a
 * large "directory of all components".
 */

export type ComponentCategory =
  | "passives"
  | "sources"
  | "semiconductors"
  | "logic"
  | "ic-mcu"
  | "switches"
  | "sensors"
  | "instruments";

export const CATEGORY_LABELS: Record<ComponentCategory, string> = {
  passives: "Passives",
  sources: "Sources & Power",
  semiconductors: "Semiconductors",
  logic: "Logic",
  "ic-mcu": "ICs & Microcontrollers",
  switches: "Switches & Inputs",
  sensors: "Sensors",
  instruments: "Instruments",
};

/** How a pin participates electrically (used by ERC and the netlist). */
export type PinRole = "passive" | "input" | "output" | "power" | "ground" | "bidir";

export interface PinDef {
  /** Stable id, unique within the component (e.g. "A", "K", "D13"). */
  id: string;
  /** Human label shown near the pin. */
  name?: string;
  /** Position in the symbol's local coordinate space (px, grid = 20). */
  x: number;
  y: number;
  role: PinRole;
  /** Side the label text should be placed relative to the pin. */
  labelSide?: "left" | "right" | "up" | "down";
}

export interface ParamDef {
  key: string;
  label: string;
  default: string | number;
  unit?: string;
  kind?: "number" | "text" | "select";
  options?: string[];
}

/**
 * Simulation behaviour. `kind` selects how the engine stamps the part.
 * `pins` maps model terminals to the component's pin ids.
 */
export type SimModelKind =
  | "none" // symbol-only (placeable/wireable, simulation on the roadmap)
  | "resistor"
  | "capacitor"
  | "inductor"
  | "potentiometer"
  | "vsource"
  | "power"
  | "ground"
  | "diode"
  | "led"
  | "switch"
  | "mcu-atmega328p";

export interface SimModel {
  kind: SimModelKind;
  /** Model terminal -> pin id. e.g. { a: "1", b: "2" } for a resistor. */
  pins?: Record<string, string>;
  /** Which parameter (by key) carries this element's primary value. */
  valueParam?: string;
  /** Extra static config consumed by a specific model. */
  [k: string]: unknown;
}

export interface ComponentSymbol {
  width: number;
  height: number;
  /** SVG fragment drawn in local space (uses currentColor for theming). */
  body: string;
  pins: PinDef[];
}

export interface ComponentDef {
  id: string;
  name: string;
  category: ComponentCategory;
  keywords: string[];
  description?: string;
  /** Reference designator prefix (R, C, U, D, LED, SW…). */
  refPrefix: string;
  symbol: ComponentSymbol;
  params: ParamDef[];
  model: SimModel;
}

/** Convenience: resolve the effective value of a param for an instance. */
export function paramValue(
  def: ComponentDef,
  overrides: Record<string, string | number> | undefined,
  key: string,
): string | number | undefined {
  if (overrides && key in overrides) return overrides[key];
  const p = def.params.find((p) => p.key === key);
  return p?.default;
}
