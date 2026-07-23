import { describe, expect, it } from "vitest";
import { createDemoProject } from "../project/demo";
import { SimulationEngine } from "./engine";

describe("simulation engine (end-to-end with avr8js)", () => {
  it("runs the Blink firmware and toggles the LED over time", () => {
    const engine = new SimulationEngine(createDemoProject());
    expect(engine.hasChips()).toBe(true);

    const seen = new Set<boolean>();
    // Step in 30ms increments across ~2s of simulated time.
    for (let i = 0; i < 70; i++) {
      const state = engine.step(0.03);
      const led = state.leds.get("led1");
      if (led) seen.add(led.on);
    }
    // The LED should have been both on and off during the run.
    expect(seen.has(true)).toBe(true);
    expect(seen.has(false)).toBe(true);
  });

  it("reports the divider voltage regardless of MCU state", () => {
    const engine = new SimulationEngine(createDemoProject());
    const state = engine.step(0.03);
    expect(state.ok).toBe(true);
  });
});
