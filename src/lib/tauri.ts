import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export interface SerialPortInfo {
  name: string;
  port_type: string;
}

export interface FlashResult {
  success: boolean;
  message: string;
  output: string;
}

export interface TestResult {
  success: boolean;
  message: string;
  events: string[];
  firmware_version: string | null;
  mac_address: string | null;
}

export interface ResetResult {
  success: boolean;
  message: string;
}

export interface FirmwareOption {
  id: number;
  name: string;
}

// Available firmware options
export const FIRMWARE_OPTIONS: FirmwareOption[] = [
  { id: 23, name: "MQTT V2 Temperature/Humidity Sensor" },
  // Add more firmware options here as needed
];

/**
 * List all available serial ports
 */
export async function listSerialPorts(): Promise<SerialPortInfo[]> {
  return invoke<SerialPortInfo[]>("list_serial_ports");
}

/**
 * Flash firmware to the device
 */
export async function flashFirmware(
  port: string,
  firmwareId: number
): Promise<FlashResult> {
  return invoke<FlashResult>("flash_firmware", {
    port,
    firmwareId,
  });
}

/**
 * Run production test on the device
 */
export async function runDeviceTest(port: string): Promise<TestResult> {
  return invoke<TestResult>("run_device_test", { port });
}

/**
 * Factory reset the device
 */
export async function factoryReset(port: string): Promise<ResetResult> {
  return invoke<ResetResult>("factory_reset", { port });
}

/**
 * Erase device flash
 */
export async function eraseDevice(port: string): Promise<ResetResult> {
  return invoke<ResetResult>("erase_device", { port });
}

/**
 * Listen for factory reset output events (real-time progress)
 */
export async function onResetOutput(callback: (line: string) => void): Promise<UnlistenFn> {
  return listen<string>("reset-output", (event) => {
    callback(event.payload);
  });
}

/**
 * Listen for erase output events (real-time progress)
 */
export async function onEraseOutput(callback: (line: string) => void): Promise<UnlistenFn> {
  return listen<string>("erase-output", (event) => {
    callback(event.payload);
  });
}

/**
 * Listen for flash output events (real-time progress)
 */
export async function onFlashOutput(callback: (line: string) => void): Promise<UnlistenFn> {
  return listen<string>("flash-output", (event) => {
    callback(event.payload);
  });
}

/**
 * Listen for test output events (real-time progress)
 */
export async function onTestOutput(callback: (line: string) => void): Promise<UnlistenFn> {
  return listen<string>("test-output", (event) => {
    callback(event.payload);
  });
}
