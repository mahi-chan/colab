/** Project (de)serialization with a schema version for forward migrations. */
import { SCHEMA_VERSION, type Project, type ProjectFile } from "./types";
import { uid } from "../util/id";

export function serializeProject(project: Project): string {
  const file: ProjectFile = {
    schemaVersion: SCHEMA_VERSION,
    app: "circuitlab",
    project: { ...project, updatedAt: Date.now() },
  };
  return JSON.stringify(file, null, 2);
}

export function deserializeProject(text: string): Project {
  const data = JSON.parse(text) as Partial<ProjectFile>;
  if (!data || data.app !== "circuitlab" || !data.project) {
    throw new Error("Not a valid CircuitLab project file.");
  }
  return migrate(data.project as Project, data.schemaVersion ?? 0);
}

/** Apply migrations from an older schema version to the current one. */
function migrate(project: Project, _fromVersion: number): Project {
  // No migrations yet (v1 is the first schema). Ensure required fields exist.
  return {
    ...project,
    id: project.id || uid("proj"),
    schematic: {
      components: project.schematic?.components ?? [],
      wires: project.schematic?.wires ?? [],
    },
    simulation: {
      sketches: project.simulation?.sketches ?? {},
      probes: project.simulation?.probes ?? [],
    },
  };
}

export function newProject(name = "Untitled Project"): Project {
  const now = Date.now();
  return {
    id: uid("proj"),
    name,
    createdAt: now,
    updatedAt: now,
    schematic: { components: [], wires: [] },
    simulation: { sketches: {}, probes: [] },
  };
}
