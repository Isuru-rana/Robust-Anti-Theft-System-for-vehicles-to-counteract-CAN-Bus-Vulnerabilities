# test_engine_status.py
# Test script for engine status handling

import serial
import time
import json
from communication.engine_status_handler import handle_engine_status

def test_engine_status_handler():
    try:
        ser = serial.Serial('COM3', 115200, timeout=1)
        print("Connected to serial port for testing")
        
        print("\n--- Testing Engine ON Message ---")
        engine_on_message = {
            "n": "TestSender",
            "c": "s",
            "d": "Engine ON",
            "t": 123
        }
        
        result = handle_engine_status(engine_on_message, ser)
        print(f"Handler processed message: {result}")
        
        time.sleep(2)
        
        print("\n--- Testing Engine OFF Message ---")
        engine_off_message = {
            "n": "TestSender",
            "c": "s",
            "d": "Engine OFF",
            "t": 124
        }
        
        result = handle_engine_status(engine_off_message, ser)
        print(f"Handler processed message: {result}")
        
        time.sleep(2)
        
        print("\n--- Testing Non-Engine Message ---")
        other_message = {
            "n": "TestSender",
            "c": "s",
            "d": "Some other data",
            "t": 125
        }
        
        result = handle_engine_status(other_message, ser)
        print(f"Handler processed message: {result}")
        
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial connection closed")

if __name__ == "__main__":
    test_engine_status_handler()