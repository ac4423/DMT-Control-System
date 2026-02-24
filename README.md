# README — MCU Terminal & STM32 Firmware (developer)

> Developer-facing README for the `mcu_terminal.py` developer serial terminal and the corresponding STM32 firmware architecture.

---

## Contents

1. **Using the terminal app (mcu_terminal.py)**

   * 1.1 Quick start (Linux / Windows)
   * 1.2 UI overview (top packet window, bottom CLI)
   * 1.3 Typical usage / examples
   * 1.4 CLI command reference (common commands + examples)
   * 1.5 TLV table (tags, numbers, types, example CLI usage)

2. **STM32 firmware architecture (brief overview)**

   * 2.1 Key modules & responsibilities
   * 2.2 Runtime state machine & transitions (handshake / debug paths)
   * 2.3 Telemetry / heartbeat / ACK semantics
   * 2.4 Important implementation notes & gotchas

---

## 1. Using the terminal app (mcu_terminal.py)

`mcu_terminal.py` is the developer serial terminal used to drive and test the STM32 firmware. The production GUI will re-use the same `mcu_comm` driver and protocol modules used by this terminal.

### 1.1 Quick start

#### Linux (example)

```bash
# create venv (recommended)
python3 -m venv venv_linux
source venv_linux/bin/activate

# install dependencies
pip install -r requirements_linux.txt

# run against a device
python3 mcu_terminal.py --port /dev/ttyUSB0
# with overrides:
python3 mcu_terminal.py --port /dev/ttyUSB0 --hb 200 --tel 500 --baud 256000 --send-ack 1
```

#### Windows (PowerShell example)

```powershell
# check ports
python -m serial.tools.list_ports

# create, activate venv and install
python -m venv venv_windows
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv_windows\Scripts\Activate.ps1
pip install -r requirements_windows.txt

# run
python .\mcu_terminal.py --port COM3
```

**If you see no packets in the UI:**

* Verify correct port and matching baud rate on both sides.
* Try `--baud 256000` (the terminal defaults to 256000 in examples).
* Ensure the MCU is powered and running the firmware build.

### 1.2 UI overview

Visually the terminal app has two regions:

* **Top window** — Incoming packets / decoded frames (scrolling). This is the live packet view.
* **Bottom window** — CLI input & history. Type commands here (type `help` for a summary).

**Features:**

* Pause / resume incoming packet display (use `pause` / `resume` commands).
* Configure number of lines for packet window and CLI history via runtime `set` command or start arguments `--packet-lines` and `--cmd-lines`.
* Top area shows parsed frames delivered by `mcu_comm.PacketParser`. Bottom area is interactive CLI with history.

### 1.3 Typical usage / examples

Send handshake, default values come from CLI flags or previous `set`:

```text
# send handshake with defaults:
h

# explicit
h --hb 200 --tel 500 --send-ack 1 --extra 0A0B
```

Send a config TLV:

```text
# set telemetry interval to 200 ms
config telemetry 200

# enable PWM debug mode (u8 flag)
config pwm_debug 1

# set PI kp float
config kp 0.002

# send a raw TLV payload directly (hand-crafted)
config raw 0A0200C8  # (example: tag 0x0A, length 2, value 0x00C8)
```

Immediate manual PWM (forces MCU into debug):

```text
pwm 50
```

Exit debug on MCU:

```text
exit-debug
```

Send scheduled desired flow or immediate:

```text
flow 1500
flow-immediate 2000
```

Send raw frame bytes:

```text
# hex string (no spaces or with spaces)
send A5100005...
```

### 1.4 CLI command reference (short)

* `h`, `handshake` `[--hb N] [--tel N] [--send-ack 0|1] [--extra HEX]` — send handshake
* `config <tag> <value>` — send single TLV config field (see TLV table below)
* `config raw <hexpayload>` — send raw TLV payload as-is
* `pwm <0..99>` — set pump manual PWM (enters `SYS_DEBUG` on MCU)
* `exit-debug` — request MCU to exit `SYS_DEBUG` → `SYS_RUNNING_PI`
* `flow <mL/min>` — scheduled desired flow
* `flow-immediate <mL/min>` — immediate desired flow
* `1, emu1 / 2, emu2` — dev emulated stepper ACK packets
* `pause` / `resume` — pause/resume incoming packet display
* `set <key> <value>` — change runtime defaults or UI sizes

  * keys: `hb`, `tel`, `send-ack`, `extra`, `baud`, `packet_lines`, `cmd_lines`
