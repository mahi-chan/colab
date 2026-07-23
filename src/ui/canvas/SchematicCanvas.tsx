/**
 * Shared SVG schematic canvas. In "eda" mode it edits the schematic (place,
 * move, wire, select, rotate, delete). In "sim" mode it renders the same graph
 * read-only with live overlays: LED glow, MCU pin levels, net colouring, and
 * interactive buttons. Both modes draw from the one project — the EDA and SIM
 * views are two windows onto the same data.
 */
import { useCallback, useMemo, useRef, useState } from "react";
import { getComponentDef } from "../../core/library/catalog";
import type { ComponentDef, PinDef } from "../../core/library/types";
import { pinKey, pinPosition } from "../../core/project/geometry";
import type { PinRef, SchematicComponent } from "../../core/project/types";
import { buildNetlist } from "../../core/netlist/netlist";
import { useProjectStore } from "../../store/projectStore";
import { isMomentary, useSimStore } from "../../store/simStore";

interface Props {
  mode: "eda" | "sim";
}

interface Resolved {
  comp: SchematicComponent;
  def: ComponentDef;
}

function ledColor(name: string | number | undefined): string {
  switch (name) {
    case "green":
      return "#39d353";
    case "blue":
      return "#4a9fe8";
    case "yellow":
      return "#e8c34a";
    case "white":
      return "#f0f0f0";
    default:
      return "#ff4d4d";
  }
}

