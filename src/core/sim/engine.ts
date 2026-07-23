/**
 * Simulation engine. Ties the compiled netlist, the MCU chip(s), and the DC
 * circuit evaluator together. `step(dt)` advances the CPU by dt worth of clock
 * cycles, solves the circuit, feeds input-pin levels back to the CPU, and
 * returns a snapshot the UI renders. The UI owns the animation loop; the engine
 * stays free of DOM/timers so it is unit-testable.
 */
import { buildNetlist, type Netlist } from "../netlist/netlist";
import type { Project } from "../project/types";
import { ATmega328P } from "./chips/ATmega328P";
import type { Chip, DigitalLevel } from "./chips/Chip";
import { evaluate, type LedState } from "./evaluate";
import { isIntelHex } from "./chips/hex";

export interface SimState {
  time: number; // simulated seconds
  netVoltage: Map<number, number>;
  leds: Map<string, LedState>;
  pinLevels: Map<string, Map<string, DigitalLevel>>; // mcuId -> pinId -> level
  ok: boolean;
}

const MAX_STEP_SECONDS = 0.05; // clamp to keep the CPU burst bounded

export class SimulationEngine {
  readonly netlist: Netlist;
  private chips = new Map<string, Chip>();
  private switches = new Map<string, boolean>();
  private time = 0;
  private serialBuffers = new Map<string, string>();

  /** Fired when an MCU emits serial text. */
  onSerial?: (componentId: string, text: string) => void;

  constructor(private project: Project) {
    this.netlist = buildNetlist(project);
    this.initChips();
  }

  private initChips(): void {
    for (const { comp, def } of this.netlist.components) {
      if (def.model.kind !== "mcu-atmega328p") continue;
      const sketch = this.project.simulation.sketches[comp.id];
      const hex = sketch?.hex ?? (sketch?.source && isIntelHex(sketch.source) ? sketch.source : undefined);
      if (!hex) continue; // no firmware loaded yet
      const chip = new ATmega328P(hex);
      chip.onSerialByte = (b) => {
        const prev = this.serialBuffers.get(comp.id) ?? "";
        this.serialBuffers.set(comp.id, prev + String.fromCharCode(b));
      };
      this.chips.set(comp.id, chip);
    }
  }

  setSwitchClosed(componentId: string, closed: boolean): void {
    this.switches.set(componentId, closed);
  }

  isSwitchClosed(componentId: string): boolean {
    return this.switches.get(componentId) ?? false;
  }

  reset(): void {
    this.time = 0;
    this.serialBuffers.clear();
    for (const chip of this.chips.values()) chip.reset();
  }

  /** Advance the simulation by `dt` seconds and return a fresh snapshot. */
  step(dt: number): SimState {
    const clamped = Math.min(Math.max(dt, 0), MAX_STEP_SECONDS);

    // 1. Run each CPU forward.
    for (const chip of this.chips.values()) {
      chip.execute(Math.round(chip.clockHz * clamped));
    }
    this.time += clamped;

    // 2. Solve the circuit using the current output-pin drive levels.
    const result = evaluate(this.netlist, {
      getMcuOutput: (componentId, pinId) => {
        const chip = this.chips.get(componentId);
        if (!chip || !chip.isOutput(pinId)) return null;
        const level = chip.getPinLevel(pinId);
        return level === "high" ? "high" : level === "low" ? "low" : null;
      },
      isSwitchClosed: (id) => this.isSwitchClosed(id),
    });

    // 3. Feed resolved input levels back into the CPUs.
    for (const [componentId, pins] of result.mcuInputs) {
      const chip = this.chips.get(componentId);
      if (!chip) continue;
      for (const [pinId, high] of pins) chip.setInput(pinId, high);
    }

    // 4. Flush serial.
    for (const [componentId, text] of this.serialBuffers) {
      if (text) {
        this.onSerial?.(componentId, text);
        this.serialBuffers.set(componentId, "");
      }
    }

    // 5. Build the display snapshot.
    const pinLevels = new Map<string, Map<string, DigitalLevel>>();
    for (const { comp, def } of this.netlist.components) {
      if (def.model.kind !== "mcu-atmega328p") continue;
      const chip = this.chips.get(comp.id);
      const map = new Map<string, DigitalLevel>();
      for (const pin of def.symbol.pins) {
        if (pin.role === "bidir") map.set(pin.id, chip ? chip.getPinLevel(pin.id) : "input");
      }
      pinLevels.set(comp.id, map);
    }

    return { time: this.time, netVoltage: result.netVoltage, leds: result.leds, pinLevels, ok: result.ok };
  }

  /** Send a byte to a chip's serial RX (from the Serial Monitor input). */
  serialInput(componentId: string, text: string): void {
    const chip = this.chips.get(componentId);
    if (!chip) return;
    for (const ch of text) chip.serialWrite(ch.charCodeAt(0));
  }

  hasChips(): boolean {
    return this.chips.size > 0;
  }
}
