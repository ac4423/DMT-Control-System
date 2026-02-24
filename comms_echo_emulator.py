# comms_echo_emulator.py
'''
You can set up and run two ports for echo like this on Linux:

sudo apt install socat
socat -d -d pty,raw,echo=0 pty,raw,echo=0

Then run this python script.

GPT:
"
Now:

Use /dev/pts/3 in your mcu_terminal.py

Use /dev/pts/4 in a small echo script

These two behave like a USB cable between two programs.
"
'''
import serial
import sys

port = sys.argv[1] if len(sys.argv) > 1 else "/dev/pts/7" # <<<<<<<<<<<<<<<< change or input on cmd line.

ser = serial.Serial(port, 115200, timeout=0.1)

print(f"Fake MCU listening on {port}")

while True:
    data = ser.read(1024)
    if data:
        print("RX:", data.hex())
        # echo back exactly what was received
        ser.write(data)
