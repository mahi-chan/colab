// CircuitLab desktop backend (Tauri v2). Exposes native open/save commands the
// desktop PlatformAdapter calls via `invoke`, using real file dialogs (rfd) and
// the filesystem. The frontend is the identical web build loaded in a native
// webview, so the app is one codebase across web and desktop.

use serde::Serialize;

#[derive(Serialize)]
struct OpenedProject {
    text: String,
    name: String,
}

#[tauri::command]
fn open_project() -> Option<OpenedProject> {
    let file = rfd::FileDialog::new()
        .add_filter("CircuitLab Project", &["clab", "json"])
        .pick_file()?;
    let text = std::fs::read_to_string(&file).ok()?;
    let name = file
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("project")
        .to_string();
    Some(OpenedProject { text, name })
}

#[tauri::command]
fn save_project(text: String, suggested_name: String) -> Result<(), String> {
    if let Some(path) = rfd::FileDialog::new()
        .add_filter("CircuitLab Project", &["clab", "json"])
        .set_file_name(format!("{}.clab", suggested_name))
        .save_file()
    {
        std::fs::write(path, text).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![open_project, save_project])
        .run(tauri::generate_context!())
        .expect("error while running CircuitLab");
}