* `status` — show current defaults and UI sizes
* `send <hex>` — send raw bytes
* `help` — show CLI help

### 1.5 TLV table (config tags)

> Use `config <name> <value>` or the `send_config_*` helpers provided by `mcu_comm.driver`. Types are the wire formats accepted by the MCU (little-endian where multi-byte).

| Friendly name (CLI)                 | Tag (hex) | Wire type          | Length | Description                                 | Example CLI                           |
| ----------------------------------- | --------: | ------------------ | -----: | ------------------------------------------- | ------------------------------------- |
| telemetry                           |    `0x01` | `u16 (LE)`         |      2 | Telemetry period in ms                      | `config telemetry 1000`               |
| hb / heartbeat                      |    `0x02` | `u16 (LE)`         |      2 | Heartbeat period in ms                      | `config heartbeat 500`                |
| kp                                  |    `0x03` | `f32 (IEEE754 LE)` |      4 | PI controller Kp (float)                    | `config kp 0.002`                     |
| ki                                  |    `0x04` | `f32 (IEEE754 LE)` |      4 | PI controller Ki (float)                    | `config ki 0.001`                     |
| enable_pi                           |    `0x05` | `u8`               |      1 | Enable/disable PI control (0/1)             | `config enable_pi 1`                  |
| enable_usb_serial_debug / usb_debug |    `0x06` | `u8`               |      1 | Enable USB serial debug (0/1)               | `config usb_debug 1`                  |
| serial_send_ms                      |    `0x07` | `u16 (LE)`         |      2 | Rate at which serial debug sends occur (ms) | `config serial_send_ms 200`           |
| pwm_debug                           |    `0x08` | `u8`               |      1 | Enable PWM saw-wave debug (0/1)             | `config pwm_debug 1`                  |
| enable_echo_debug                   |    `0x09` | `u8`               |      1 | Enable echo debug (mirrors UART)            | `config enable_echo_debug 1`          |
| flow_window_ms                      |    `0x0A` | `u16 (LE)`         |      2 | Flow meter averaging/window (ms)            | `config flow_window_ms 1000`          |
| flow_pulses_per_litre               |    `0x0B` | `u32 (LE)`         |      4 | Pulses per litre for flowmeter calibration  | `config flow_pulses_per_litre 450000` |
| enable_lookup_table                 |    `0x0C` | `u8`               |      1 | Enable lookup table flow→PWM mode (0/1)     | `config enable_lookup_table 1`        |
| pump_sample_time_ms                 |    `0x0D` | `u16 (LE)`         |      2 | Pump sample interval (ms)                   | `config pump_sample_time_ms 100`      |

**Notes:**

* Float fields (`kp`, `ki`) are packed as little-endian IEEE-754 (the terminal uses `struct.pack('<f', value)`). Ensure the host uses the same encoding.
* You can send multiple TLV fields in a single `MSG_CONFIG` by using `send_config([(tag, bytes), ...])` from the driver or `config raw <hexpayload>` CLI.
* `config raw` allows you to craft arbitrary TLV bytes for testing.

---

## 2. STM32 firmware architecture (overview)

This section describes the key firmware components and important runtime behaviors based on the sources in the repo.

### 2.1 Key modules (firmware side)

* **`comms_protocol.c`** — transport-layer framing and parsing (header `0xA5`, type, seq, len, payload, XOR CRC). Pure transport; does not depend on state machine or flow logic. On valid frames it calls a registered application callback.

* **`comms_app.c`** — application-layer comms: message handlers for handshake, config TLVs, telemetry, heartbeat, desired flow commands, debug control (`MSG_SET_PUMP_PWM`, `MSG_EXIT_SYS_DEBUG`), and ACK/NACK behavior. Uses `comms_protocol` to send frames.

