/**
 * Preloaded demo project so the app does something the moment it opens:
 *  - An Arduino Uno running the Blink firmware, driving an LED through a resistor.
 *  - A separate resistor divider (battery + two resistors + ground) that shows
 *    the analog MNA solver producing a correct mid-point voltage.
 */
import { BLINK } from "../sim/examples";
import type { Project, SchematicComponent, Wire } from "./types";

let wireN = 0;
function wire(a: [string, string], b: [string, string]): Wire {
  return {
    id: `w${++wireN}`,
    a: { componentId: a[0], pinId: a[1] },
    b: { componentId: b[0], pinId: b[1] },
  };
}

function comp(
  id: string,
  defId: string,
  ref: string,
  x: number,
  y: number,
  params: Record<string, string | number> = {},
): SchematicComponent {
  return { id, defId, ref, x, y, rotation: 0, params };
}

export function createDemoProject(): Project {
  const now = Date.now();
  const components: SchematicComponent[] = [
    comp("u1", "arduino-uno", "U1", 40, 40),
    comp("r1", "resistor", "R1", 360, 60, { resistance: 220 }),
    comp("led1", "led", "LED1", 500, 55, { color: "red" }),
    comp("gnd1", "ground", "GND1", 600, 90),
    // Resistor divider (analog demo).
    comp("v1", "dc-voltage", "V1", 380, 440, { voltage: 5 }),
    comp("r2", "resistor", "R2", 460, 430, { resistance: 1000 }),
    comp("r3", "resistor", "R3", 600, 430, { resistance: 1000 }),
    comp("gnd2", "ground", "GND2", 720, 450),
  ];

  const wires: Wire[] = [
    // Blink: D13 -> R1 -> LED anode -> ground; MCU GND is ground too.
    wire(["u1", "D13"], ["r1", "1"]),
    wire(["r1", "2"], ["led1", "a"]),
    wire(["led1", "k"], ["gnd1", "g"]),
    // Divider: V+ -> R2 -> R3 -> gnd ; V- -> gnd.
    wire(["v1", "pos"], ["r2", "1"]),
    wire(["r2", "2"], ["r3", "1"]),
    wire(["r3", "2"], ["gnd2", "g"]),
    wire(["v1", "neg"], ["gnd2", "g"]),
  ];

  return {
    id: "demo",
    name: "Demo — Blink + Divider",
    createdAt: now,
    updatedAt: now,
    schematic: { components, wires },
    simulation: {
      sketches: { u1: { source: BLINK.source, hex: BLINK.hex, lang: "arduino" } },
      probes: [{ id: "p1", pin: { componentId: "r2", pinId: "2" }, label: "Vout" }],
    },
  };
}
