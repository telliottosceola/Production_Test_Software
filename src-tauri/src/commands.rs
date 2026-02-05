use serde::{Deserialize, Serialize};
use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager};

/// Returns the appropriate Python command for the current platform
fn python_command() -> &'static str {
    if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    }
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SerialPortInfo {
    pub name: String,
    pub port_type: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct FlashResult {
    pub success: bool,
    pub message: String,
    pub output: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct TestResult {
    pub success: bool,
    pub message: String,
    pub events: Vec<String>,
    pub firmware_version: Option<String>,
    pub mac_address: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ResetResult {
    pub success: bool,
    pub message: String,
}

/// List all available serial ports
#[tauri::command]
pub fn list_serial_ports() -> Result<Vec<SerialPortInfo>, String> {
    let ports = serialport::available_ports()
        .map_err(|e| format!("Failed to list serial ports: {}", e))?;

    let port_infos: Vec<SerialPortInfo> = ports
        .into_iter()
        // On macOS, filter out /dev/tty.* ports - we only want /dev/cu.* (call-out devices)
        .filter(|p| {
            #[cfg(target_os = "macos")]
            {
                !p.port_name.starts_with("/dev/tty.")
            }
            #[cfg(not(target_os = "macos"))]
            {
                true
            }
        })
        .map(|p| {
            let port_type = match p.port_type {
                serialport::SerialPortType::UsbPort(info) => {
                    format!(
                        "USB - {}",
                        info.product.unwrap_or_else(|| "Unknown".to_string())
                    )
                }
                serialport::SerialPortType::PciPort => "PCI".to_string(),
                serialport::SerialPortType::BluetoothPort => "Bluetooth".to_string(),
                serialport::SerialPortType::Unknown => "Unknown".to_string(),
            };
            SerialPortInfo {
                name: p.port_name,
                port_type,
            }
        })
        .collect();

    Ok(port_infos)
}

/// Get the path to the bundled flasher script
fn get_flasher_path(app_handle: &AppHandle) -> Result<PathBuf, String> {
    // Try to get the resource path for bundled app
    if let Ok(resource_path) = app_handle.path().resource_dir() {
        let script_path = resource_path.join("flasher").join("ncd_flasher.py");
        if script_path.exists() {
            return Ok(script_path);
        }
    }
    
    // Fallback for development: look in src-tauri/resources
    let dev_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("resources")
        .join("flasher")
        .join("ncd_flasher.py");
    
    if dev_path.exists() {
        return Ok(dev_path);
    }
    
    Err("Could not find ncd_flasher.py in bundled resources".to_string())
}

/// Flash firmware to the device using the Python ncd_flasher script
/// Emits "flash-output" events for real-time progress
#[tauri::command]
pub async fn flash_firmware(app_handle: AppHandle, port: String, firmware_id: u32) -> Result<FlashResult, String> {
    let script_path = get_flasher_path(&app_handle)?;
    let script_dir = script_path.parent()
        .ok_or("Could not get script directory")?
        .to_path_buf();
    
    // Run the blocking operation in a separate thread
    let handle = app_handle.clone();
    let result = tokio::task::spawn_blocking(move || {
        let mut child = Command::new(python_command())
            .arg(&script_path)
            .arg("--port")
            .arg(&port)
            .arg("--firmware")
            .arg(firmware_id.to_string())
            .current_dir(&script_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to execute flash script: {}", e))?;

        let mut all_output = Vec::new();
        
        // Read stdout in real-time
        if let Some(stdout) = child.stdout.take() {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(line) = line {
                    // Emit event to frontend
                    let _ = handle.emit("flash-output", &line);
                    all_output.push(line);
                }
            }
        }
        
        // Read any remaining stderr
        if let Some(stderr) = child.stderr.take() {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(line) = line {
                    let _ = handle.emit("flash-output", &line);
                    all_output.push(line);
                }
            }
        }
        
        let status = child.wait().map_err(|e| format!("Failed to wait for process: {}", e))?;
        let combined_output = all_output.join("\n");
        let success = status.success() && combined_output.contains("Status: Success");

        Ok::<FlashResult, String>(FlashResult {
            success,
            message: if success {
                "Firmware flashed successfully".to_string()
            } else {
                "Firmware flash failed".to_string()
            },
            output: combined_output,
        })
    }).await.map_err(|e| format!("Task join error: {}", e))??;

    Ok(result)
}

/// Run production test on the device
/// Emits "test-output" events for real-time progress
#[tauri::command]
pub async fn run_device_test(app_handle: AppHandle, port: String) -> Result<TestResult, String> {
    // Run the blocking serial operations in a separate thread
    let handle = app_handle.clone();
    let result = tokio::task::spawn_blocking(move || {
        let mut serial = serialport::new(&port, 115200)
            .timeout(Duration::from_millis(100))
            .open()
            .map_err(|e| format!("Failed to open serial port: {}", e))?;

        // Set DTR and RTS low to prevent ESP32 reset/bootloader mode
        // On ESP32 boards, these lines control reset (RTS->EN) and boot mode (DTR->GPIO0)
        let _ = serial.write_data_terminal_ready(false);
        let _ = serial.write_request_to_send(false);
        
        // Small delay to let the lines settle
        std::thread::sleep(Duration::from_millis(50));

        // Send TEST command
        serial
            .write_all(b"TEST\r\n")
            .map_err(|e| format!("Failed to send TEST command: {}", e))?;
        serial.flush().map_err(|e| format!("Failed to flush: {}", e))?;

        let mut events: Vec<String> = Vec::new();
        let mut firmware_version: Option<String> = None;
        let mut mac_address: Option<String> = None;
        let mut test_passed = false;
        
        // Track required events for auto-detection of success
        let mut boot_complete = false;
        let mut wifi_connected = false;
        let mut mqtt_connected = false;
        let mut sensor_ok = false;
        let mut mqtt_publish_ok = false;

        let start = std::time::Instant::now();
        let timeout = Duration::from_secs(60);

        let mut reader = BufReader::new(serial.try_clone().map_err(|e| e.to_string())?);
        let mut line = String::new();

        while start.elapsed() < timeout {
            line.clear();
            match reader.read_line(&mut line) {
                Ok(0) => continue,
                Ok(_) => {
                    let trimmed = line.trim().to_string();
                    if !trimmed.is_empty() {
                        events.push(trimmed.clone());
                        
                        // Emit raw line to frontend for real-time display
                        let _ = handle.emit("test-output", &trimmed);
                        
                        // Note: We don't immediately trust [EVENT:TEST_PASS] or [EVENT:TEST_FAIL]
                        // from the device's internal test because it may run before MQTT connects.
                        // Instead, we wait for the actual connection events.
                        
                        // Track production events for auto-detection and emit status
                        if trimmed.contains("[EVENT:BOOT_COMPLETE]") {
                            boot_complete = true;
                            let _ = handle.emit("test-output", "[CHECK] ✓ Boot complete");
                            if let Some(fw) = extract_param(&trimmed, "FIRMWARE") {
                                firmware_version = Some(fw.clone());
                                let _ = handle.emit("test-output", &format!("[INFO] Firmware: {}", fw));
                            }
                            if let Some(mac) = extract_param(&trimmed, "MAC") {
                                mac_address = Some(mac.clone());
                                let _ = handle.emit("test-output", &format!("[INFO] MAC: {}", mac));
                            }
                        } else if trimmed.contains("[EVENT:WIFI_CONNECTED]") {
                            wifi_connected = true;
                            let _ = handle.emit("test-output", "[CHECK] ✓ WiFi connected");
                        } else if trimmed.contains("[EVENT:MQTT_CONNECTED]") {
                            mqtt_connected = true;
                            let _ = handle.emit("test-output", "[CHECK] ✓ MQTT connected");
                        } else if trimmed.contains("[EVENT:SENSOR_OK]") {
                            if !sensor_ok {
                                sensor_ok = true;
                                let _ = handle.emit("test-output", "[CHECK] ✓ Sensor OK");
                            }
                        } else if trimmed.contains("[EVENT:MQTT_PUBLISH_OK]") {
                            if !mqtt_publish_ok {
                                mqtt_publish_ok = true;
                                let _ = handle.emit("test-output", "[CHECK] ✓ MQTT publish OK");
                            }
                        }
                        
                        // Auto-detect success when all required events have been seen
                        if boot_complete && wifi_connected && mqtt_connected && sensor_ok && mqtt_publish_ok {
                            test_passed = true;
                            let _ = handle.emit("test-output", "[CHECK] ✓ All checks passed!");
                            break;
                        }
                    }
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::TimedOut => continue,
                Err(e) => return Err(format!("Read error: {}", e)),
            }
        }

        if test_passed {
            Ok::<TestResult, String>(TestResult {
                success: true,
                message: "All tests passed".to_string(),
                events,
                firmware_version,
                mac_address,
            })
        } else {
            // Build a message showing which events were missing
            let mut missing = Vec::new();
            if !boot_complete { missing.push("BOOT_COMPLETE"); }
            if !wifi_connected { missing.push("WIFI_CONNECTED"); }
            if !mqtt_connected { missing.push("MQTT_CONNECTED"); }
            if !sensor_ok { missing.push("SENSOR_OK"); }
            if !mqtt_publish_ok { missing.push("MQTT_PUBLISH_OK"); }
            
            let message = if missing.is_empty() {
                "Test timed out".to_string()
            } else {
                format!("Test timed out - missing events: {}", missing.join(", "))
            };
            
            Ok(TestResult {
                success: false,
                message,
                events,
                firmware_version: None,
                mac_address: None,
            })
        }
    }).await.map_err(|e| format!("Task join error: {}", e))??;

    Ok(result)
}

/// Factory reset the device
/// Emits "reset-output" events for real-time progress
#[tauri::command]
pub async fn factory_reset(app_handle: AppHandle, port: String) -> Result<ResetResult, String> {
    // Run the blocking serial operations in a separate thread
    let handle = app_handle.clone();
    let result = tokio::task::spawn_blocking(move || {
        let mut serial = serialport::new(&port, 115200)
            .timeout(Duration::from_millis(100))
            .open()
            .map_err(|e| format!("Failed to open serial port: {}", e))?;

        // Set DTR and RTS low to prevent ESP32 reset/bootloader mode
        // On ESP32 boards, these lines control reset (RTS->EN) and boot mode (DTR->GPIO0)
        let _ = serial.write_data_terminal_ready(false);
        let _ = serial.write_request_to_send(false);
        
        // Small delay to let the lines settle
        std::thread::sleep(Duration::from_millis(50));

        // Send FACTORY_RESET command
        serial
            .write_all(b"FACTORY_RESET\r\n")
            .map_err(|e| format!("Failed to send FACTORY_RESET command: {}", e))?;
        serial.flush().map_err(|e| format!("Failed to flush: {}", e))?;

        let _ = handle.emit("reset-output", "Sent FACTORY_RESET command...");

        let mut reader = BufReader::new(serial.try_clone().map_err(|e| e.to_string())?);
        let start = std::time::Instant::now();
        let timeout = Duration::from_secs(30);
        let mut reset_complete = false;
        let mut line = String::new();

        while start.elapsed() < timeout {
            line.clear();
            match reader.read_line(&mut line) {
                Ok(0) => continue,
                Ok(_) => {
                    let trimmed = line.trim();
                    if !trimmed.is_empty() {
                        let _ = handle.emit("reset-output", trimmed);
                    }
                    if trimmed.contains("Factory reset complete") || trimmed.contains("FACTORY_RESET_COMPLETE") {
                        reset_complete = true;
                        let _ = handle.emit("reset-output", "[CHECK] ✓ Factory reset complete");
                        break;
                    }
                }
                Err(ref e) if e.kind() == std::io::ErrorKind::TimedOut => continue,
                Err(e) => return Err(format!("Read error: {}", e)),
            }
        }

        Ok::<ResetResult, String>(ResetResult {
            success: reset_complete,
            message: if reset_complete {
                "Factory reset completed successfully".to_string()
            } else {
                "Factory reset timed out or failed".to_string()
            },
        })
    }).await.map_err(|e| format!("Task join error: {}", e))??;

    Ok(result)
}

/// Erase the device flash
/// Emits "erase-output" events for real-time progress
#[tauri::command]
pub async fn erase_device(app_handle: AppHandle, port: String) -> Result<ResetResult, String> {
    let script_path = get_flasher_path(&app_handle)?;
    let script_dir = script_path.parent()
        .ok_or("Could not get script directory")?
        .to_path_buf();
    
    // esptool.py is in the same directory as ncd_flasher.py
    let esptool_path = script_dir.join("esptool.py");
    
    // Run the blocking operation in a separate thread
    let handle = app_handle.clone();
    let result = tokio::task::spawn_blocking(move || {
        let _ = handle.emit("erase-output", "Starting flash erase...");
        
        // Using esptool v4.5.1 which has improved reset timing
        let mut child = Command::new(python_command())
            .arg(&esptool_path)
            .arg("--chip")
            .arg("esp32")
            .arg("--port")
            .arg(&port)
            .arg("erase_flash")
            .current_dir(&script_dir)
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to execute esptool: {}", e))?;

        let mut success = false;
        
        // Read stdout in real-time
        if let Some(stdout) = child.stdout.take() {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                if let Ok(line) = line {
                    let _ = handle.emit("erase-output", &line);
                    if line.contains("Chip erase completed") {
                        success = true;
                    }
                }
            }
        }
        
        // Read any remaining stderr
        if let Some(stderr) = child.stderr.take() {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(line) = line {
                    let _ = handle.emit("erase-output", &line);
                }
            }
        }
        
        let status = child.wait().map_err(|e| format!("Failed to wait for process: {}", e))?;
        success = success || status.success();

        if success {
            let _ = handle.emit("erase-output", "[CHECK] ✓ Flash erase complete");
        }

        Ok::<ResetResult, String>(ResetResult {
            success,
            message: if success {
                "Flash erased successfully".to_string()
            } else {
                "Flash erase failed".to_string()
            },
        })
    }).await.map_err(|e| format!("Task join error: {}", e))??;

    Ok(result)
}

/// Helper function to extract a parameter value from an event string
fn extract_param(line: &str, param: &str) -> Option<String> {
    let pattern = format!("{}=", param);
    if let Some(start) = line.find(&pattern) {
        let value_start = start + pattern.len();
        let rest = &line[value_start..];
        let end = rest.find(' ').unwrap_or(rest.len());
        Some(rest[..end].to_string())
    } else {
        None
    }
}
