import { describe, expect, it } from "vitest";
import { createDemoProject } from "../project/demo";
import { pinKey } from "../project/geometry";
import { buildNetlist } from "./netlist";

describe("netlist compilation", () => {
  it("finds a ground reference in the demo project", () => {
    const nl = buildNetlist(createDemoProject());
    expect(nl.groundNetId).toBe(0);
    expect(nl.nets.find((n) => n.isGround)).toBeTruthy();
  });

  it("merges pins joined by a wire onto the same net", () => {
    const nl = buildNetlist(createDemoProject());
    // R1.2 and LED1.a are wired together.
    const a = nl.pinToNet.get(pinKey("r1", "2"));
    const b = nl.pinToNet.get(pinKey("led1", "a"));
    expect(a).toBeDefined();
    expect(a).toBe(b);
  });

  it("collapses ground symbols and MCU GND onto net 0", () => {
    const nl = buildNetlist(createDemoProject());
    // LED cathode -> GND1 ; Arduino GND ; battery neg -> GND2 all share net 0.
    expect(nl.pinToNet.get(pinKey("led1", "k"))).toBe(0);
    expect(nl.pinToNet.get(pinKey("u1", "GND"))).toBe(0);
    expect(nl.pinToNet.get(pinKey("gnd2", "g"))).toBe(0);
  });
});
