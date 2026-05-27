#!/usr/bin/env python3
# Quick MCU serial test. Close the GUI first, then run:
#   C:\Python312\python.exe test_mcu_serial.py
#   C:\Python312\python.exe test_mcu_serial.py COM12
import sys
import time

from mcu_comm.protocol import build_frame, MSG_HANDSHAKE
from mcu_comm.driver import MCUComm
from Control_GUI.comms_manager import find_mcu_usb_port, BAUD_RATE


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else find_mcu_usb_port()
    if not port:
        print("No USB-UART (CH340) port found. Plug in the MCU USB cable.")
        return 1
    print(f"Testing {port} @ {BAUD_RATE} (GUI must be closed)...")
    try:
        with MCUComm(port, BAUD_RATE, timeout=0.2) as comm:
            hb = build_frame(MSG_HANDSHAKE, 1, bytes([0xF4, 0x01, 0xC8, 0x00, 0x01]))
            print(f"TX handshake: {hb.hex()}")
            comm.send_handshake(500, 200, True)
            got = []

            def on_any(pkt):
                if "invalid" not in pkt:
                    got.append(pkt)

            comm.register_callback(None, on_any)
            time.sleep(2.0)
            if got:
                print(f"OK: received {len(got)} packet(s) from MCU")
                for p in got[:5]:
                    print(f"  type=0x{p['type']:02X} len={p['len']}")
            else:
                print("FAIL: port opened but MCU sent nothing back.")
                print("  - Watch the USB-serial TX LED (blinks when PC sends)")
                print("  - Confirm firmware is flashed and board is powered")
                print("  - Try another USB cable / UART connector on the board")
                return 1
    except Exception as e:
        print(f"FAIL: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
