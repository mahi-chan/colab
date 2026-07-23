/**
 * EDA inspector: edit the selected component's reference + parameters, rotate or
 * delete it, and show live ERC issues for the whole schematic.
 */
import { useMemo } from "react";
import { getComponentDef } from "../../core/library/catalog";
import { runErc } from "../../core/erc/erc";
import { useProjectStore } from "../../store/projectStore";

function ErcPanel() {
  const project = useProjectStore((s) => s.project);
  const select = useProjectStore((s) => s.select);
  const issues = useMemo(() => runErc(project), [project]);

  return (
    <div className="issues">
      <div className="panel-title">
        Electrical Rules
        <span className="badge">{issues.length}</span>
      </div>
      {issues.length === 0 ? (
        <div className="empty" style={{ padding: "14px 16px" }}>
          No issues found.
        </div>
      ) : (
        <div className="scrolllist" style={{ maxHeight: 220 }}>
          {issues.map((issue, i) => (
            <div
              key={i}
              className={`issue ${issue.severity}`}
              onClick={() => issue.componentId && select(issue.componentId)}
            >
              <span className="dot" />
              <span className="msg">{issue.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Inspector() {
  const project = useProjectStore((s) => s.project);
  const selectedId = useProjectStore((s) => s.selectedId);
  const updateParam = useProjectStore((s) => s.updateParam);
  const renameRef = useProjectStore((s) => s.renameRef);
  const rotateComponent = useProjectStore((s) => s.rotateComponent);
  const deleteComponent = useProjectStore((s) => s.deleteComponent);

  const comp = project.schematic.components.find((c) => c.id === selectedId);
  const def = comp ? getComponentDef(comp.defId) : undefined;

  return (
    <>
      <div className="panel-title">Properties</div>
      <div className="inspector" style={{ flex: "0 0 auto", maxHeight: "45%" }}>
        {!comp || !def ? (
          <div className="empty">
            Select a component to edit its properties.
            <br />
            Add parts from the library on the left.
          </div>
        ) : (
          <>
            <div className="prop-actions">
              <button onClick={() => rotateComponent(comp.id)}>Rotate</button>
              <button className="danger" onClick={() => deleteComponent(comp.id)}>
                Delete
              </button>
            </div>
            <div className="prop-row">
              <label>Type</label>
              <span style={{ color: "var(--text-dim)" }}>{def.name}</span>
            </div>
            <div className="prop-row">
              <label>Reference</label>
              <input value={comp.ref} onChange={(e) => renameRef(comp.id, e.target.value)} />
            </div>
            {def.params.map((p) => {
              const value = comp.params[p.key] ?? p.default;
              return (
                <div className="prop-row" key={p.key}>
                  <label>{p.label}</label>
                  {p.kind === "select" ? (
                    <select value={String(value)} onChange={(e) => updateParam(comp.id, p.key, e.target.value)}>
                      {p.options?.map((o) => (
                        <option key={o} value={o}>
                          {o}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={p.kind === "number" ? "number" : "text"}
                      value={String(value)}
                      onChange={(e) =>
                        updateParam(
                          comp.id,
                          p.key,
                          p.kind === "number" ? Number(e.target.value) : e.target.value,
                        )
                      }
                    />
                  )}
                  {p.unit && <span style={{ color: "var(--text-faint)" }}>{p.unit}</span>}
                </div>
              );
            })}
          </>
        )}
      </div>
      <ErcPanel />
    </>
  );
}
