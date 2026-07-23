import { describe, expect, it } from "vitest";
import { buildNetlist } from "../netlist/netlist";
import { createDemoProject } from "../project/demo";
import { pinKey } from "../project/geometry";
import { evaluate } from "./evaluate";

describe("circuit evaluation", () => {
  it("computes the resistor-divider midpoint (~2.5V)", () => {
    const nl = buildNetlist(createDemoProject());
    const r = evaluate(nl, { getMcuOutput: () => null });
    const midNet = nl.pinToNet.get(pinKey("r2", "2"))!;
    expect(r.ok).toBe(true);
    expect(r.netVoltage.get(midNet)!).toBeCloseTo(2.5, 1);
  });

  it("lights the LED when the driving pin is HIGH", () => {
    const nl = buildNetlist(createDemoProject());
    const r = evaluate(nl, {
      getMcuOutput: (_c, pin) => (pin === "D13" ? "high" : null),
    });
    expect(r.leds.get("led1")!.on).toBe(true);
    expect(r.leds.get("led1")!.current).toBeGreaterThan(0.005);
  });

  it("keeps the LED off when the driving pin is LOW", () => {
    const nl = buildNetlist(createDemoProject());
    const r = evaluate(nl, {
      getMcuOutput: (_c, pin) => (pin === "D13" ? "low" : null),
    });
    expect(r.leds.get("led1")!.on).toBe(false);
  });
});
