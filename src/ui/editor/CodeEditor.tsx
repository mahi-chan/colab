/**
 * MCU code editor. Edits the Arduino-style source for a selected microcontroller
 * and lets the user load a bundled example (which carries verified precompiled
 * hex the emulator runs). Compiling edited source needs an arduino-cli backend
 * and is on the roadmap — noted in the UI so the boundary is honest.
 */
import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { cpp } from "@codemirror/lang-cpp";
import { EXAMPLES } from "../../core/sim/examples";
import { isIntelHex } from "../../core/sim/chips/hex";
import { useProjectStore } from "../../store/projectStore";

export function CodeEditor({ componentId }: { componentId: string }) {
  const project = useProjectStore((s) => s.project);
  const setSketch = useProjectStore((s) => s.setSketch);

  const sketch = project.simulation.sketches[componentId];
  const source = sketch?.source ?? "";
  const hasHex = !!sketch?.hex;

  const theme = useMemo(() => ({}), []);

  const loadExample = (id: string) => {
    const ex = EXAMPLES.find((e) => e.id === id);
    if (!ex) return;
    setSketch(componentId, ex.source, ex.hex);
  };

  const onChange = (value: string) => {
    // If the user pastes Intel HEX directly, treat it as loadable firmware.
    if (isIntelHex(value)) setSketch(componentId, value, value);
    else setSketch(componentId, value, sketch?.hex);
  };

  return (
    <div className="code-panel">
      <div className="code-toolbar">
        <span style={{ color: "var(--text-dim)" }}>Example:</span>
        {EXAMPLES.map((ex) => (
          <button key={ex.id} className="ghost" onClick={() => loadExample(ex.id)} title={ex.description}>
            {ex.name}
          </button>
        ))}
        <span className="spacer" />
        <span className="badge" style={{ color: hasHex ? "var(--accent-2)" : "var(--text-faint)" }}>
          {hasHex ? "firmware ready" : "no firmware"}
        </span>
      </div>
      <div className="code-scroll">
        <CodeMirror
          value={source}
          height="100%"
          theme="dark"
          extensions={[cpp()]}
          onChange={onChange}
          style={theme}
        />
      </div>
      <div className="note">
        Loading an example attaches verified precompiled firmware that runs on the emulator. Editing the
        C++ here does not recompile yet — an <kbd>arduino-cli</kbd> build service is on the roadmap. You can
        also paste an Intel-HEX image to run it directly.
      </div>
    </div>
  );
}
