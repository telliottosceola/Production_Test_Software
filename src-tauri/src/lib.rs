mod commands;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![
      commands::list_serial_ports,
      commands::flash_firmware,
      commands::run_device_test,
      commands::factory_reset,
      commands::erase_device,
    ])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