export function SchematicCanvas({ mode }: Props) {
  const project = useProjectStore((s) => s.project);
  const selectedId = useProjectStore((s) => s.selectedId);
  const select = useProjectStore((s) => s.select);
  const moveComponent = useProjectStore((s) => s.moveComponent);
  const addWire = useProjectStore((s) => s.addWire);
  const deleteWire = useProjectStore((s) => s.deleteWire);
  const deleteComponent = useProjectStore((s) => s.deleteComponent);
  const rotateComponent = useProjectStore((s) => s.rotateComponent);

  const snapshot = useSimStore((s) => s.snapshot);
  const pressed = useSimStore((s) => s.pressed);
  const toggles = useSimStore((s) => s.toggles);
  const pressButton = useSimStore((s) => s.pressButton);
  const releaseButton = useSimStore((s) => s.releaseButton);
  const toggleSwitch = useSimStore((s) => s.toggleSwitch);

  const svgRef = useRef<SVGSVGElement>(null);
  const [view, setView] = useState({ tx: 40, ty: 20, scale: 1 });
  const [hoverPin, setHoverPin] = useState<string | null>(null);
  const [pending, setPending] = useState<{ from: PinRef; x: number; y: number } | null>(null);
  const [selectedWire, setSelectedWire] = useState<string | null>(null);

  // Interaction refs (avoid re-render during drag).
  const drag = useRef<{ id: string; dx: number; dy: number; x: number; y: number } | null>(null);
  const pan = useRef<{ sx: number; sy: number; tx: number; ty: number } | null>(null);
  const [dragPos, setDragPos] = useState<{ id: string; x: number; y: number } | null>(null);

  const resolved = useMemo<Resolved[]>(
    () =>
      project.schematic.components
        .map((comp) => ({ comp, def: getComponentDef(comp.defId)! }))
        .filter((r) => r.def),
    [project.schematic.components],
  );

  const netlist = useMemo(() => buildNetlist(project), [project]);

  const compById = useMemo(() => {
    const m = new Map<string, Resolved>();
    for (const r of resolved) m.set(r.comp.id, r);
    return m;
  }, [resolved]);

  const effectiveComp = useCallback(
    (comp: SchematicComponent): SchematicComponent =>
      dragPos && dragPos.id === comp.id ? { ...comp, x: dragPos.x, y: dragPos.y } : comp,
    [dragPos],
  );

  const pinAbs = useCallback(
    (componentId: string, pinId: string) => {
      const r = compById.get(componentId);
      if (!r) return { x: 0, y: 0 };
      const pin = r.def.symbol.pins.find((p) => p.id === pinId);
      if (!pin) return { x: 0, y: 0 };
      return pinPosition(effectiveComp(r.comp), r.def, pin);
    },
    [compById, effectiveComp],
  );

  const toWorld = useCallback(
    (clientX: number, clientY: number) => {
      const rect = svgRef.current!.getBoundingClientRect();
      return {
        x: (clientX - rect.left - view.tx) / view.scale,
        y: (clientY - rect.top - view.ty) / view.scale,
      };
    },
    [view],
  );

  // ---- Background pan / zoom ----
  const onBackgroundDown = (e: React.PointerEvent) => {
    if (e.button !== 0) return;
    select(null);
    setSelectedWire(null);
    setPending(null);
    pan.current = { sx: e.clientX, sy: e.clientY, tx: view.tx, ty: view.ty };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (pan.current) {
      setView((v) => ({ ...v, tx: pan.current!.tx + (e.clientX - pan.current!.sx), ty: pan.current!.ty + (e.clientY - pan.current!.sy) }));
      return;
    }
    if (drag.current) {
      const w = toWorld(e.clientX, e.clientY);
      const x = w.x - drag.current.dx;
      const y = w.y - drag.current.dy;
      drag.current.x = x;
      drag.current.y = y;
      setDragPos({ id: drag.current.id, x, y });
      return;
    }
    if (pending) {
      const w = toWorld(e.clientX, e.clientY);
      setPending((p) => (p ? { ...p, x: w.x, y: w.y } : p));
    }
  };

  const onPointerUp = () => {
    if (drag.current) {
      moveComponent(drag.current.id, drag.current.x, drag.current.y);
      drag.current = null;
      setDragPos(null);
    }
    pan.current = null;
    if (pending) {
      if (hoverPin) {
        const [componentId, pinId] = hoverPin.split("::");
        addWire(pending.from, { componentId, pinId });
      }
      setPending(null);
    }
  };

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const rect = svgRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
    const newScale = Math.min(Math.max(view.scale * factor, 0.3), 3);
    // Zoom around cursor.
    const wx = (mx - view.tx) / view.scale;
    const wy = (my - view.ty) / view.scale;
    setView({ scale: newScale, tx: mx - wx * newScale, ty: my - wy * newScale });
  };

  // ---- Component drag (EDA) ----
  const onCompDown = (e: React.PointerEvent, comp: SchematicComponent) => {
    if (mode !== "eda" || e.button !== 0) return;
    e.stopPropagation();
    select(comp.id);
    setSelectedWire(null);
    const w = toWorld(e.clientX, e.clientY);
    drag.current = { id: comp.id, dx: w.x - comp.x, dy: w.y - comp.y, x: comp.x, y: comp.y };
    (e.target as Element).setPointerCapture?.(e.pointerId);
  };

  // ---- Pin interactions ----
  const onPinDown = (e: React.PointerEvent, ref: PinRef) => {
    if (mode !== "eda") return;
    e.stopPropagation();
    const p = pinAbs(ref.componentId, ref.pinId);
    setPending({ from: ref, x: p.x, y: p.y });
    (svgRef.current as Element)?.setPointerCapture?.(e.pointerId);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (mode !== "eda") return;
    if (e.key === "Delete" || e.key === "Backspace") {
      if (selectedId) deleteComponent(selectedId);
      else if (selectedWire) {
        deleteWire(selectedWire);
        setSelectedWire(null);
      }
    } else if (e.key.toLowerCase() === "r" && selectedId) {
      rotateComponent(selectedId);
    }
  };

  // ---- SIM helpers ----
  const netVoltage = (componentId: string, pinId: string): number | undefined => {
    const net = netlist.pinToNet.get(pinKey(componentId, pinId));
    if (net === undefined) return undefined;
    return snapshot?.netVoltage.get(net);
  };

  const wireColor = (w: { a: PinRef }): string => {
    if (mode !== "sim" || !snapshot) return "var(--wire)";
    const v = netVoltage(w.a.componentId, w.a.pinId);
    if (v === undefined) return "var(--wire)";
    if (v > 2.5) return "var(--wire-hi)";
    if (v > 0.3) return "var(--warning)";
    return "var(--wire-lo)";
  };

  return (
    <div className="canvas-wrap">
      <svg
        ref={svgRef}
        className="schematic"
        tabIndex={0}
        onPointerDown={onBackgroundDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onWheel={onWheel}
        onKeyDown={onKeyDown}
      >
        <defs>
          <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
            <circle cx="1" cy="1" r="0.6" fill="#2a3242" />
          </pattern>
        </defs>
        <g transform={`translate(${view.tx},${view.ty}) scale(${view.scale})`}>
          <rect
            x={-2000}
            y={-2000}
            width={6000}
            height={6000}
            fill="url(#grid)"
            data-bg="1"
            onPointerDown={onBackgroundDown}
          />

          {/* Wires */}
          {project.schematic.wires.map((w) => {
            const a = pinAbs(w.a.componentId, w.a.pinId);
            const b = pinAbs(w.b.componentId, w.b.pinId);
            const midX = (a.x + b.x) / 2;
            const d = `M ${a.x} ${a.y} L ${midX} ${a.y} L ${midX} ${b.y} L ${b.x} ${b.y}`;
            return (
              <path
                key={w.id}
                className={`wire${selectedWire === w.id ? " selected" : ""}`}
                d={d}
                stroke={wireColor(w)}
                onPointerDown={(e) => {
                  if (mode !== "eda") return;
                  e.stopPropagation();
                  setSelectedWire(w.id);
                  select(null);
                }}
              />
            );
          })}

          {/* Components */}
          {resolved.map(({ comp, def }) => {
            const c = effectiveComp(comp);
            const { width: wd, height: ht } = def.symbol;
            const isSel = selectedId === comp.id;
            const led = mode === "sim" ? snapshot?.leds.get(comp.id) : undefined;
            const isSwitch = def.model.kind === "switch";
            const switchClosed = pressed[comp.id] || toggles[comp.id];
            return (
              <g
                key={comp.id}
                className={`comp-group${isSel ? " selected" : ""}`}
                transform={`translate(${c.x},${c.y}) rotate(${c.rotation} ${wd / 2} ${ht / 2})`}
                onPointerDown={(e) => {
                  if (mode === "sim" && isSwitch) {
                    e.stopPropagation();
                    if (isMomentary(def.id)) pressButton(comp.id);
                    else toggleSwitch(comp.id);
                    return;
                  }
                  onCompDown(e, comp);
                }}
                onPointerUp={() => {
                  if (mode === "sim" && isSwitch && isMomentary(def.id)) releaseButton(comp.id);
                }}
                style={{ cursor: mode === "sim" ? (isSwitch ? "pointer" : "default") : "grab" }}
              >
                {/* selection / hit outline */}
                <rect className="comp-outline" x={-4} y={-4} width={wd + 8} height={ht + 8} fill="transparent" />

                {/* LED glow underlay */}
                {led && led.on && (
                  <circle
                    cx={wd / 2}
                    cy={ht / 2}
                    r={16}
                    fill={ledColor(comp.params.color ?? def.params.find((p) => p.key === "color")?.default)}
                    opacity={0.25 + 0.55 * led.brightness}
                    style={{ filter: "blur(3px)" }}
                  />
                )}

                {/* symbol body */}
                <g dangerouslySetInnerHTML={{ __html: def.symbol.body }} />

                {/* switch closed indicator */}
                {mode === "sim" && isSwitch && switchClosed && (
                  <circle cx={wd / 2} cy={ht / 2 - 12} r={3} fill="var(--accent-2)" />
                )}

                {/* reference label */}
                <text className="comp-ref" x={0} y={-8}>
                  {comp.ref}
                </text>

                {/* pins */}
                {def.symbol.pins.map((pin: PinDef) => {
                  const key = `${comp.id}::${pin.id}`;
                  const level = mode === "sim" ? snapshot?.pinLevels.get(comp.id)?.get(pin.id) : undefined;
                  const dotFill =
                    level === "high" ? "var(--wire-hi)" : level === "low" ? "var(--wire-lo)" : undefined;
                  return (
                    <g key={pin.id}>
                      <circle
                        className={`pin-dot${hoverPin === key ? " hover" : ""}`}
                        cx={pin.x}
                        cy={pin.y}
                        r={3}
                        fill={dotFill}
                      />
                      {mode === "eda" && (
                        <circle
                          className="pin-hit"
                          cx={pin.x}
                          cy={pin.y}
                          r={8}
                          onPointerEnter={() => setHoverPin(key)}
                          onPointerLeave={() => setHoverPin((h) => (h === key ? null : h))}
                          onPointerDown={(e) => onPinDown(e, { componentId: comp.id, pinId: pin.id })}
                        />
                      )}
                    </g>
                  );
                })}
              </g>
            );
          })}

          {/* Rubber-band wire */}
          {pending && (
            <line
              className="rubber"
              x1={pinAbs(pending.from.componentId, pending.from.pinId).x}
              y1={pinAbs(pending.from.componentId, pending.from.pinId).y}
              x2={pending.x}
              y2={pending.y}
            />
          )}
        </g>
      </svg>

      <div className="canvas-hint">
        {mode === "eda"
          ? "Drag from a pin to wire · drag to move · R to rotate · Del to delete · scroll to zoom"
          : "Click & hold buttons to interact · scroll to zoom · drag to pan"}
      </div>
      <div className="zoom-controls">
        <button onClick={() => setView((v) => ({ ...v, scale: Math.min(v.scale * 1.15, 3) }))}>+</button>
        <button onClick={() => setView((v) => ({ ...v, scale: Math.max(v.scale / 1.15, 0.3) }))}>−</button>
        <button onClick={() => setView({ tx: 40, ty: 20, scale: 1 })} title="Reset view">⤢</button>
      </div>
    </div>
  );
}
