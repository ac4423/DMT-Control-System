# MCU Control Suite — README

## Contents
- [Project layout (important files & folders)](#project-layout-important-files-folders)
- [Quickstart](#quickstart)
  - [1 — Create & activate a venv](#1---create-activate-a-venv)
  - [2 — Install dependencies](#2---install-dependencies)
- [Applications — how to run & what they do](#applications---how-to-run-what-they-do)
  - [A. `mcu_terminal.py` — developer serial terminal (CLI + minimal UI)](#a-mcu_terminalpy--developer-serial-terminal-cli-minimal-ui)
  - [B. `GUI.py` — control GUI (Qt/PySide or similar)](#b-guipy--control-gui-qtpyside-or-similar)
  - [C. `test_manager.py` — automated/manual test harness](#c-test_managerpy--automatedmanual-test-harness)
  - [D. `comms_echo_emulator.py` (Linux only)](#d-commsechoemulatorpy-linux-only)
- [Firmware — `PWR_Control_F401RCT6` Overview, Architecture & Runtime Reference](#firmware--pwr_control_f401rct6-overview-architecture-runtime-reference)
  - [Key firmware modules](#key-firmware-modules)
  - [State transitions & important behaviors](#state-transitions-important-behaviors)
  - [Telemetry, heartbeat, ACK/NACK, CRC](#telemetry-heartbeat-acknack-crc)
- [Firmware — `PWR_Control_F401RCT6` - Module reference](#firmware--pwr_control_f401rct6-module-reference)
- [Authors & Project Info](#authors--project-info)

---

## Project layout (important files & folders)

---

```
.
├─ README.md
│
├─ mcu_comm/                       # shared serial driver + protocol for all apps
│  ├─ driver.py                    # MCUComm: open/close/register_callback/send helpers
│  └─ protocol.py                  # message / TLV constants & helpers
│
├─ mcu_terminal.py                 # main terminal entrypoint (selects UI backend)
├─ mcu_terminal_lib/               # terminal implementation
│  ├─ commands.py                  # CLI command processor
│  ├─ decode.py                    # packet decoder / prettifier
│  ├─ flowcalc.py                  # flow calculation & pulse debug
│  ├─ ui_linux.py                  # POSIX curses-like UI backend
│  └─ ui_windows.py                # Windows console UI backend
│
├─ GUI.py                          # GUI entrypoint
├─ Control_GUI/                    # GUI app sources
│  ├─ comms_manager.py             # comms glue for GUI
│  ├─ displays.py                  # widgets / display elements
│  └─ hardware.py                  # platform/hardware mapping
│
├─ test_manager.py
│
├─ comms_echo_emulator.py
│
├─ PWR_Control_F401RCT6/           # active STM32 firmware project
│  └─ (firmware source, headers, project files)
│
├─ PWR_Control_F103ZET6/           # older/unused firmware project
│  └─ (legacy project files)
│
├─ requirements_linux.txt
└─ requirements_windows.txt
```

---

## Quickstart

Minimal steps to get the repository running (Linux / Windows).

### 1 — Create & activate a venv

**Linux / macOS**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell)**
```powershell
python -m venv venv_windows
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv_windows\Scripts\Activate.ps1
```

### 2 — Install dependencies

**Linux**
```bash
pip install -r requirements_linux.txt
```

**Windows**
```powershell
pip install -r requirements_windows.txt
```

Both requirements files install the dependencies used by the three main Python apps in the repo:  
`mcu_terminal.py`, `test_manager.py`, and `GUI.py`.

There is an additional helper `comms_echo_emulator.py` (Linux-only) used for virtual-port echo testing.

---

## Applications — how to run & what they do

This section documents the three Python apps and the small Linux-only emulator script.

---

### A. `mcu_terminal.py` — Quick start + full reference

Below are two parts: a **Quick Start** you can follow in 30 seconds, and a **Comprehensive Reference** that explains every useful command, behaviour and gotcha you’ll need while developing and debugging.

---

#### Quick Start

1. **Open the terminal app pointing at your serial port:**

   **Linux:**
   ```bash
   python3 mcu_terminal.py --port /dev/ttyUSB0
   ```

   **Windows:**
   ```powershell
   python .\mcu_terminal.py --port COM3
   ```

2. **Send a handshake (use defaults or override):**
   ```
   h --hb 200 --tel 500 --send-ack 1 --extra 0A0B
   ```
   Output:
   ```
   [TX] HANDSHAKE SEQ=12 HB=200ms TEL=500ms ACKFLAG=1 EXTRA=0a0b
   ```

3. **See live packets in the top pane; type `help` in the bottom CLI for commands.**

4. **Send a desired flow:**
   ```
   flow 150
   ```
   Output:
   ```
   [TX] DESIRED_FLOW SEQ=34 FLOW=150mL/min
   ```

5. **Pause the live stream if you need to inspect or run a long command:**
   ```
   pause
   resume
   ```

That’s it — you can now transmit TLVs, raw frames, or use the UI controls.

---

#### Comprehensive Reference (concise, precise, and practical)

##### Overall purpose & UX

`mcu_terminal.py` is an interactive developer terminal that:

- Sends framed messages (handshake, config TLVs, commands).
- Receives and decodes framed packets from the MCU (telemetry, debug messages).
- Shows a scrolling packet window (top) and interactive CLI (bottom).
- Supports command history, pause/resume, and developer emulation helpers.

**Top window** = live decoded packet stream.  
**Bottom** = CLI.  
Use `pause` to freeze the stream (buffered packets kept), `resume` to flush.

---

##### CLI flags (examples)

- `--port` (required) — serial device / COM port
- `--baud` (default `256000`)
- `--hb` heartbeat period in ms (default `500`)
- `--tel` telemetry period in ms (default `5880`)
- `--send-ack` `0|1` (default `1`)
- `--extra` extra bytes (hex)
- `--packet-lines` (default `16`) — top window height
- `--cmd-lines` (default `30`) — bottom window height

**Example with overrides:**
```bash
python3 mcu_terminal.py --port /dev/ttyUSB0 --hb 200 --tel 500 --baud 256000 --send-ack 1
```

---

##### Command list (with examples and notes)

- **help**  
  Prints the built-in help text.

- **q, quit, exit**  
  Exit the application cleanly.

- **status**  
  Show current runtime defaults and UI sizes.  
  Example output:
  ```
  [STATUS] defaults: hb=500ms tel=5880ms send_ack=1 extra=.. baud=256000 port=/dev/ttyUSB0
  [STATUS] ui: packet_lines=16 cmd_lines=30 packets_paused=OFF buffered=0
  ```

- **set `<key>` `<value>`** — change runtime defaults or UI sizes  
  Keys: `hb`, `tel`, `send-ack`, `extra`, `baud`, `port`, `packet_lines`, `cmd_lines`  
  Examples:
  ```
  set hb 200
  set extra DEADBE  # hex string, stored as bytes
  set packet_lines 30
  set send-ack 0
  ```

- **h, handshake [--hb N] [--tel N] [--send-ack 0|1] [--extra HEX]**  
  Send handshake. If `--extra` omitted, uses `defaults["extra"]`. Printed TX shows sequence and parameters.

- **send `<hex>`**  
  Send raw bytes (frame or arbitrary). Input accepts spaces or contiguous hex:
  ```
  send A5 10 00 05 ...
  send a5100005...
  ```
  Errors: invalid hex or serial port closed will print an error.

- **flow `<mL/min>` (alias `f`)**  
  Send scheduled desired flow (queued). Example:
  ```
  flow 100
  [TX] DESIRED_FLOW SEQ=17 FLOW=100mL/min
  ```

- **flow-immediate `<mL/min>` (aliases `flow-now`, `fi`)**  
  Send immediate desired flow.

- **pwm `<0..99>` (alias `set-pwm`, `set_pwm`)**  
  Directly set pump PWM duty (MCU enters SYS_DEBUG). Accepts integers 0..99; out-of-range raises error.

- **exit-debug (alias `exitdebug`)**  
  Exit SYS_DEBUG on MCU and return to the regular running mode.

- **pause / resume**  
  Pause/resume live packet display. `pause` toggles if no argument; or accept `on|off|1|0`.

- **sys filters**  
  List packet type filters (which packet types are suppressed in the UI).

- **sys filter `<type>` hide|show**  
  Suppress or show packets of a given message type. Accepts decimal or hex (e.g. `0x32`). Example:
  ```
  sys filter 0x32 hide
  # hides MSG_FLOWMETER_PULSE_DEBUG
  ```

- **1 / emu1 and 2 / emu2**  
  Developer-only: write raw emulated ACK packets to the serial line for stepper emulation. Useful when testing UI handling of legacy raw messages.

---

##### config command — TLV helper (most powerful command)

**Usage:**
```
config <tag> <value>
config raw <hexpayload>
config tlv <hexpayload>
```

Friendly tag names map to numeric TLV tags (examples below). If you pass a numeric tag instead (e.g. `0x0A`) it will accept hex/decimal and try to parse the value by tag size.

**Common friendly tag names and types:**

| Friendly Name                | Tag Constant                        | Type         |
|------------------------------|-------------------------------------|--------------|
| telemetry                    | CONFIG_TAG_TELEMETRY_PERIOD_MS      | u16 (ms)     |
| hb, heartbeat                | CONFIG_TAG_HEARTBEAT_PERIOD_MS      | u16 (ms)     |
| kp                           | CONFIG_TAG_PI_KP                    | float (f32)  |
| ki                           | CONFIG_TAG_PI_KI                    | float (f32)  |
| enable_pi                    | CONFIG_TAG_ENABLE_PI_CONTROL        | u8 (0/1)     |
| enable_usb_serial_debug      | CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG  | u8           |
| usb_debug                    | CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG  | u8           |
| serial_send_ms               | CONFIG_TAG_SERIAL_SEND_MS           | u16 (ms)     |
| pwm_debug                    | CONFIG_TAG_PWM_DEBUG                | u8           |
| enable_echo_debug            | CONFIG_TAG_ENABLE_ECHO_DEBUG        | u8           |
| flow_window_ms               | CONFIG_TAG_FLOW_WINDOW_MS           | u16 (ms)     |
| flow_pulses_per_litre        | CONFIG_TAG_FLOW_PULSES_PER_LITRE    | u32          |
| pulses_per_litre             | CONFIG_TAG_FLOW_PULSES_PER_LITRE    | u32          |
| enable_lookup_table          | CONFIG_TAG_ENABLE_LOOKUP_TABLE      | u8           |
| lookup_table                 | CONFIG_TAG_ENABLE_LOOKUP_TABLE      | u8           |
| pump_sample_time_ms          | CONFIG_TAG_PUMP_SAMPLE_TIME_MS      | u16 (ms)     |
| flowpulse_debug              | CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG | u8 (0/1)  |
| flow_pulse_debug             | CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG | u8 (0/1)  |

**Examples:**

- Set telemetry period to 200 ms:
  ```
  config telemetry 200
  [TX] MSG_CONFIG SEQ=45 TAG=0x01 VAL=200
  ```

- Set PI constants:
  ```
  config kp 0.002
  config ki 0.0015
  [TX] MSG_CONFIG SEQ=46 TAG=0x03 VAL=0.002
  ```
  (these use 4-byte IEEE754 little-endian encoding under the hood)

- Enable a debug flag:
  ```
  config enable_usb_serial_debug 1
  [TX] MSG_CONFIG SEQ=47 TAG=0x06 VAL=1
  ```

- Set pulses per litre (u32):
  ```
  config flow_pulses_per_litre 1000
  [TX] MSG_CONFIG SEQ=48 TAG=0x0B VAL=1000
  # value encoded as little-endian 4 bytes: 0xE8 0x03 0x00 0x00
  ```

- Send a raw TLV payload (you compose tag/len/value bytes yourself):
  ```
  config raw 0B04E8030000
  # sends payload bytes exactly as provided in hex
  ```

**Behavioural note:** when you toggle `CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG`, the CLI will try to enable/disable the PC-side flow calculator (`flow_calc.set_enabled(bool)`) if that helper is available, and print an `[INFO]` message.

**Fallback:** unknown tags accept a raw hex value: `config 0x99 deadbeef`.

---

##### What the driver (`mcu_comm.driver.MCUComm`) provides (useful for scripting / advanced use)

**Public convenience methods (examples):**
- `send_frame(msg_type:int, payload:bytes) -> seq`
- `send_handshake(hb_ms, tel_ms, send_ack:bool, extra:bytes=b"")`
- `send_desired_flow(flow_ml_per_min:int)` — scheduled
- `send_desired_flow_immediate(flow_ml_per_min:int)` — immediate
- `send_config(fields: list[(tag,value_bytes)])` — build and send TLV payload
- `send_config_u16(tag, value)`, `send_config_u8(tag, value)`, `send_config_f32(tag, value)`
- `send_set_pump_pwm(duty:int)` — duty 0..99
- `send_exit_sys_debug()` — no payload
- `send_stepper_go_home(slave_addr=0x03)`, `send_stepper_set_middle()`, `send_stepper_move_to(steps, ...)`

**Tip:** `send_frame` will raise `RuntimeError("Serial port not open")` if the port is closed — handle that in scripts.

---

##### Telemetry decoding (what you’ll see, and how to read it)

Telemetry payload is fixed-length: 21 bytes with the following fields (little-endian):

```
[ts:u32][state:u8][flow1:u32][total1:u32][flow2:u32][total2:u32]
```

Decoded dict:
```python
{
  "ts": <uint32>,
  "state": <uint8>,
  "flow1": <uint32>,   # mL/min
  "total1": <uint32>,  # mL
  "flow2": <uint32>,   # mL/min (secondary)
  "total2": <uint32>,  # mL (secondary)
}
```

If a telemetry payload length is wrong the decoder raises a `ValueError` and the terminal logs a decode failure. The driver registers an internal telemetry handler; you can also register callbacks:

- `register_telemetry_callback(cb)` — `cb(tel_dict)`
- `get_latest_telemetry()` — returns the last parsed dict or None
- `get_latest_secondary_flow()` — convenience to return flow2 or None

---

##### Raw framing and CRC

Frames are built with header `0xA5`, a 1-byte message type, 1-byte seq, 1-byte length, payload, and a 1-byte XOR CRC (`type ^ seq ^ each payload byte`). Use `send_frame()` or the high-level wrappers — they set sequence numbers and verify payload length.

---

##### Emulation helpers

`emu1` / `emu2` write small legacy raw packets used by older stepper code. Helpful for exercising legacy parsing paths or UI display of non-framed messages.

---

##### Troubleshooting & common errors

- **serial not open** — you tried to send while the port is closed. Use `--port` and ensure the device is present and not used by another app.
- **invalid hex** — hex parsing for `send` or `config raw` failed; ensure you only use 0-9A-F characters and an even count of digits.
- **u16/u8 out of range** — `send_config_u16` / `u8` validate ranges (`u16 ≤ 65535`, `u8 ≤ 255`). `send_set_pump_pwm` validates 0..99.
- **Telemetry decode errors** — mismatch in telemetry length; check MCU firmware and terminal's `TELEMETRY_LEN` (currently 21).
- If you toggle `flowpulse_debug` and nothing seems to change, check that the MCU firmware supports the tag and that `MSG_FLOWMETER_PULSE_DEBUG` (type `0x32`) is being emitted.

---

##### Example session (compact)

```
> h --hb 200 --tel 500 --send-ack 1
[TX] HANDSHAKE SEQ=12 HB=200ms TEL=500ms ACKFLAG=1 EXTRA=
< RX telemetry ... >   # live decoded telemetry lines in the top pane

> config kp 0.002
[TX] MSG_CONFIG SEQ=13 TAG=0x03 VAL=0.002

> flow 150
[TX] DESIRED_FLOW SEQ=14 FLOW=150mL/min

> pause
[CMD] packets paused
# do some commands
> resume
[CMD] packets resumed
# buffered lines are flushed to top pane
```

---

##### Advanced: programmatic usage pattern

If you embed `MCUComm` in another script, typical usage:

```python
from mcu_comm.driver import MCUComm
with MCUComm("/dev/ttyUSB0", baud=256000) as comm:
    seq = comm.send_handshake(200, 500, True, extra=b"\x01")
    comm.register_callback(None, lambda pkt: print("any packet:", pkt))
    comm.register_telemetry_callback(lambda tel: print("telemetry:", tel))
    comm.send_desired_flow(100)   # schedule
```

---

##### Final tips

- Use `sys filter` to reduce noise from frequent debug packets when you want to focus on telemetry or specific message types.
- Keep `packet_lines` large enough to capture useful context but not too large to hide the CLI.
- Use `config raw` when you need to reproduce a specific TLV byte pattern exactly.
- The terminal is intentionally low-level — use it to exercise specific firmware paths or to debug framing/CRC/telemetry issues before building higher-level GUIs.


### B. `GUI.py` — control GUI (Qt/PySide or similar)

**Location:** `GUI.py`  
**Primary helpers:**  
- `Control_GUI/comms_manager.py`
- `Control_GUI/displays.py`
- `Control_GUI/hardware.py`

Uses the shared driver/protocol modules (`mcu_comm.driver`, `mcu_comm.protocol`) when available.

#### Quick start — run the GUI

From the repository root (venv active, dependencies installed):

```bash
# Run with default serial port (see comms_manager.SERIAL_PORT)
python Control_GUI/GUI.py

# Override serial port and optionally baud:
python Control_GUI/GUI.py -p /dev/ttyUSB1
python Control_GUI/GUI.py -p COM3 -b 115200
```

Typical exit:  
```python
sys.exit(app.exec())
```

#### Dependencies (high level)

Make sure your environment has at least:

- `PyQt6`
- `pyqtgraph`
- `pyserial`
- *optional*: `mcu_comm` package (driver + protocol)

If `mcu_comm` is not present, the GUI will fall back to a legacy serial listener and the built-in simulator.

---

#### What the GUI provides (compact overview)

- **Left control panel:**
  - Stepper motor controls (Home, Middle, set absolute position in mm)
  - Flow controls (immediate set, delayed set with ms delay)
  - Experiment controls (Run Dynamic / Run Static)
- **Right dashboard:**
  - Plots (motor height, pump RPM, injection flow, main flow)
  - Status indicators (LASERS, INJECTION VALVE)
  - Visual diagram tracking laser height

The GUI re-uses the same comms and protocol stack as the terminal app via `Control_GUI/comms_manager.py`:

- Prefers the higher-level `MCUComm` driver when available
- Falls back to raw pyserial + `CommsListener` when the driver is missing or fails
- Built-in simulator (`DataGeneratorThread`) runs automatically when no real comms are detected

---

#### Detailed / comprehensive usage and internals

##### Startup behaviour & CLI options

- `-p` / `--port` — serial port (default from `Control_GUI/comms_manager.SERIAL_PORT`)
- `-b` / `--baud` — optional baud override (if not provided, `CommsManager` uses its `BAUD_RATE`)

`MainWindow` is instantiated with `comms_port=args.port` and creates `CommsManager(port, baud)` internally.  
If you want baud propagated to the manager, the script includes commented guidance to set `window.comms.baud` after construction.

---

##### Comms architecture — how the GUI talks to the device

`Control_GUI/comms_manager.py` wraps two models:

**Primary (preferred): MCUComm driver**
- If `mcu_comm.driver.MCUComm` can be imported and opened, `CommsManager` instantiates it and registers a callback for telemetry packets.
- When available, higher-level helper functions on `MCUComm` are used for sending (e.g. `send_stepper_move_to`, `send_desired_flow`), preserving driver sequence handling and decoding.

**Fallback: legacy serial framing**
- If the driver is unavailable or fails, `CommsManager` opens a `pyserial.Serial` and starts `CommsListener` (a `QThread`) that reads and parses framed packets from the serial stream.
- The fallback implements the original frame format (header `0xA5`, sequence byte, length, payload, CRC) and decodes telemetry.

**CommsManager exposes:**
- Qt signal `telemetry_data(ts, state, flow, vol, pos)` — used across the GUI
- Send helpers (compat API):  
  - `send_go_home`
  - `send_set_middle`
  - `send_move_to(steps, slave_addr=0x03, speed=1000, acc=150)`
  - `send_desired_flow(ml_per_min, immediate=False)`
- `get_mcu()` — returns the underlying `MCUComm` object or `None` (useful for advanced access / diagnostics)
- `close()` — stops driver/listener and closes serial

---

##### Message IDs / legacy mapping

- `MSG_TELEMETRY` default: `0x03` (used as the telemetry message id in legacy decoding)
- Movement / control IDs:  
  - `MSG_GO_HOME = 0x41`
  - `MSG_SET_MIDDLE = 0x42`
  - `MSG_POSITION_MODE2 = 0x43` (Move-to absolute steps)
- These are used by the fallback raw sender.

---

##### Telemetry format (what the GUI expects)

Legacy telemetry payload: `'<IBIIiI'` (21 bytes), unpacked as:

- `ts` (unsigned int) — timestamp (ms)
- `state` (unsigned char)
- `flow` (unsigned int) — primary flow (mL/min)
- `vol` (unsigned int)
- `pos` (signed int) — motor encoder steps
- `rsv` (unsigned int) — reserved

The GUI's `telemetry_data` Qt signal keeps the legacy shape: `(ts, state, flow, vol, pos)`.

`MainWindow._on_telemetry` is defensive — accepts either the legacy 5-arg tuple or a single dict (if the `MCUComm` driver later emits richer decoded telemetry).

**Unit notes:**  
Flows from telemetry are in mL/min. Within some GUI paths they're converted to mL/s (divide by 60) for display/update functions that expect mL/s.

---

##### How the GUI maps user actions → comms

- **Home (`btn_home`)** → sends `comms.send_go_home(slave_addr=0x03)`
- **Middle (`btn_middle`)** → `comms.send_set_middle()`
- **Set Position (mm) (`spin_target` → `btn_set_pos`)** → GUI converts mm to motor steps and calls `comms.send_move_to(steps)`. The conversion used in the GUI is:
  ```
  steps = (mm / 10.0) * 360.0 / 1.8
  ```
  (this is the current implementation — see "conversion consistency" below)
- **Set Flow (immediate)** → GUI currently updates the simulator and uses `send_desired_flow` when integrated with hardware (call path exists in `comms_manager`)
- **Set Flow (delayed)** → sets a delayed command in the simulator (`SET_FLOW_DELAYED`), and the comms layer exposes `send_desired_flow(..., immediate=True)` for immediate requests when the MCU driver supports it
- **Run Dynamic/Static** → GUI toggles simulator modes (wave-run / hold) and updates dashboard visuals and status indicators. When real comms are present, the dynamic/static actions should be synchronized with firmware commands (extend UI to call driver helpers if needed)

---

##### Simulator — DataGeneratorThread behaviour & command mapping

Use this to run the GUI without hardware; it starts automatically if `CommsManager` detects no real comms (neither MCU driver nor open serial).

**Key commands accepted by `DataGeneratorThread.set_command()`:**

- `"HOME"` → linear move to `MIN_ENCODER_VAL`
- `"MIDDLE"` → linear move to `MIDDLE_ENCODER_VAL`
- `"MOVE_TO"` with `value=mm` → sets encoder target = `value * UNITS_PER_MM`
- `"SET_FLOW_IMMEDIATE"` with `value=rate` → `flow_setpoint = value * 60.0` (GUI spin boxes are in mL/s; simulator converts to mL/min)
- `"SET_FLOW_DELAYED"` with `value=rate`, `extra=delay_ms` → schedules flow change after `delay_ms`
- `"RUN_DYNAMIC"` → start wave mode
- `"STOP"` → halt/run stop

**Important units detail:**  
GUI flow spin boxes show mL/s. The simulator internally tracks flows in mL/min (hence the `* 60` when the GUI passes values). When integrating with hardware via `send_desired_flow`, the comms helper expects mL/min (or will convert as needed) — confirm before sending to the actual MCU.

---

##### Dashboard / plotting

`DashboardWidget` provides four scrolling plots:

- Motor (height in mm)
- Pump RPM
- Flowmeter Injection (mL/min)
- Flowmeter Main (mL/min)

Plots are driven by either:

- `DashboardWidget.update_plots(times, motors, injs, mains, pumps)` — bulk updates (used by simulator)
- `DashboardWidget.add_telemetry_point(ts_ms, motor_steps, flow1_ml_min, flow2_ml_min, pump_rpm)` — single-sample update (used by `MainWindow._handle_telemetry`)

**Motor encoder → mm conversion currently used in the display code:**
```
motor_mm = (motor_steps / 16384.0) * 10.0
```
(this maps 16384 encoder units → 10 mm in the plotting code)

The dashboard also updates a laser visual (`laser_line`) to reflect current height.

---

##### Conversion inconsistencies you should know about (and fix)

There are multiple conversion constants in the codebase:

- `hardware.py`: `UNITS_PER_MM = 1638.4`
- `displays.py`: uses `/ 16384.0 * 10.0` when converting steps → mm
- `GUI.py` (set position): formula converting mm → steps uses stepper-angle math `(mm/10) * 360 / 1.8`

These three use different conventions.  
**Action:** pick a single canonical conversion (preferably `UNITS_PER_MM`) and use it across:

- GUI when computing steps to send
- `DataGeneratorThread` when mapping mm → encoder units
- `DashboardWidget` when converting encoder units → mm

(Keeping conversions consistent avoids 10× errors and mismatched visual behaviour.)

---

##### Signal / API compatibility & robustness

- `CommsManager.telemetry_data` is the single Qt signal the rest of the GUI expects. That signal currently emits the legacy five-argument tuple; the GUI code accepts either that or a dict decoded by `MCUComm`.
- `MainWindow._on_telemetry`:
  - Converts primary/secondary flows from mL/min → mL/s for `dashboard.update_flow_rates` (if available)
  - If `dashboard.update_flow_rates` doesn't exist, falls back to `dashboard.update_plots` or prints debug info
- `CommsManager._on_mcu_packet` decodes raw `MSG_TELEMETRY` payloads into the legacy tuple and emits `telemetry_data` — keeping backward compatibility with the original UI

---

##### Threading & shutdown

- `CommsListener` and `DataGeneratorThread` are `QThread` subclasses. The GUI connects their signals to main-thread slots — Qt takes care of thread-safety for signals.
- On window close (`MainWindow.closeEvent`) the GUI:
  - Calls `self.comms.close()` to stop `MCUComm` or fallback listener, close serial
  - Calls `self.generator.stop()` to stop simulator thread
- **Always use `close()` / `stop()` to join background threads cleanly.**

---

##### Debugging & troubleshooting checklist

- **If telemetry never appears:**
  - Verify the correct serial port and permissions (Linux: add user to `dialout` or use `sudo` for testing)
  - Check whether `CommsManager` printed `connected via MCUComm` or `legacy serial connected` on startup
  - If `mcu_comm` import fails, you will see the fallback message — install/point `PYTHONPATH` to your `mcu_comm` package if you intend to use the driver

- **If plots show strange scales:**
  - Confirm encoder→mm conversion constants (see "Conversion inconsistencies")
  - Check whether flows are in mL/min vs mL/s at each call site

- **If GUI freezes:**
  - Look for blocking operations on the GUI thread. Comms reading should be in worker threads (`MCUComm` reader or `CommsListener`); ensure any heavy processing is not done directly in signal handlers

- **If images don't show:**
  - Dashboard loads `Control_GUI/assets/RPV_Diagram.png` or `Control_GUI/RPV_Diagram.png`. Ensure assets folder exists and the image file is at one of the checked paths

---

##### Extending or integrating

- **To add additional commands or telemetry fields:**
  - Extend `CommsManager` helpers to call `MCUComm` methods if available (or add a new legacy framing branch)
  - Emit richer telemetry dicts from `CommsManager._on_mcu_packet` and update `MainWindow._on_telemetry` to handle them

- **To expose baud on MainWindow start:**
  - Add `baud` to `MainWindow.__init__` and pass down to `CommsManager(port, baud)`

- **To make simulator optional:**
  - Add a `--no-sim` CLI flag to force simulator off even if no comms found

- **To improve unit consistency:**
  - Move unit constants into a single `Control_GUI/constants.py` used by `GUI.py`, `displays.py`, and `hardware.py`

---

##### Quick reference (mapping summary)

**UI buttons → CommsManager calls:**

- Home → `CommsManager.send_go_home(slave_addr=0x03)`
- Middle → `CommsManager.send_set_middle()`
- Set position (mm) → `CommsManager.send_move_to(steps)`
- Set flow immediate → `CommsManager.send_desired_flow(ml_per_min, immediate=True)` (when `MCUComm` supports it)
- Set flow delayed → GUI simulator internal scheduling (`SET_FLOW_DELAYED`) — add comms call if hardware must accept delayed commands

**Telemetry signal:**  
`telemetry_data(ts, state, flow, vol, pos)` (flow in mL/min, pos = encoder steps)

**Simulator commands accepted:**  
`HOME`, `MIDDLE`, `MOVE_TO` (value=mm), `SET_FLOW_IMMEDIATE` (value in mL/s), `SET_FLOW_DELAYED` (value in mL/s, extra=delay_ms), `RUN_DYNAMIC`, `STOP`.

---



### C. `test_manager.py` — automated/manual test harness

#### Quick Start

1. **Edit the serial port and baud rate in the script:**

   Find the line near `FlowTester('COM3', 256000)` and change `'COM3'` and `256000` to match your device (e.g., `/dev/ttyUSB0`, `115200`), or modify the script to accept CLI arguments.

2. **Run the test harness:**

   ```bash
   python test_manager.py
   ```

3. **When connected, you’ll see:**

   ```
   Connected to <port>. Type 'Test 1', 'Test 2', or 'Test 3'.
   ```

4. **Type `Test 1`, `Test 2`, or `Test 3` at the prompt to run a test.**  
   Press `Ctrl-C` to stop and close the port.

**Safety:**  
This script directly controls the pump PWM. **Ensure the motor/pump is safe to run** (no blocked tubing, no human contact with moving parts), and always bench-test with the pump unloaded.

---

#### Purpose (one line)

A small interactive harness that opens an MCU serial port and runs three prebuilt pump tests (ramp, steady hold, emergency step-down) in background threads so the CLI remains responsive.

---

#### Behaviour summary (concise, exact)

- Opens the serial device using `mcu_comm.driver.MCUComm` and waits 1.0 s for MCU initialization.
- Prompts for user commands: `Test 1`, `Test 2`, `Test 3`.
- Each test is launched in a daemon thread and controlled via a `running_test` flag so the main loop stays responsive.
- If a test is running and you start another, the harness requests the running test to stop and joins it with a 0.5 s timeout before starting the new one.
- On `KeyboardInterrupt`, the script sets `running_test = False`, joins threads, and closes the serial port cleanly.

---

#### Tests (exact behaviour)

- **Test 1 — Ramp:**  
  PWM from 0% → 90% in 5% increments, 1 s between increments. After completion, sends `PWM=0` to stop the motor.

- **Test 2 — Hold:**  
  Sets PWM to 99% and holds for 20 s (configurable in code), then sends `PWM=0`.

- **Test 3 — Emergency step-down:**  
  Steps PWM through `[75, 50, 25, 0]`, waiting 2 s between steps. Aborts early if `running_test` is cleared.

*(The script uses `self.mcu.send_set_pump_pwm(value)` to set PWM — the driver must implement this call and `open()/close()`.)*

---

#### Implementation notes & gotchas

- **Edit port/baud:**  
  The shipped script hardcodes the port and baud — change `FlowTester('COM3', 256000)` to your device (`/dev/ttyUSB0`, `/dev/pts/X`, etc.) or add a simple `argparse` wrapper.

- **Driver dependency:**  
  Requires `mcu_comm.driver.MCUComm` to expose `.open()`, `.close()`, `.port`, and `.send_set_pump_pwm()`.

- **Thread join behaviour:**  
  The code calls `join(timeout=0.5)` when stopping a previous test to avoid blocking the CLI; tests should check `running_test` frequently so they exit promptly.

- **Safety reset:**  
  Tests explicitly send `PWM=0` at the end as a safety measure — do not remove this unless you understand the consequences.

- **Extendable:**  
  Simple to add tests (create a new `run_test_X` and handle it in `handle_input`). Consider adding CLI arguments, logging, or telemetry reading during tests.

---

### D. `comms_echo_emulator.py` (Linux only)

#### Quick Start

1. **Create two virtual serial endpoints (example using socat):**

   ```bash
   sudo apt install socat
   socat -d -d pty,raw,echo=0 pty,raw,echo=0
   # socat prints two /dev/pts/X paths
   ```

2. **Run the emulator on one of the endpoints:**

   ```bash
   python comms_echo_emulator.py /dev/pts/4
   ```

3. **Connect `mcu_terminal.py` (or any host) to the other endpoint** (`/dev/pts/3`) to test end-to-end comms.

---

#### Purpose & behaviour (direct)

- Opens a single virtual serial port and echoes every received byte sequence back unchanged.
- Designed to act as a fake MCU endpoint for local end-to-end testing: whatever the host sends is printed (hex) and echoed back, so a terminal on the opposite end behaves as if talking to a real device.

---

#### Usage notes

- **Requires two virtual ports** created externally (e.g., socat, pty pairs, tty0tty).
- **Run on Linux only** (depends on pty semantics).
- Launch the emulator on one end and point your terminal/debug tool at the other end to simulate a physical USB/serial link.

---

## Firmware — `PWR_Control_F401RCT6` (Architecture & Runtime Reference)

This folder contains the STM32F401 firmware for the current hardware.  
**Below is a concise, implementation-accurate reference for architecture, runtime behavior, interfaces, byte-level layouts, timers/ISRs, and critical invariants.**

---

### High-Level Overview

- Firmware initializes all peripherals, starts a TIM2-based system tick, configures PWM for the injection pump, and sets up two input-capture channels for flow meters.
- The main loop is cooperative and non-blocking, repeatedly calling:
  - `Comms_Process()` (frame parsing)
  - `StateMachine_ProcessTick()` (state transitions)
  - `Comms_Tick()` (heartbeat/telemetry scheduling)
- Real-time events (flow pulses, tick increments) are handled in timer ISRs.

---

### Firmware Modules & Responsibilities

| Module                | Responsibilities                                                                                   |
|-----------------------|---------------------------------------------------------------------------------------------------|
| `comms_protocol.c`    | Transport framing/parser. Handles frame format, CRC (XOR), sequence, and invokes app callbacks.   |
| `comms_app.c`         | Application-layer messages: TLV config, handshake, telemetry, heartbeat, ACK/NACK, immediate cmds.|
| `state_machine.c/h`   | Global runtime state, startup sequence, all state transitions and error handling.                  |
| `injection_and_flow.*`| Pump actuator control, PI controller struct, flowmeter helpers and totals.                        |
| HAL wrappers          | `uart_hal`, `tim.h`, board macros: centralize low-level HAL calls.                                |
| `config.c/h`          | Runtime defaults, TLV tag table, build-time flags, derived tick thresholds.                       |

---

### Initialization & Main Loop (Exact Sequence)

1. `HAL_Init()` → `SystemClock_Config()` → MX_* peripheral inits (GPIO, TIM2, TIM3, TIM5, USART2, USART1, TIM1, ...)
2. Start peripherals:
   - `HAL_TIM_Base_Start_IT(&htim2)` — system tick
   - `HAL_TIM_PWM_Start(&htim5, TIM_CHANNEL_2)` — injection pump PWM
   - `HAL_TIM_IC_Start_IT(&htim1, TIM_CHANNEL_1)` — flowmeter 1
   - `HAL_TIM_IC_Start_IT(&htim3, TIM_CHANNEL_1)` — flowmeter 2
3. Call `InjectionAndFlow_Init()`, `flags_init()`, `StateMachine_Init()`, `Comms_Init(USART1)`, `UartHAL_FlushRx(USART1)`
4. Main loop (non-blocking, no delays):
   - `Comms_Process()`
   - `StateMachine_ProcessTick()`
   - `Comms_Tick()`
   - (Timing is coordinated by ISRs and flags)

---

### Timers & ISRs — Authoritative Mapping

| Timer/Channel         | Purpose / ISR Behavior                                                                                 |
|----------------------|--------------------------------------------------------------------------------------------------------|
| TIM2                 | System tick. `HAL_TIM_PeriodElapsedCallback()` increments `SYSTEM_TICK`, drives tick-based counters.   |
| TIM5 CH2             | PWM output for injection pump.                                                                         |
| TIM1 CH1             | Input-capture for flowmeter #1. ISR calls `FlowMeter_PulseCallback()` directly.                        |
| TIM3 CH1             | Input-capture for flowmeter #2. ISR calls `FlowMeter2_PulseCallback()` directly.                       |

- **ISR rules:**  
  - Input-capture ISRs call flow pulse handlers directly (minimal, timestamp only).
  - `HAL_TIM_PeriodElapsedCallback()` (TIM2) updates all tick-based flags/counters.

---

### Communication: Frame Format, CRC, Sequence

- **Frame format:**  
  ```
  0xA5 | msgType:1 | seq:1 | len:1 | payload:len | xor_crc:1
  ```
- **CRC:**  
  - Single-byte XOR: `msgType ^ seq ^ payload_bytes`
  - CRC mismatch: frame dropped silently (no auto-NACK; add if needed)
- **Sequence:**  
  - Single-byte, legacy parity must be preserved for host compatibility
- **Parser:**  
  - On valid frame, calls `Comms_OnPacket(type, seq, payload, len)`

---

### Handshake & ACK/NACK

- **Handshake (`MSG_HANDSHAKE`):**  
  - Payload: `[heartbeat_period_ms:2][telemetry_period_ms:2][send_ack_and_nack_packets:1]` (≥5 bytes)
  - On valid handshake in `SYS_PAIRING`:
    - Sets heartbeat/telemetry periods, ACK/NACK flag
    - Sends `MSG_HANDSHAKE_ACK` with `[SYSTEM_TICK:u32][state:u8][0:u8]`
    - Calls handshake callback, transitions to `SYS_RUNNING_PI`
  - If handshake outside pairing or malformed: sends NACK (if enabled)
- **ACK/NACK:**  
  - Controlled by handshake flag
  - Payload: `[SYSTEM_TICK:u32][state:u8]` (5 bytes)
  - Must honor flag for host compatibility

---

### TLV Config (Application-Level)

- **TLV format:** `[tag:1][length:1][value:length]...` (parsing stops on malformed length)
- **Endianness:**  
  - `uint16_t`, `uint32_t`, `float` are little-endian (host: `struct.pack('<f', value)`)
- **Recognized tags:**  
  - `CONFIG_TAG_TELEMETRY_PERIOD_MS` — 2 bytes — `uint16_t`
  - `CONFIG_TAG_HEARTBEAT_PERIOD_MS` — 2 bytes — `uint16_t`
  - `CONFIG_TAG_PI_KP` / `CONFIG_TAG_PI_KI` — 4 bytes each — `float`
  - `CONFIG_TAG_ENABLE_PI_CONTROL` — 1 byte — `uint8_t`
  - `CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG` — 1 byte — `uint8_t`
  - `CONFIG_TAG_SERIAL_SEND_MS` — 2 bytes — `uint16_t`
  - `CONFIG_TAG_PWM_DEBUG` — 1 byte — `uint8_t`
  - `CONFIG_TAG_ENABLE_ECHO_DEBUG` — 1 byte — `uint8_t`
  - `CONFIG_TAG_FLOW_WINDOW_MS` — 2 bytes — `uint16_t`
  - `CONFIG_TAG_FLOW_PULSES_PER_LITRE` — 4 bytes — `uint32_t`
  - `CONFIG_TAG_ENABLE_LOOKUP_TABLE` — 1 byte — `uint8_t`
  - `CONFIG_TAG_PUMP_SAMPLE_TIME_MS` — 2 bytes — `uint16_t`
  - `CONFIG_TAG_FLOWMETER_PULSE_SEND_DEBUG` — 1 byte — `uint8_t`
- **Apply:**  
  - `Comms_ApplyConfigTLV(payload, len)` returns `true` on success (caller may ACK/NACK)

---

### Telemetry & Heartbeat Payloads

- **Heartbeat (`MSG_HEARTBEAT`):**  
  - 8 bytes: `[SYSTEM_TICK:u32][state:u8][startup_step_or_0:u8][heartbeat_counter:u16]`
  - Sent periodically, even before handshake (for host discovery)
- **Telemetry (`MSG_TELEMETRY_PUSH`):**  
  - 21 bytes: `[ts:u32][state:u8][flow1:u32][total1:u32][flow2:u32][total2:u32]`
  - Sent only after startup/pairing (in `SYS_RUNNING_PI`, `SYS_STANDALONE_OPERATION`, or `SYS_DEBUG`)
- **Scheduling:**  
  - `Comms_Tick()` sends heartbeat/telemetry on their respective periods (from `SYSTEM_TICK`)

---

### State Machine — Authoritative Rules

| State                      | Description / Transitions                                                                                   |
|----------------------------|------------------------------------------------------------------------------------------------------------|
| `SYS_STARTUP_SEQUENCE`     | Homing/zero steps (timeouts: 5s). If `SKIP_STARTUP_SEQUENCE` defined, skips to next state.                 |
| `SYS_PAIRING`              | Accepts handshake. On valid handshake: → `SYS_RUNNING_PI`. Timeout: → `SYS_STANDALONE_OPERATION`.          |
| `SYS_RUNNING_PI`           | Normal PI-regulated flow. Accepts config, desired flow, flow updates. Debug flags → `SYS_DEBUG`.           |
| `SYS_DEBUG`                | Only entered from `SYS_RUNNING_PI`. Manual PWM/debug behaviors. Exit via `MSG_EXIT_SYS_DEBUG`.              |
| `SYS_STANDALONE_OPERATION` | Autonomous. Debug only reachable via running.                                                              |
| `SYS_ERROR_SHUTDOWN`       | Fatal error. Disables outputs.                                                                             |

- **Debug entry:** Only from `SYS_RUNNING_PI`.  
- **Debug exit:** Host sends `MSG_EXIT_SYS_DEBUG`; MCU clears debug flags, disables manual PWM, sets PWM compare to zero, returns to `SYS_RUNNING_PI`.

---

### Pump Control & PI

- `Pump_Control` struct: contains `kp`, `ki`, runtime counters/flags.
- PI control enabled/disabled via TLV and runtime flags.
- `MSG_SET_PUMP_PWM` forces manual PWM (`manual_pwm_enabled`), writes timer compare register immediately (`__HAL_TIM_SET_COMPARE`).
- Derived tick thresholds (pump sample, flow window) calculated from ms via `MS_TO_TICKS()` at startup/config change.

---

### ISR vs Non-ISR Boundaries & Threading Model

- **Flow pulse handlers** (`FlowMeter_PulseCallback()`, etc.):  
  - Called directly from input-capture ISRs for timestamp accuracy.  
  - Should be minimal; queue work for main loop.
- **Comms_Process():**  
  - Runs in main loop (non-ISR), parses UART RX buffer (must be re-entrant safe).
- **Comms_DrainFlowPulseQueue():**  
  - Called from main loop by `Comms_Tick()` if debug enabled.
- **Rule:**  
  - Avoid heavy processing in ISRs; only timestamp/enqueue.

---

### Public API Surface

- **State machine:**  
  - `StateMachine_Init()`, `StateMachine_ProcessTick()`, `StateMachine_GetState()`, `StateMachine_OnHandshakeAccepted()`, `StateMachine_EnterDebug()`, `StateMachine_ExitDebug()`, `StateMachine_TriggerFatal()`
- **Comms:**  
  - `Comms_Init(UART_HandleTypeDef *huart)`, `Comms_Process()`, `Comms_Tick()`, `Comms_SendTelemetry()`, `Comms_SendHeartbeat()`, `Comms_SendAck(seq)`, `Comms_SendNack(seq)`
- **Callbacks:**  
  - `Comms_RegisterHandshakeCb(cb)`, `Comms_RegisterConfigCb(cb)`
- **Config:**  
  - `Comms_ApplyConfigTLV(payload, len)`

---

### Implementation Gotchas & Invariants

- **Tag parity:** TLV tag values in `config.h` must match host `mcu_comm.protocol` exactly.
- **Float endianness:** PI gains are little-endian IEEE-754 (`<f` on host).
- **Immediate PWM writes:** `MSG_SET_PUMP_PWM` writes hardware compare register immediately.
- **Echo debug port:** `EchoDebug_Process()` expects `USART1`.
- **Tick base:** `SYSTEM_TICK` is incremented in TIM2 ISR (ignore TIM6 comments).
- **No auto-NACK on CRC:** CRC errors drop frames silently unless explicit NACK is added.
- **Debug entry:** Only from `SYS_RUNNING_PI`.
- **Startup skip:** `SKIP_STARTUP_SEQUENCE` disables homing/zero (for bring-up, not for production).

---

### Extension & Maintenance Notes

- **Add TLV tags:**  
  - Append to `ConfigTag_t` and TLV table in `config.c`
  - Implement parsing in `Comms_ApplyConfigTLV()`
  - Update host protocol to match tag numbers
- **Add NACK-on-CRC:**  
  - Modify parser in `comms_protocol.c` to call app hook or return error for NACK
- **Add telemetry fields:**  
  - Update payload size/order in `Comms_SendTelemetry()`, update host decoder
- **Change PWM timer/channel:**  
  - Update both main PWM start and all `__HAL_TIM_SET_COMPARE` uses

---

### Common Constants & Types

- **Frame format, CRC, sequence:** See above.
- **Handshake:** Sets heartbeat/telemetry periods, ACK/NACK flag.
- **Telemetry interval:** Controlled by `telemetry_period_ms` (default in `config.c`).
- **Tick thresholds:** Derived from ms via `MS_TO_TICKS()`.

---

## Firmware — `PWR_Control_F401RCT6` (Module Reference)

This section extends the firmware architecture reference with byte-level, runtime-accurate details for the following modules:

- `injection_and_flow.*`
- `flow_lut.*`
- `mks42d.*` (custom stepper protocol)
- `motor_control` (high-level stepper wrapper)
- `lasers.*`

All details below reflect the exact behavior in the supplied implementation.

---

### 1. Injection & Flow Module (`injection_and_flow.*`)

#### 1.1 Global State (Authoritative)

**Primary Flowmeter**  
`volatile FlowState_t Flow_State;`

- `pulse_count_window` — Pulses in current window (for instantaneous flow)
- `pulse_count_total` — Lifetime pulse count
- `short_term_pulses[]` — Circular buffer of pulse timestamps (ms ticks)
- `short_term_index`, `short_term_count` — Buffer management
- `last_flow_mlmin` — Last computed instantaneous flow (integer mL/min)
- `total_ml` — Cumulative volume (integer mL)
- *(Optional, if `RECORD_PULSE_TIMESTAMPS` defined):*
  - `pulse_deltas[]`, `pulse_delta_index`, `delta_accumulator`

**Secondary Flowmeter**  
`volatile FlowState_t Flow_State2;`

- Same structure as primary, but:
  - Uses `flow2_window_ms`
  - Uses `flow2_pulses_per_litre`
  - **Does NOT** enqueue debug pulse packets

**Pump Control**  
`volatile PumpControl_t Pump_Control;`

- `duty_pump` — Current PWM duty (applied directly)
- `kp`, `ki` — PI controller gains
- `pi_integral` — PI integral accumulator
- `pump_flag`, `pump_counter` — Scheduler flags/counters
- `flow_schedule[]`, `schedule_head`, `schedule_tail` — Circular buffer for scheduled flow setpoints
- `instantaneous_desired_flow` — Current flow setpoint (mL/min)
- `solenoid_flag`, `solenoid_counter` — Solenoid control

---

#### 1.2 Initialization — `InjectionAndFlow_Init()`

- **IRQs disabled** during state reset
- Clears all flow counters and buffers
- Sets PWM duty to 0:  
  `__HAL_TIM_SET_COMPARE(&htim5, TIM_CHANNEL_2, 0);`
- Solenoid forced **CLOSED**:  
  `HAL_GPIO_WritePin(SOLENOID_GPIO_PORT, SOLENOID_GPIO_PIN, GPIO_PIN_RESET);`
- Initializes PI gains:  
  `kp = DEFAULT_PI_Kp`, `ki = DEFAULT_PI_Ki`, `pi_integral = 0`
- Clears schedule buffer
- Initializes secondary flowmeter parameters:  
  `flow2_window_ms = DEFAULT_FLOW2_WINDOW_MS;`  
  `flow2_pulses_per_litre = DEFAULT_FLOW2_PULSES_PER_LITRE;`

---

#### 1.3 Flow Pulse Handling (ISR Context)

**Primary — `FlowMeter_PulseCallback()`**

- Called from input-capture ISR
- Actions:
  - `now = HAL_GetTick()`
  - Stores timestamp in circular buffer
  - Increments `pulse_count_window` and `pulse_count_total`
  - If `flowmeter_pulse_send_debug_enabled` **AND** `SYS_DEBUG`:
    - Calls `Comms_EnqueueFlowmeterPulse(now, 0, pulse_count_total);`
  - If timestamp recording enabled:
    - Stores delta ticks, handles overflow marker

> **Note:** ISR must remain lightweight — only timestamps and increments.

---

#### 1.4 Instantaneous Flow Calculation (Primary)

**Function:** `FlowMeter_UpdateInstantaneous()`

- **Concurrency Model:**  
  - Implements retry-based atomic snapshot:
    - Snapshots `short_term_count` and `short_term_index`
    - Copies circular buffer into local array
    - Re-checks values; retries if changed (avoids race conditions)
- **Wrap-Safe Windowing:**  
  - Age: `uint32_t age = now - t;` (unsigned, wrap-safe)
  - Pulse included if: `age <= flow_window_ms`
- **Flow Calculation Formula:**  
  - If `pulses_in_window >= 2` and `delta_ms > 0` and `flow_pulses_per_litre > 0`:
    - `frequency = (pulses - 1) / delta_seconds`
    - `flow_mlmin = frequency * (1000 * 60) / pulses_per_litre`
    - Stored as:  
      `Flow_State.last_flow_mlmin = (uint32_t)(flow_mlmin + 0.5f);`
- **Defensive Checks:**  
  - Window and PPL must not be 0
  - NaN/Inf/negative/zero-delta rejected

---

#### 1.5 Total Volume Calculation

- `total_ml = (pulse_count_total * 1000) / pulses_per_litre`
- **Integer math only**

---

### 2. PI Pump Controller

#### 2.1 Execution Model

- `update_pump_state()` executes when `Pump_Control.pump_flag == 1`
- Flag is set by timer-driven scheduler

#### 2.2 Schedule Consumption

- Implements circular buffer with `FLOW_SCHEDULE_MIN_LOOKAHEAD`
- Flow value only consumed if `distance > MIN_LOOKAHEAD`
- Else, last value held

#### 2.3 PI Equation

- `error = desired - measured`
- `integral += error * dt`
- `duty = kp*error + ki*integral`
- **Clamped:**  
  `PUMP_DUTY_MIN <= duty <= PUMP_DUTY_MAX`
- **PWM applied immediately:**  
  `__HAL_TIM_SET_COMPARE(&htim5, TIM_CHANNEL_2, duty)`

#### 2.4 Lookup Table Override (Experimental)

- If `lookup_table_enabled == 1` **AND** `abs(flow_diff) >= FLOW_DIFF_LUT_THRESHOLD_MLMIN`:
  - `Pump_Control.duty_pump = FlowLUT_GetDutyForFlow(desired_flow)`
  - **PI skipped that tick**

---

### 3. Flow Lookup Table Module (`flow_lut.*`)

> ⚠ **Status:** Not fully tested / not production validated

#### 3.1 LUT Structure

- `FlowLUT.points[]` — Array of points
- `FlowLUT.n_points` — Number of points
- Each point:  
  ```c
  struct {
      uint32_t flow_mlmin;
      uint16_t duty;
  }
  ```

#### 3.2 Interpolation

- **Linear interpolation:**  
  `duty = y0 + ((y1 - y0) * (flow - x0)) / (x1 - x0)`
- **Clamped** to endpoints
- **Fallback:**  
  Returns `PUMP_DUTY_MAX` if out of range

#### 3.3 Auto-Tune Routine (Blocking)

- `FlowLUT_AutoTune()`
- For duty from `PUMP_DUTY_MIN` → `PUMP_DUTY_MAX` (step `CAL_STEP_DUTY`):
  - Apply duty:  
    `__HAL_TIM_SET_COMPARE(&htim2, TIM_CHANNEL_1, duty)`  
    *(NOTE: This is a different timer/channel than normal pump output)*
  - `HAL_Delay(CAL_STABILIZE_MS)`
  - Measure flow, store point
- **Issues:**
  - Uses `HAL_Delay()` (blocking)
  - LUT stored only in RAM (no persistence)
  - No filtering/smoothing
  - **Should not be used in production without redesign**

---

### 4. Custom Stepper Motor Protocol (`mks42d.*`)

- Stepper driver communicates via `USART2`
- Bus accessor:  
  `static inline USART_TypeDef* MKS_BUS(void) { return USART2; }`

#### 4.1 Frame Format

- **TX Frame:**  
  `0xFA | slave | cmd | data... | checksum`
  - Checksum: `sum(bytes) & 0xFF`
- **RX Frame:**  
  `0xFB | slave | cmd | data... | checksum`
- Parser: State-machine based, tolerant to misalignment

#### 4.2 Supported Commands

| Command         | TX Example                | RX Example                        | Notes                                 |
|-----------------|--------------------------|------------------------------------|---------------------------------------|
| Go Home         | FA | ID | 0x91 | sum     | FB | ID | 0x91 | status | sum        | status: 2=success, 0=fail, 1=busy     |
| Set Zero        | FA | ID | 0x92 | sum     | FB | ID | 0x92 | status | sum        |                                       |
| Speed Mode      | FA | ID | 0xF6 | ...     | FB | ID | 0xF6 | status | sum        | Direction: high bit of byte 3         |
| Position Mode 1 | FA | ID | 0xFD | pulses  | FB | ID | 0xFD | status | sum        | Pulses: uint32 big-endian             |
| Position Mode 2 | FA | ID | 0xFE | abs pos | FB | ID | 0xFE | status | sum        | Abs pos: int32 big-endian, speed: u16 |
| Read Position   | FA | ID | 0x31 | sum     | FB | ID | 0x31 | pos[6] | sum        | 6-byte signed position (48-bit)       |

#### 4.3 Position Decode

- 48-bit signed:  
  - If `pos & (1 << 47)`, sign-extend to 64 bits
  - Cast to `int32_t stepper_pos`

---

### 5. High-Level Stepper Controller (`motor_control`)

- Global:  
  `int32_t stepper_pos;`  
  `bool stepper_rx_check_start;`

#### 5.1 Motor Test

- Toggles between:  
  `positionMode2Run(..., 3100)` and `positionMode2Run(..., 100)`
- Triggered by `motor_flag`

#### 5.2 Motor Read Loop

- Driven by `motor_read_flag` and `stepper_rx_check_flag`
- Logic:
  - If command pending → transmit
  - Else → request position
  - RX parsed until success
- **Non-blocking polling architecture**

---

### 6. Solenoid Control

- `Update_Solenoid_State()`
  - If `duty_pump == 0` → solenoid **OFF**
  - Else → solenoid **ON**
- GPIO write only when `solenoid_flag` set

---

### 7. Saw Wave Debug Mode

- `GenerateSawWaveDebug()`
  - Oscillates duty between `SAW_PWM_MIN` and `SAW_PWM_MAX`
  - Step: `SAW_PWM_STEP`
  - Direction flips at bounds
  - Direct PWM write (bypasses PI & LUT)
  - **Used only in `SYS_DEBUG`**

---

### 8. Laser Control

- Simple GPIO control:
  - If `hall_status` → `GPIOB PIN13 = 1`
  - Else → `GPIOB PIN13 = 0`
- Triggered by `lasers_flag`
- **No PWM, no modulation**

---

### 9. Architectural Observations & Critical Notes

1. **LUT System**
   - Implemented but not production validated
   - Auto-tune is blocking
   - Timer channel inconsistency (auto-tune vs normal operation)
   - No persistence

2. **PI Controller**
   - Float internal math, integer I/O
   - No anti-windup
   - No derivative term
   - Integral unbounded except by duty clamp

3. **Flow Calculation**
   - Wrap-safe, race-safe
   - Float conversion only in final stage

4. **Stepper Protocol**
   - Custom binary protocol
   - Big-endian multi-byte values
   - Poll-based RX parsing
   - No timeout watchdog

5. **Hardware Direct Writes**
   - Immediate effects via `__HAL_TIM_SET_COMPARE`, `HAL_GPIO_WritePin`
   - No abstraction safety layer

---

### 10. Extension Guidance

- **PI Controller:** Add anti-windup clamp to PI integral
- **LUT:** Move auto-tune to non-blocking state machine; validate duty channel consistency; add persistence
- **Stepper:** Add timeout detection to RX; improve error handling
- **Flow:** Add sanity bounds to `instantaneous_desired_flow`
- **General:** Maintain wrap/race safety and hardware parity

---

**End of firmware architecture section — concise, byte-level accurate, and preservation-oriented for host parity.**

---

## Authors & Project Info

### Project Description
DMT 6 is a Nuclear Thermal-Hydraulics Rig designed to replicate boric acid injection in pressurized water reactors (PWRs) at a laboratory scale. The system combines three major subsystems: the Reactor Pressure Vessel (RPV) and internals, the Primary Circuit Flow Loop and Pump Assembly, and the Tracer Fluid Injection and Measurement System.  

The rig enables experimental studies on flow patterns, tracer mixing, and injection strategies for emergency boron injection systems (EBIS). Key features include:  

- **Reactor Pressure Vessel Sub-assembly (Group A):** Layered acrylic and 3D-printed structures simulating the core barrel, lower and upper core plates, flow distributor, and fuel rod assemblies for visual and optical testing.  
- **Primary Circuit Flow Loop (Group B):** A clear, closed-loop PVC piping system with pumps, valves, and flow meters to replicate PWR hydraulic conditions, including turbulent flow and representative Reynolds numbers.  
- **Tracer Injection & Optical Measurement (Group C):** A controlled fluorescein dye injection system with high-speed imaging and laser-based optical diagnostics for studying fluid mixing, boundary layer effects, and tracer transport.  

DMT 6 provides a portable and modular experimental platform for nuclear thermal-hydraulic research in a controlled laboratory environment.

### Authors / Maintainers
- [Name Placeholder] — [Role / Responsibility Placeholder]
- [Name Placeholder] — [Role / Responsibility Placeholder]
- [Name Placeholder] — [Role / Responsibility Placeholder]

### Contact / Support
- Email: [ac4423@ic.ac.uk](mailto:ac4423@ic.ac.uk)
- GitHub Issues: [https://github.com/ac4423/DMT-Control-System/issues](https://github.com/ac4423/DMT-Control-System/issues)

### Version
- Version: 1.0.0
- Release date: 2026-03-03

### License
- [LICENSE PLACEHOLDER]

### Project Metadata
- **Firmware (current):** `PWR_Control_F401RCT6`
- **Supported OS:** Linux, Windows

### Acknowledgements
- [Acknowledgements Placeholder]

---

**End of README**

---