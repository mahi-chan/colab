/**
 * DC circuit evaluation. Assembles MNA stamps from the compiled netlist and the
 * live runtime state (switch positions, MCU output pins), then solves for node
 * voltages. LEDs/diodes are handled by a short fixed-point iteration: start with
 * them open, solve, mark forward-biased ones conducting, and repeat until the
 * conducting set is stable.
 *
 * Every source is stamped as a Norton equivalent (conductance + current source),
 * so the system is purely resistive and always solvable (a tiny gmin ties every
 * node to ground). This keeps parallel ideal sources from making it singular.
 */
import type { ComponentDef } from "../library/types";
import type { Netlist } from "../netlist/netlist";
import { pinKey } from "../project/geometry";
import type { SchematicComponent } from "../project/types";
import { solveMNA, type CurrentStamp, type ResistorStamp } from "./analog/mna";

export interface LedState {
  on: boolean;
  brightness: number; // 0..1
  current: number; // amps
}

export interface EvalResult {
  ok: boolean;
  /** net id -> voltage (V). */
  netVoltage: Map<number, number>;
  /** component id -> LED state. */
  leds: Map<string, LedState>;
  /** component id -> (pin id -> logic high?) for MCU input pins. */
  mcuInputs: Map<string, Map<string, boolean>>;
}

export interface EvalOptions {
  /** For an MCU IO pin: "high"/"low" if the CPU drives it, else null (input). */
  getMcuOutput?: (componentId: string, pinId: string) => "high" | "low" | null;
  /** Whether a switch/button component is currently closed. */
  isSwitchClosed?: (componentId: string) => boolean;
  vcc?: number;
}

const R_OUT_MCU = 40;
const R_OUT_SUPPLY = 0.5;
const R_ON_LED = 24;
const R_ON_DIODE = 8;
const R_SWITCH_CLOSED = 0.01;
const R_INDUCTOR = 0.001;
const R_GMIN = 1e9;
const LED_I_MAX = 0.02;
const LED_I_ON = 0.0005;
const LOGIC_THRESHOLD = 2.5;

function num(comp: SchematicComponent, def: ComponentDef, key: string, fallback: number): number {
  const raw = key in comp.params ? comp.params[key] : def.params.find((p) => p.key === key)?.default;
  const v = typeof raw === "string" ? parseFloat(raw) : raw;
  return typeof v === "number" && isFinite(v) ? v : fallback;
}

