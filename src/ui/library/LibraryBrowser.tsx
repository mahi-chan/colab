/**
 * Library Browser — the searchable "directory of all components". Groups the
 * catalog by category and adds a part to the schematic on click. Each row shows
 * a live SVG thumbnail of the actual schematic symbol.
 */
import { useMemo, useState } from "react";
import { CATALOG } from "../../core/library/catalog";
import { CATEGORY_LABELS, type ComponentCategory, type ComponentDef } from "../../core/library/types";
import { useProjectStore } from "../../store/projectStore";

function Thumb({ def }: { def: ComponentDef }) {
  const { width, height, body } = def.symbol;
  const pad = 8;
  return (
    <svg
      className="thumb"
      viewBox={`${-pad} ${-pad} ${width + pad * 2} ${height + pad * 2}`}
      preserveAspectRatio="xMidYMid meet"
    >
      <g dangerouslySetInnerHTML={{ __html: body }} />
    </svg>
  );
}

export function LibraryBrowser() {
  const [query, setQuery] = useState("");
  const addComponent = useProjectStore((s) => s.addComponent);

  const grouped = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (d: ComponentDef) =>
      !q ||
      d.name.toLowerCase().includes(q) ||
      d.keywords.some((k) => k.includes(q)) ||
      d.category.includes(q);
    const groups = new Map<ComponentCategory, ComponentDef[]>();
    for (const def of CATALOG) {
      if (!match(def)) continue;
      const list = groups.get(def.category) ?? [];
      list.push(def);
      groups.set(def.category, list);
    }
    return groups;
  }, [query]);

  const add = (defId: string) => {
    // Drop near the top-left of the working area; the user then drags it.
    addComponent(defId, 160 + Math.random() * 80, 140 + Math.random() * 80);
  };

  const totalShown = [...grouped.values()].reduce((n, l) => n + l.length, 0);

  return (
    <div className="library">
      <div className="search">
        <input
          placeholder="Search components…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <div className="list">
        {totalShown === 0 && <div className="empty">No components match “{query}”.</div>}
        {[...grouped.entries()].map(([cat, defs]) => (
          <div key={cat}>
            <div className="lib-category">{CATEGORY_LABELS[cat]}</div>
            {defs.map((def) => (
              <div
                key={def.id}
                className="lib-item"
                title={def.description}
                onClick={() => add(def.id)}
              >
                <Thumb def={def} />
                <div className="meta" style={{ minWidth: 0 }}>
                  <div className="name">{def.name}</div>
                  <div className="desc">{def.description}</div>
                </div>
                {def.model.kind === "none" && <span className="badge">symbol</span>}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
