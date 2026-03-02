# -*- coding: utf-8 -*-
"""
Created on Sun Mar  1 08:22:34 2026

@author: zykov
"""

import serial
import time
import threading
from mcu_comm.driver import MCUComm


class FlowTester:
    def __init__(self, port, baud):
        self.mcu = MCUComm(port, baud)
        self.running_test = False
        self._test_thread = None

    def start(self):
        self.mcu.open()
        print(f"Connected to {self.mcu.port}. Type 'Test 1', 'Test 2', or 'Test 3'.")
 
        # Let the MCU initialize after opening the port
        time.sleep(1.0)

    def stop(self):
        self.running_test = False
        if self._test_thread:
            self._test_thread.join()
        self.mcu.close()

    # --- Test Logic ---

    # --- PWM Test Logic ---

    def run_test_1(self):
        """Test 1: Increase PWM from 0% to 90%."""
        print("Starting Test 1: Ramping PWM Up...")
        current_pwm = 0
        target_pwm = 90  # 90% Duty Cycle
        step = 5         # Increase by 5% every second
        
        while self.running_test and current_pwm <= target_pwm:
            # Change the method to set_pump_pwm
            self.mcu.send_set_pump_pwm(current_pwm)
            print(f"Current PWM: {current_pwm}%")
            current_pwm += step
            time.sleep(1.0)
        
        # Safety: Don't leave it spinning at 90% forever
        self.mcu.send_set_pump_pwm(0)
        print("Test 1 Complete. Motor Stopped.")

    def run_test_2(self):
        """Test 2: Stable PWM (50%) for 20 seconds."""
        print("Starting Test 2: Stable PWM 99%...")
        self.mcu.send_set_pump_pwm(99)
        
        duration = 20
        start_time = time.time()
        while self.running_test and (time.time() - start_time) < duration:
            time.sleep(1.0)
            
        self.mcu.send_set_pump_pwm(0)
        print("Test 2 Complete.")

    def run_test_3(self):
        """Test 3: Emergency Stop / Step Down."""
        print("Starting Test 3: Stepping Down...")
        for p in [75, 50, 25, 0]:
            if not self.running_test: break
            self.mcu.send_set_pump_pwm(p)
            print(f"PWM: {p}%")
            time.sleep(2.0)
        print("Test 3 Complete.")

    def handle_input(self, user_cmd):
        # Stop previous test, but do NOT block main thread
        if self._test_thread and self._test_thread.is_alive():
            self.running_test = False
            # Let previous thread clean up itself
            self._test_thread.join(timeout=0.5)  # Non-blocking join

        # Reset running flag
        self.running_test = True

        # Select the test
        if user_cmd == "Test 1":
            self._test_thread = threading.Thread(target=self.run_test_1, daemon=True)
        elif user_cmd == "Test 2":
            self._test_thread = threading.Thread(target=self.run_test_2, daemon=True)
        elif user_cmd == "Test 3":
            self._test_thread = threading.Thread(target=self.run_test_3, daemon=True)
        else:
            print("Unknown command.")
            self.running_test = False
            return

        # Start the test thread
        self._test_thread.start()

# --- Main Execution ---
if __name__ == "__main__":
    # Change 'COM3' or '/dev/ttyUSB0' to your actual port
    tester = FlowTester('COM3',256000) 
    tester.start()

    try:
        while True:
            cmd = input("Enter Command: ")
            tester.handle_input(cmd)
    except KeyboardInterrupt:
        tester.stop()