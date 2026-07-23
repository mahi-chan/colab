/**
 * App shell. One toolbar with EDA/SIM tabs and project actions; a three-pane
 * body (palette · canvas · inspector) whose side panels swap with the view; and
 * a serial monitor in the SIM view. The canvas is shared — EDA and SIM are two
 * views of the same project.
 */
import { useEffect, useMemo } from "react";
import { getComponentDef } from "../core/library/catalog";
import { useProjectStore } from "../store/projectStore";
import { useSimStore } from "../store/simStore";
import { SchematicCanvas } from "./canvas/SchematicCanvas";
import { LibraryBrowser } from "./library/LibraryBrowser";
import { Inspector } from "./eda/Inspector";
import { SimControls } from "./sim/SimControls";
import { CodeEditor } from "./editor/CodeEditor";
import { SerialMonitor } from "./sim/SerialMonitor";

function useMcuIds(): string[] {
  const project = useProjectStore((s) => s.project);
  return useMemo(
    () =>
      project.schematic.components
        .filter((c) => getComponentDef(c.defId)?.model.kind === "mcu-atmega328p")
        .map((c) => c.id),
    [project.schematic.components],
  );
}

function Toolbar() {
  const view = useProjectStore((s) => s.view);
  const setView = useProjectStore((s) => s.setView);
  const project = useProjectStore((s) => s.project);
  const rename = useProjectStore((s) => s.rename);
  const save = useProjectStore((s) => s.save);
  const open = useProjectStore((s) => s.open);
  const resetToNew = useProjectStore((s) => s.resetToNew);
  const loadDemo = useProjectStore((s) => s.loadDemo);
  const dirty = useProjectStore((s) => s.dirty);

  const running = useSimStore((s) => s.running);
  const start = useSimStore((s) => s.start);
  const stop = useSimStore((s) => s.stop);
  const reset = useSimStore((s) => s.reset);

  const switchView = (v: "eda" | "sim") => {
    if (v === "eda") stop();
    setView(v);
  };

  return (
    <header className="toolbar">
      <div className="brand">
        <span className="logo">◈</span>
        CircuitLab
      </div>
      <input
        className="project-name"
        value={project.name}
        onChange={(e) => rename(e.target.value)}
        title="Project name"
      />
      {dirty && <span style={{ color: "var(--text-faint)" }}>•</span>}

      <div className="tabs">
        <button className={view === "eda" ? "active" : ""} onClick={() => switchView("eda")}>
          EDA · Schematic
        </button>
        <button className={view === "sim" ? "active" : ""} onClick={() => switchView("sim")}>
          Simulate
        </button>
      </div>

      <span className="spacer" />

      {view === "sim" && (
        <div className="toolbar-actions">
          <span className={`run-dot${running ? " live" : ""}`} />
          {running ? (
            <button className="primary" onClick={stop}>
              ■ Stop
            </button>
          ) : (
            <button className="primary" onClick={() => start(project)}>
              ▶ Run
            </button>
          )}
          <button onClick={() => reset(project)}>↻ Reset</button>
        </div>
      )}

      <div className="toolbar-actions">
        <button className="ghost" onClick={resetToNew}>
          New
        </button>
        <button className="ghost" onClick={open}>
          Open
        </button>
        <button className="ghost" onClick={save}>
          Save
        </button>
        <button className="ghost" onClick={loadDemo} title="Load the built-in demo">
          Demo
        </button>
      </div>
    </header>
  );
}

function SimCodePanel({ mcuIds }: { mcuIds: string[] }) {
  if (mcuIds.length === 0) {
    return (
      <>
        <div className="panel-title">Microcontroller Code</div>
        <div className="empty">
          No microcontroller in the circuit.
          <br />
          Add an Arduino Uno from the library (in the EDA view) to write and run code.
        </div>
      </>
    );
  }
  // MVP: edit the first MCU's firmware.
  return (
    <>
      <div className="panel-title">Microcontroller Code</div>
      <CodeEditor componentId={mcuIds[0]} />
    </>
  );
}

export function App() {
  const view = useProjectStore((s) => s.view);
  const stop = useSimStore((s) => s.stop);
  const mcuIds = useMcuIds();

  // Stop the simulation if the component unmounts.
  useEffect(() => () => stop(), [stop]);

  return (
    <div className="app">
      <Toolbar />
      <div className="body">
        <aside className="left">
          {view === "eda" ? (
            <>
              <div className="panel-title">Components</div>
              <LibraryBrowser />
            </>
          ) : (
            <SimControls />
          )}
        </aside>

        <main className="center">
          <SchematicCanvas mode={view} />
        </main>

        <aside className="right">
          {view === "eda" ? <Inspector /> : <SimCodePanel mcuIds={mcuIds} />}
        </aside>
      </div>

      {view === "sim" && (
        <footer className="bottom">
          <div className="bottom-tabs">
            <button className="active">Serial Monitor</button>
          </div>
          <SerialMonitor componentId={mcuIds[0] ?? null} />
        </footer>
      )}
    </div>
  );
}
