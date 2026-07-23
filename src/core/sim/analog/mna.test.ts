import { describe, expect, it } from "vitest";
import { solveMNA } from "./mna";

describe("MNA solver", () => {
  it("solves a 1:1 resistor divider to half the source voltage", () => {
    // node1 = 5V source, node2 = midpoint, ground = 0.
    const r = solveMNA(
      2,
      [
        { a: 1, b: 2, r: 1000 },
        { a: 2, b: 0, r: 1000 },
      ],
      [],
      [{ pos: 1, neg: 0, v: 5 }],
    );
    expect(r.ok).toBe(true);
    expect(r.voltage(1)).toBeCloseTo(5, 6);
    expect(r.voltage(2)).toBeCloseTo(2.5, 6);
  });

  it("weights an unequal divider correctly", () => {
    // 2k over (2k + 1k) => 5 * 1k/3k
    const r = solveMNA(
      2,
      [
        { a: 1, b: 2, r: 2000 },
        { a: 2, b: 0, r: 1000 },
      ],
      [],
      [{ pos: 1, neg: 0, v: 5 }],
    );
    expect(r.voltage(2)).toBeCloseTo((5 * 1000) / 3000, 6);
  });

  it("reports the source current through a single resistor", () => {
    const r = solveMNA(1, [{ a: 1, b: 0, r: 100 }], [], [{ pos: 1, neg: 0, v: 10 }]);
    // I = V/R = 0.1 A, leaving the source node.
    expect(Math.abs(r.sourceCurrent(0))).toBeCloseTo(0.1, 6);
  });

  it("handles a current source into a resistor", () => {
    const r = solveMNA(1, [{ a: 1, b: 0, r: 1000 }], [{ pos: 1, neg: 0, i: 0.001 }], []);
    expect(r.voltage(1)).toBeCloseTo(1, 6); // 1mA * 1k = 1V
  });
});