* **`state_machine.c` / `state_machine.h`** — top-level runtime states and the tick-based state machine:

  * States: `SYS_STARTUP_SEQUENCE`, `SYS_PAIRING`, `SYS_RUNNING_PI`, `SYS_DEBUG`, `SYS_STANDALONE_OPERATION`, `SYS_ERROR_SHUTDOWN`.
  * Entry/exit helpers and `ProcessTick` implement the logic for transitions and debug handling.

* **`injection_and_flow.*`** — pump/flow control primitives, flow meter helpers and PI controller struct `Pump_Control`.

* **`config.h`** — TLV tag constants (must match host-side protocol), default timing values, and compile-time options (e.g. `SKIP_STARTUP_SEQUENCE`).

* **HAL wrappers** — `uart_hal`, `tim.h`, and HAL macros are used for UART and PWM timer operations.

### 2.2 State machine & transitions (handshake/debug flow)

**Startup**

* Normal: `SYS_STARTUP_SEQUENCE` runs `RunStartupSequence()` (hardware homing, set-zero steps). When complete:

  * If `self_op_enabled == 1` → `SYS_STANDALONE_OPERATION`.
  * Else → `StateMachine_EnterPairing()` → `SYS_PAIRING`.
* If `SKIP_STARTUP_SEQUENCE` is defined, startup is bypassed (immediately goes to PAIRING or STANDALONE based on `self_op_enabled`).

**Pairing / Handshake**

* In `SYS_PAIRING`, MCU accepts `MSG_HANDSHAKE` frames. A valid handshake updates `heartbeat_period_ms`, `telemetry_period_ms`, `send_ack_and_nack_packets`, sends `MSG_HANDSHAKE_ACK`, and calls `StateMachine_OnHandshakeAccepted()` which sets `SYS_RUNNING_PI`.

**Running (normal operation)**

* `SYS_RUNNING_PI` is the normal PI-controlled state. Flow updates and PI control run here.
* `MSG_CONFIG` is accepted in `SYS_PAIRING` and `SYS_RUNNING_PI`. TLV fields are parsed and applied.

**Enter `SYS_DEBUG`**

Two ways:

1. Host sends a config TLV that sets a debug flag (e.g. `CONFIG_TAG_PWM_DEBUG`, `CONFIG_TAG_ENABLE_USB_SERIAL_DEBUG`, or `CONFIG_TAG_ENABLE_ECHO_DEBUG`). At the next `StateMachine_ProcessTick()` the machine checks these flags and calls `StateMachine_EnterDebug()` (only allowed from `SYS_RUNNING_PI`).

2. Host sends `MSG_SET_PUMP_PWM` while in `SYS_RUNNING_PI`. MCU sets `manual_pwm_enabled` and `duty`, updates timer compare immediately and calls `StateMachine_EnterDebug()`.

**Exit `SYS_DEBUG`**

* Host must send `MSG_EXIT_SYS_DEBUG`. When in `SYS_DEBUG`, `StateMachine_ExitDebug()` clears debug flags, disables manual PWM, resets compare to zero and returns to `SYS_RUNNING_PI`.

**Standalone mode**

* `SYS_STANDALONE_OPERATION` runs autonomous behavior; some debug flags may be acted upon in that state (example: saw-wave generation is invoked in standalone case), but the implementation enforces that `SYS_DEBUG` is only entered from `SYS_RUNNING_PI` (see notes below).

### 2.3 Telemetry / heartbeat / ACK semantics

**Heartbeat**

* `Comms_Tick()` sends heartbeat periodically even before handshake (so a host can discover device state).
* Heartbeat payload contains `SYSTEM_TICK`, state, optional startup step, and a 16-bit counter.

**Telemetry**

* Sent only after device leaves startup/pairing (in `SYS_RUNNING_PI` or `SYS_STANDALONE_OPERATION`) at `telemetry_period_ms`.

**ACK/NACK**