export function evaluate(netlist: Netlist, opts: EvalOptions = {}): EvalResult {
  const vcc = opts.vcc ?? 5;
  const emptyResult: EvalResult = {
    ok: false,
    netVoltage: new Map(),
    leds: new Map(),
    mcuInputs: new Map(),
  };

  // No ground reference -> voltages undefined; report LEDs off.
  if (netlist.groundNetId < 0) {
    return { ...emptyResult, ok: false };
  }

  const nonGround = netlist.nets.filter((n) => !n.isGround);
  const numNodes = nonGround.length;
  const netOf = (componentId: string, pinId: string) =>
    netlist.pinToNet.get(pinKey(componentId, pinId)) ?? 0;

  // Static stamps (independent of diode/LED conduction state).
  const baseResistors: ResistorStamp[] = [];
  const baseCurrents: CurrentStamp[] = [];

  // gmin: tie every node weakly to ground so the matrix is never singular.
  for (const net of nonGround) baseResistors.push({ a: net.id, b: 0, r: R_GMIN });

  interface DiodeEl {
    componentId: string;
    anode: number;
    cathode: number;
    rOn: number;
    isLed: boolean;
  }
  const diodes: DiodeEl[] = [];

  for (const { comp, def } of netlist.components) {
    const m = def.model;
    const p = (name: string) => (m.pins ? m.pins[name] : undefined);
    switch (m.kind) {
      case "resistor": {
        const r = Math.max(num(comp, def, "resistance", 1000), 1e-3);
        baseResistors.push({ a: netOf(comp.id, p("a")!), b: netOf(comp.id, p("b")!), r });
        break;
      }
      case "inductor": {
        baseResistors.push({ a: netOf(comp.id, p("a")!), b: netOf(comp.id, p("b")!), r: R_INDUCTOR });
        break;
      }
      case "capacitor":
        // Open at DC steady state (MVP).
        break;
      case "potentiometer": {
        const rTotal = Math.max(num(comp, def, "resistance", 10000), 1e-3);
        const w = Math.min(Math.max(num(comp, def, "wiper", 0.5), 0), 1);
        baseResistors.push({ a: netOf(comp.id, p("a")!), b: netOf(comp.id, p("w")!), r: Math.max(rTotal * w, 1e-2) });
        baseResistors.push({ a: netOf(comp.id, p("w")!), b: netOf(comp.id, p("b")!), r: Math.max(rTotal * (1 - w), 1e-2) });
        break;
      }
      case "vsource": {
        const v = num(comp, def, "voltage", 5);
        nortonSource(baseResistors, baseCurrents, netOf(comp.id, p("pos")!), netOf(comp.id, p("neg")!), v, R_OUT_SUPPLY);
        break;
      }
      case "power": {
        const v = num(comp, def, "voltage", 5);
        nortonSource(baseResistors, baseCurrents, netOf(comp.id, p("p")!), 0, v, R_OUT_SUPPLY);
        break;
      }
      case "switch": {
        const closed = opts.isSwitchClosed?.(comp.id) ?? false;
        if (closed) {
          baseResistors.push({ a: netOf(comp.id, p("a")!), b: netOf(comp.id, p("b")!), r: R_SWITCH_CLOSED });
        }
        break;
      }
      case "diode":
      case "led": {
        diodes.push({
          componentId: comp.id,
          anode: netOf(comp.id, p("a")!),
          cathode: netOf(comp.id, p("k")!),
          rOn: m.kind === "led" ? R_ON_LED : R_ON_DIODE,
          isLed: m.kind === "led",
        });
        break;
      }
      case "mcu-atmega328p": {
        for (const pin of def.symbol.pins) {
          if (pin.id === "5V") {
            nortonSource(baseResistors, baseCurrents, netOf(comp.id, pin.id), 0, 5, R_OUT_SUPPLY);
          } else if (pin.id === "3V3") {
            nortonSource(baseResistors, baseCurrents, netOf(comp.id, pin.id), 0, 3.3, R_OUT_SUPPLY);
          } else if (pin.role === "bidir") {
            const drive = opts.getMcuOutput?.(comp.id, pin.id) ?? null;
            if (drive === "high") {
              nortonSource(baseResistors, baseCurrents, netOf(comp.id, pin.id), 0, vcc, R_OUT_MCU);
            } else if (drive === "low") {
              baseResistors.push({ a: netOf(comp.id, pin.id), b: 0, r: R_OUT_MCU });
            }
          }
        }
        break;
      }
    }
  }

  // Fixed-point iteration over diode/LED conduction.
  const conducting = new Set<string>();
  let result = solveMNA(numNodes, baseResistors, baseCurrents, []);
  for (let iter = 0; iter < 8; iter++) {
    const next = new Set<string>();
    for (const d of diodes) {
      const va = result.voltage(d.anode);
      const vk = result.voltage(d.cathode);
      if (va - vk > 0.01) next.add(d.componentId);
    }
    const same = next.size === conducting.size && [...next].every((id) => conducting.has(id));
    if (same && iter > 0) break;
    conducting.clear();
    next.forEach((id) => conducting.add(id));
    const rs = baseResistors.slice();
    for (const d of diodes) {
      if (conducting.has(d.componentId)) rs.push({ a: d.anode, b: d.cathode, r: d.rOn });
    }
    result = solveMNA(numNodes, rs, baseCurrents, []);
    if (!result.ok) return { ...emptyResult, ok: false };
  }

  // Collect outputs.
  const netVoltage = new Map<number, number>();
  for (const net of netlist.nets) netVoltage.set(net.id, result.voltage(net.id));

  const leds = new Map<string, LedState>();
  for (const d of diodes) {
    if (!d.isLed) continue;
    const va = result.voltage(d.anode);
    const vk = result.voltage(d.cathode);
    const current = conducting.has(d.componentId) ? Math.max((va - vk) / d.rOn, 0) : 0;
    leds.set(d.componentId, {
      on: current > LED_I_ON,
      brightness: Math.min(current / LED_I_MAX, 1),
      current,
    });
  }

  const mcuInputs = new Map<string, Map<string, boolean>>();
  for (const { comp, def } of netlist.components) {
    if (def.model.kind !== "mcu-atmega328p") continue;
    const pinMap = new Map<string, boolean>();
    for (const pin of def.symbol.pins) {
      if (pin.role !== "bidir") continue;
      const drive = opts.getMcuOutput?.(comp.id, pin.id) ?? null;
      if (drive === null) {
        const v = result.voltage(netOf(comp.id, pin.id));
        pinMap.set(pin.id, v > LOGIC_THRESHOLD);
      }
    }
    mcuInputs.set(comp.id, pinMap);
  }

  return { ok: true, netVoltage, leds, mcuInputs };
}

/** Stamp a Thevenin source (V, Rout) between `pos` and `neg` as a Norton pair. */
function nortonSource(
  resistors: ResistorStamp[],
  currents: CurrentStamp[],
  pos: number,
  neg: number,
  v: number,
  rOut: number,
): void {
  resistors.push({ a: pos, b: neg, r: rOut });
  currents.push({ pos, neg, i: v / rOut });
}
