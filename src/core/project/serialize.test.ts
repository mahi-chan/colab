import { describe, expect, it } from "vitest";
import { createDemoProject } from "./demo";
import { deserializeProject, serializeProject } from "./serialize";

describe("project serialization", () => {
  it("round-trips a project without loss", () => {
    const original = createDemoProject();
    const restored = deserializeProject(serializeProject(original));
    expect(restored.name).toBe(original.name);
    expect(restored.schematic.components).toHaveLength(original.schematic.components.length);
    expect(restored.schematic.wires).toHaveLength(original.schematic.wires.length);
    expect(restored.simulation.sketches.u1.hex).toBe(original.simulation.sketches.u1.hex);
  });

  it("rejects non-CircuitLab files", () => {
    expect(() => deserializeProject('{"foo":1}')).toThrow();
  });
});
