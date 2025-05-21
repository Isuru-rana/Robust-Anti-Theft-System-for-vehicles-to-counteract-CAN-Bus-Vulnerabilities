# receiver.py
# Module for receiving and processing data from serial port

import serial
import time
import json
import re
from utils.db_utils import get_latest_derived_key
from communication.message_processor import process_received_message, process_bus_message

def run_receiver(port, baud, identity, current_nonce, last_received_nonce):
    key = get_latest_derived_key(identity)
    if key is None:
        print("WARNING: No encryption key available. Run key exchange first!")
        return current_nonce, last_received_nonce
    else:
        print(f"Found encryption key: {key.hex()}")
    
    try:
        ser = serial.Serial(port, baud, timeout=1)
        print(f"Connected to {port} at {baud} baud")
        print("Listening for incoming data... Press Ctrl+C to exit")
        
        buffer = b""

        while True:
            try:
                if ser.in_waiting > 0:
                    new_data = ser.read(ser.in_waiting)
                    buffer += new_data
                    
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        try:
                            line_str = line.decode('utf-8', errors='replace').strip()
                            
                            if line_str.startswith("2,"):
                                print("\nData Received!")
                                print("Processing direct encrypted message...")
                                print("==========================")
                                encrypted_hex = line_str[2:]
                                print(f"Length: {len(encrypted_hex)}")
                                print("==========================\n")
                                current_nonce, last_received_nonce = process_received_message(
                                    encrypted_hex, key, identity, current_nonce, last_received_nonce
                                )
                            else:
                                try:
                                    json_pattern = re.compile(r'{.*?}')
                                    matches = json_pattern.finditer(line_str)
                                    
                                    found_match = False
                                    for match in matches:
                                        found_match = True
                                        json_str = match.group(0)
                                        message_data = json.loads(json_str)
                                        
                                        if "pgn" in message_data and "sender" in message_data and "data" in message_data:
                                            current_nonce, last_received_nonce = process_bus_message(
                                                message_data, key, identity, current_nonce, last_received_nonce
                                            )
                                        else:
                                            print("\nData Received!")
                                            print("Raw JSON message (unprocessed):")
                                            print("==========================")
                                            print(json.dumps(message_data, indent=2))
                                            print("==========================\n")
                                    
                                    if not found_match:
                                        print(f"\nData Received: {line_str}")
                                    
                                except json.JSONDecodeError:
                                    print(f"\nData Received (non-JSON): {line_str}")
                                    
                        except Exception as e:
                            print(f"Error processing line: {e}")
                    
                    if len(buffer) > 10000:
                        print("Buffer too large, clearing...")
                        buffer = b""
                
                time.sleep(0.01)
                
            except KeyboardInterrupt:
                print("\nStopping...")
                break
            
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial connection closed")
        
    return current_nonce, last_received_nonce