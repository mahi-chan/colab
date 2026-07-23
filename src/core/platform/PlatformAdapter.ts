/**
 * Platform abstraction. The web build and the Tauri desktop build each provide
 * an implementation; everything else in the app depends only on this interface,
 * which is what lets a single codebase target both.
 */
export interface OpenedProject {
  text: string;
  name?: string;
}

export interface PlatformAdapter {
  readonly kind: "web" | "desktop";
  /** Prompt the user to open a project file. Returns null if cancelled. */
  openProject(): Promise<OpenedProject | null>;
  /** Save project text, prompting for a location when appropriate. */
  saveProject(text: string, suggestedName: string): Promise<void>;
  /** Autosave the working project (best-effort, silent). */
  autosave(key: string, text: string): Promise<void>;
  /** Restore an autosaved project, or null if none. */
  loadAutosave(key: string): Promise<string | null>;
}
