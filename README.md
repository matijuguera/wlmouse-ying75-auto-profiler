# WLMouse Auto Profiler

Automatically switches your **WLKB YING 75** keyboard profile based on which application is running.

Launch a game → keyboard switches to your gaming profile. Close it → back to default.

![Python](https://img.shields.io/badge/Python-3.10+-blue) ![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey) ![License](https://img.shields.io/badge/License-MIT-green)

## How it works

The WLMouse YING 75 keyboard stores multiple profiles with different key configurations, actuation points, and lighting. The HID protocol was decoded by analyzing the JavaScript source of the official Web Hub configurator, allowing profile-switch commands to be sent directly from Python.

1. **Monitors running processes** — polls every second for processes matching your rules
2. **Sends HID command** — when a match is found, sends the profile-switch packet over USB
3. **Reverts on close** — when the matched process exits, switches back to your default profile

## Features

- Auto-connect to keyboard on launch
- Auto-start monitoring on launch
- Process → Profile mapping with file browser
- Manual profile switching
- Configurable default profile
- Minimize to system tray
- Start with Windows (registry-based)
- Single instance lock (prevents duplicate processes)
- Dark theme UI matching WLMouse branding

## Setup

```bash
pip install -r requirements.txt
python step3_auto_profiler.py
```

### Requirements

- Python 3.10+
- Windows 10/11
- WLMouse WLKB YING 75 connected via USB

## Project Structure

| File | Description |
|------|-------------|
| `step3_auto_profiler.py` | Main app — GUI, process monitoring, profile switching |
| `wlmouse_protocol.py` | HID protocol — packet builder for the WLKB YING 75 |
| `config.json` | User config — device info, profiles, rules, settings |
| `step1_hid_scanner.py` | Utility — lists all HID devices to find VID/PID |

## How the protocol was decoded

1. **Identified the device** using `hidapi` to enumerate HID devices and find the vendor-specific interface (`usage_page: 0xFFA0`)
2. **Analyzed the Web Hub source** — the official WLMouse web configurator JavaScript contains all protocol logic, including packet structures and command IDs
3. **Decoded the packets** — profile switch uses a 64-byte report with header `0x5C 0x04`, command byte `0x70`, and the profile ID in the payload

### Device Info

| Field | Value |
|-------|-------|
| Vendor ID | `0x36A7` |
| Product ID | `0xF887` |
| Usage Page | `0xFFA0` (vendor-specific) |
| Config Interface | 2 |
| Protocol Version | 1.0.7 |
| Firmware | App V1.0.2 |

## Disclaimer

This project is not affiliated with WLMouse. The HID protocol was decoded from the official Web Hub source for personal use. Use at your own risk.
