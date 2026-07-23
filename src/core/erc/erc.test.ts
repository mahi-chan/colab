import { describe, expect, it } from "vitest";
import { createDemoProject } from "../project/demo";
import { newProject } from "../project/serialize";
import type { Project } from "../project/types";
import { runErc } from "./erc";

function projectWith(components: Project["schematic"]["components"], wires: Project["schematic"]["wires"] = []): Project {
  const p = newProject();
  p.schematic.components = components;
  p.schematic.wires = wires;
  return p;
}

describe("ERC", () => {
  it("passes the fully-wired demo project", () => {
    expect(runErc(createDemoProject())).toHaveLength(0);
  });

  it("does not flag unused MCU GPIO pins", () => {
    // Just an Arduino on the sheet: no floating-pin spam for its many GPIO.
    const p = projectWith([{ id: "u1", defId: "arduino-uno", ref: "U1", x: 0, y: 0, rotation: 0, params: {} }]);
    const floating = runErc(p).filter((i) => i.code === "floating-pin");
    expect(floating).toHaveLength(0);
  });

  it("flags a dangling passive lead", () => {
    const p = projectWith(
      [
        { id: "v1", defId: "dc-voltage", ref: "V1", x: 0, y: 0, rotation: 0, params: {} },
        { id: "r1", defId: "resistor", ref: "R1", x: 100, y: 0, rotation: 0, params: {} },
        { id: "g1", defId: "ground", ref: "GND1", x: 200, y: 0, rotation: 0, params: {} },
      ],
      [
        { id: "w1", a: { componentId: "v1", pinId: "pos" }, b: { componentId: "r1", pinId: "1" } },
        { id: "w2", a: { componentId: "v1", pinId: "neg" }, b: { componentId: "g1", pinId: "g" } },
      ],
    );
    // R1 pin "2" dangles.
    const floating = runErc(p).filter((i) => i.code === "floating-pin");
    expect(floating.length).toBeGreaterThanOrEqual(1);
    expect(floating.some((i) => i.componentId === "r1")).toBe(true);
  });

  it("warns when a powered circuit has no ground", () => {
    const p = projectWith(
      [
        { id: "v1", defId: "dc-voltage", ref: "V1", x: 0, y: 0, rotation: 0, params: {} },
        { id: "r1", defId: "resistor", ref: "R1", x: 100, y: 0, rotation: 0, params: {} },
      ],
      [
        { id: "w1", a: { componentId: "v1", pinId: "pos" }, b: { componentId: "r1", pinId: "1" } },
        { id: "w2", a: { componentId: "v1", pinId: "neg" }, b: { componentId: "r1", pinId: "2" } },
      ],
    );
    expect(runErc(p).some((i) => i.code === "no-ground")).toBe(true);
  });
});
