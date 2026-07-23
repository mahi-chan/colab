/**
 * SIM left panel: interactive inputs (buttons/switches), live measurements
 * (probes + net voltages), and LED status — all driven by the running engine.
 */
import { useMemo } from "react";
import { getComponentDef } from "../../core/library/catalog";
import { buildNetlist } from "../../core/netlist/netlist";
import { pinKey } from "../../core/project/geometry";
import { useProjectStore } from "../../store/projectStore";
import { isMomentary, useSimStore } from "../../store/simStore";

export function SimControls() {
  const project = useProjectStore((s) => s.project);
  const snapshot = useSimStore((s) => s.snapshot);
  const running = useSimStore((s) => s.running);
  const pressed = useSimStore((s) => s.pressed);
  const toggles = useSimStore((s) => s.toggles);
  const pressButton = useSimStore((s) => s.pressButton);
  const releaseButton = useSimStore((s) => s.releaseButton);
  const toggleSwitch = useSimStore((s) => s.toggleSwitch);

  const netlist = useMemo(() => buildNetlist(project), [project]);

  const inputs = project.schematic.components.filter((c) => getComponentDef(c.defId)?.model.kind === "switch");
  const leds = project.schematic.components.filter((c) => getComponentDef(c.defId)?.model.kind === "led");

  const probeVoltage = (componentId: string, pinId: string) => {
    const net = netlist.pinToNet.get(pinKey(componentId, pinId));
    if (net === undefined) return undefined;
    return snapshot?.netVoltage.get(net);
  };

  return (
    <div className="side-scroll">
      <div className="panel-title">Inputs</div>
      {inputs.length === 0 && <div className="empty" style={{ padding: "12px 16px" }}>No buttons or switches.</div>}
      {inputs.map((c) => {
        const momentary = isMomentary(c.defId);
        const on = pressed[c.id] || toggles[c.id];
        return (
          <div className="prop-row" key={c.id}>
            <label>{c.ref}</label>
            {momentary ? (
              <button
                onPointerDown={() => pressButton(c.id)}
                onPointerUp={() => releaseButton(c.id)}
                onPointerLeave={() => pressed[c.id] && releaseButton(c.id)}
                style={{ width: "100%", background: on ? "var(--accent)" : undefined }}
              >
                {on ? "Pressed" : "Hold"}
              </button>
            ) : (
              <button onClick={() => toggleSwitch(c.id)} style={{ width: "100%", background: on ? "var(--accent)" : undefined }}>
                {on ? "Closed" : "Open"}
              </button>
            )}
          </div>
        );
      })}

      <div className="panel-title">Measurements</div>
      {project.simulation.probes.map((p) => {
        const v = probeVoltage(p.pin.componentId, p.pin.pinId);
        return (
          <div className="probe" key={p.id}>
            <span>{p.label}</span>
            <span className="val">{v === undefined ? "—" : `${v.toFixed(2)} V`}</span>
          </div>
        );
      })}
      {leds.map((c) => {
        const st = snapshot?.leds.get(c.id);
        return (
          <div className="probe" key={c.id}>
            <span>{c.ref}</span>
            <span className="val" style={{ color: st?.on ? "var(--wire-hi)" : "var(--text-faint)" }}>
              {st?.on ? `ON · ${(st.current * 1000).toFixed(1)} mA` : "off"}
            </span>
          </div>
        );
      })}

      {!running && (
        <div className="note" style={{ borderTop: "1px solid var(--border)", marginTop: 8 }}>
          Press <strong>Run</strong> in the toolbar to start the simulation.
        </div>
      )}
    </div>
  );
}
