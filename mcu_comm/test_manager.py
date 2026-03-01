# -*- coding: utf-8 -*-
"""
Created on Sun Mar  1 08:22:34 2026

@author: zykov
"""

import time
import threading
from mcu_comm.driver import MCUComm

class FlowTester:
    def __init__(self, port):
        self.mcu = MCUComm(port)
        self.running_test = False
        self._test_thread = None

    def start(self):
        self.mcu.open()
        print(f"Connected to {self.mcu.port}. Type 'Test 1', 'Test 2', or 'Test 3'.")

    def stop(self):
        self.running_test = False
        if self._test_thread:
            self._test_thread.join()
        self.mcu.close()

    # --- Test Logic ---

    def run_test_1(self):
        """Test 1: Increase flow at a pre-programmed speed."""
        print("Starting Test 1: Ramping Up...")
        current_flow = 0
        target_flow = 5000  # 5000 mL/min
        step = 100          # Increase by 100 mL/min every second
        
        while self.running_test and current_flow <= target_flow:
            self.mcu.send_desired_flow(current_flow)
            print(f"Flow: {current_flow} mL/min")
            current_flow += step
            time.sleep(1.0)
        print("Test 1 Complete.")

    def run_test_2(self):
        """Test 2: Stable flow for a certain period."""
        print("Starting Test 2: Stable Flow (30 seconds)...")
        stable_flow = 2500
        duration = 30
        
        self.mcu.send_desired_flow_immediate(stable_flow)
        start_time = time.time()
        while self.running_test and (time.time() - start_time) < duration:
            # We re-send just to ensure MCU stays updated
            self.mcu.send_desired_flow(stable_flow)
            time.sleep(1.0)
        print("Test 2 Complete.")

    def run_test_3(self):
        """Test 3: Decrease flow at a pre-programmed speed."""
        print("Starting Test 3: Ramping Down...")
        current_flow = 5000
        min_flow = 0
        step = 200
        
        while self.running_test and current_flow >= min_flow:
            self.mcu.send_desired_flow(current_flow)
            print(f"Flow: {current_flow} mL/min")
            current_flow -= step
            time.sleep(1.0)
        print("Test 3 Complete.")

    def handle_input(self, user_cmd):
        # Stop any currently running test before starting a new one
        self.running_test = False
        if self._test_thread:
            self._test_thread.join()

        self.running_test = True
        
        if user_cmd == "Test 1":
            self._test_thread = threading.Thread(target=self.run_test_1)
        elif user_cmd == "Test 2":
            self._test_thread = threading.Thread(target=self.run_test_2)
        elif user_cmd == "Test 3":
            self._test_thread = threading.Thread(target=self.run_test_3)
        else:
            print("Unknown command.")
            self.running_test = False
            return

        self._test_thread.start()

# --- Main Execution ---
if __name__ == "__main__":
    # Change 'COM3' or '/dev/ttyUSB0' to your actual port
    tester = FlowTester('COM3') 
    tester.start()

    try:
        while True:
            cmd = input("Enter Command: ")
            tester.handle_input(cmd)
    except KeyboardInterrupt:
        tester.stop()