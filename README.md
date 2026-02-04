# NCD Sensor Programmer

A desktop application for programming, testing, and configuring NCD ESP32 sensors. Built with SvelteKit, Tauri, and ShadCN-Svelte.

## Features

- **Program Firmware**: Flash ESP32 firmware to devices via USB serial connection
- **Production Testing**: Run automated production test sequences with real-time output
- **Factory Reset**: Reset devices to factory defaults before shipping

## Supported Devices

- MQTT V2 Temperature/Humidity Sensor (Firmware ID: 23)

## Prerequisites

### System Requirements

- **Node.js** 18+ (20+ recommended)
- **Rust** (install via [rustup](https://rustup.rs/))
- **Python 3** with `pyserial` (for firmware flashing)

### Install Rust

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

After installation, restart your terminal or run:

```bash
source ~/.cargo/env
```

## Development

### Install Dependencies

```bash
npm install
```

### Run in Development Mode

```bash
# Start the Tauri app in development mode
npm run tauri dev
```

This will start both the Vite development server and the Tauri desktop application.

### Build for Production

```bash
npm run tauri build
```

The built application will be in `src-tauri/target/release/bundle/`.

## Configuration

### Flash Script

The firmware flash script (`ncd_flasher.py` and `esptool.py`) is bundled with the application in `src-tauri/resources/flasher/`. These files are automatically included when building the app.

### Serial Connection Settings

- Baud Rate: 115200
- Data Bits: 8
- Parity: None
- Stop Bits: 1
- Flow Control: None

## Usage

1. **Connect Device**: Connect your ESP32 sensor to a USB port
2. **Select Port**: Choose the serial port from the dropdown (click Refresh if needed)
3. **Select Firmware**: Choose the appropriate firmware for your device
4. **Program**: Click "Program" to flash the firmware
5. **Test**: Click "Test" to run production tests
6. **Factory Reset**: Click "Factory Reset" to prepare for shipping

## Test Events

The production test monitors these events:

| Event | Description |
|-------|-------------|
| `[EVENT:TEST_START]` | Test sequence started |
| `[TEST:WIFI_PASS]` | WiFi connection successful |
| `[TEST:MQTT_PASS]` | MQTT connection successful |
| `[TEST:SENSOR_PASS]` | Sensor reading successful |
| `[TEST:SPIFFS_PASS]` | File system check passed |
| `[EVENT:TEST_PASS]` | All tests passed |
| `[EVENT:TEST_FAIL]` | One or more tests failed |

## Project Structure

```
Production_Test_Software/
├── src/                    # SvelteKit frontend
│   ├── lib/
│   │   ├── components/ui/  # ShadCN UI components
│   │   ├── tauri.ts        # Tauri command wrappers
│   │   └── utils.ts        # Utility functions
│   └── routes/
│       └── +page.svelte    # Main application page
├── src-tauri/              # Tauri/Rust backend
│   ├── resources/
│   │   └── flasher/        # Bundled Python flash scripts
│   │       ├── ncd_flasher.py
│   │       └── esptool.py
│   ├── src/
│   │   ├── commands.rs     # Tauri commands
│   │   ├── lib.rs          # App entry point
│   │   └── main.rs         # Main executable
│   └── Cargo.toml          # Rust dependencies
├── package.json
└── README.md
```

## License

MIT
