/**
 * Electrical Rule Check (ERC). A pragmatic starter set: floating pins, single-pin
 * nets, output-to-output conflicts, and a missing ground reference. Runs off the
 * compiled netlist so the same logic serves the EDA issues panel and tests.
 */
import type { ComponentDef } from "../library/types";
import { buildNetlist, type Netlist } from "../netlist/netlist";
import { pinKey } from "../project/geometry";
import type { Project, SchematicComponent } from "../project/types";

export type ErcSeverity = "error" | "warning";

export interface ErcIssue {
  severity: ErcSeverity;
  code: string;
  message: string;
  /** Component the issue is anchored to (for highlighting), if any. */
  componentId?: string;
}

function defOf(components: { comp: SchematicComponent; def: ComponentDef }[], id: string) {
  return components.find((c) => c.comp.id === id);
}

export function runErc(project: Project, netlist?: Netlist): ErcIssue[] {
  const nl = netlist ?? buildNetlist(project);
  const issues: ErcIssue[] = [];

  if (project.schematic.components.length === 0) return issues;

  // Missing ground: any circuit with a source really wants a reference.
  const hasSource = nl.components.some((c) =>
    ["vsource", "power", "mcu-atmega328p"].includes(c.def.model.kind),
  );
  if (nl.groundNetId < 0 && hasSource) {
    issues.push({
      severity: "warning",
      code: "no-ground",
      message: "No ground reference in the circuit. Add a Ground symbol so voltages have a reference.",
    });
  }

  // Per-pin checks.
  const wiredPins = new Set<string>();
  for (const wire of project.schematic.wires) {
    wiredPins.add(pinKey(wire.a.componentId, wire.a.pinId));
    wiredPins.add(pinKey(wire.b.componentId, wire.b.pinId));
  }

  for (const { comp, def } of nl.components) {
    // Unused GPIO on an IC/MCU is normal — don't flag those.
    if (def.model.kind === "mcu-atmega328p") continue;
    for (const pin of def.symbol.pins) {
      // Only a dangling passive lead or an unconnected gate input/output is a
      // likely mistake; leaving power/ground/bidir pins open is common.
      if (pin.role !== "passive" && pin.role !== "input" && pin.role !== "output") continue;
      const key = pinKey(comp.id, pin.id);
      const net = nl.pinToNet.get(key);
      const alone = net !== undefined && nl.nets.find((n) => n.id === net)!.pins.length === 1;
      if (!wiredPins.has(key) && alone) {
        issues.push({
          severity: "warning",
          code: "floating-pin",
          message: `${comp.ref} pin "${pin.name ?? pin.id}" is not connected to anything.`,
          componentId: comp.id,
        });
      }
    }
  }

  // Output-to-output conflicts on a net (two driving outputs shorted together).
  for (const net of nl.nets) {
    if (net.isGround) continue;
    const outputs = net.pins.filter((p) => {
      const entry = defOf(nl.components, p.componentId);
      const pin = entry?.def.symbol.pins.find((pp) => pp.id === p.pinId);
      return pin?.role === "output";
    });
    if (outputs.length > 1) {
      const refs = outputs
        .map((p) => defOf(nl.components, p.componentId)?.comp.ref ?? p.componentId)
        .join(", ");
      issues.push({
        severity: "error",
        code: "output-conflict",
        message: `Multiple outputs driving the same net (${refs}). This can cause a short.`,
        componentId: outputs[0].componentId,
      });
    }
  }

  return issues;
}