* Application sends ACK/NACK depending on `send_ack_and_nack_packets` flag (set by handshake).
* On malformed packets or wrong-state messages, the application NACKs when send_ack is enabled.

**CRC**

* Protocol uses an XOR CRC over `msgType ^ seq ^ payload_bytes`. On CRC mismatch the protocol parser returns an invalid packet to host-side parser. The current firmware implementation does not automatically send a NACK for CRC errors — legacy behavior may have differed. If you need NACKs on CRC failures, implement it in protocol or at app layer.

### 2.4 Important implementation notes & gotchas

* **Tag / protocol parity:** The terminal's `mcu_comm/protocol.py` defines TLV tag numbers; these must match the MCU `config.h` exactly (they do in this repo: tags `0x01..0x0D`).

* **Float encoding:** `kp`/`ki` are 4-byte floats packed as little-endian IEEE-754 on the host. Host and MCU must use the same packing; mismatches cause incorrect PI gains. If you need cross-language safety, consider using fixed-point or explicit serialization.

* **Entering `SYS_DEBUG`:**

  * The state machine only allows entering `SYS_DEBUG` from `SYS_RUNNING_PI`. Enabling `pwm_debug` while in `SYS_STANDALONE_OPERATION` will not change state to `SYS_DEBUG` but may trigger saw-wave behavior in standalone code path — review intended semantics.

* **Immediate PWM:**

  * `MSG_SET_PUMP_PWM` changes `__HAL_TIM_SET_COMPARE` immediately and sets `manual_pwm_enabled`. That writes to the timer compare register used by pump hardware — ensure safety when testing.

* **CRC mismatch handling:**

  * The protocol parser on MCU drops frames on CRC mismatch; the host-side `PacketParser` returns `{'invalid': ...}` for debugging. If you want the MCU to reply with NACK on CRC errors, add explicit handling.

* **Echo debug port:**

  * `EchoDebug_Process()` uses a hardcoded `USART1` definition inside firmware. Make sure the chosen UART is consistent with your wiring and expectations.

* **Startup skip:**

  * If `SKIP_STARTUP_SEQUENCE` is defined at build time, the firmware will jump straight to pairing or standalone based on `self_op_enabled`. Ensure build defines match your test scenario.

### Quick tests to verify handshake → running → debug

1. Start MCU and terminal. Ensure correct `--port` and `--baud`.
2. From CLI, send handshake (example):

```text
h --hb 200 --tel 500 --send-ack 1
```

Expect: terminal prints `MSG_HANDSHAKE_ACK` and state becomes `SYS_RUNNING_PI` (firmware heartbeat/telemetry reflects that).

3. Enable PWM debug via TLV:

```text
config pwm_debug 1
```

Expect: next `StateMachine_ProcessTick()` transitions to `SYS_DEBUG`. Observe debug behavior (saw-wave) in PWM and echoed debug packets if enabled.

4. Or, set manual PWM:

```text
pwm 40
```

Expect: MCU immediately sets compare to duty 40 and enters `SYS_DEBUG`.

5. Exit debug:

```text
exit-debug
```

Expect: MCU acknowledges and returns to `SYS_RUNNING_PI` (PWM compare reset to zero by exit function).

---

## Where the terminal code maps to firmware

* `mcu_comm.driver` → wraps frame building and sends frames that `comms_protocol.c` on MCU expects.
* `mcu_comm.protocol` → tag/message constants and helper builders must be kept in sync with MCU `comms_app.c` / `comms_protocol.c`.
* `mcu_terminal.py` & `mcu_terminal_lib` → UI + CLI + decode only; reuses `mcu_comm` driver for all packet I/O.

---

## Extras / offers

If you want, I can:

* Produce a small `EXAMPLES.md` with a set of copy-paste CLI sessions that verify each transition (handshake, config TLV, pwm debug, exit-debug).
* Produce a tiny patch to document `SYS_DEBUG` in the firmware `state_machine.h` if that header is missing the enum entry.

---

## License / notes

Add your preferred license and contribution notes here.
Generated by GPT

---

*End of developer README.*

