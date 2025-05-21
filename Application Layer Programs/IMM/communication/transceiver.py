# transceiver.py
# Main module combining sending and receiving capabilities

import serial
import time
import argparse
import json
import re
import os
import msvcrt

from utils.db_utils import get_latest_derived_key
from communication.nonce_manager import load_nonce_from_file, save_nonce_to_file
from communication.message_processor import process_received_message, process_bus_message
from communication.command_handler import handle_commands

def main():
    parser = argparse.ArgumentParser(description='Encrypted Serial Transceiver')
    parser.add_argument('--identity', '-i', default='BCM', help='Device identity (BCM, PCM, VSM)')
    parser.add_argument('--port', '-p', default='COM3', help='Serial port to use')
    parser.add_argument('--baud', '-b', type=int, default=115200, help='Baud rate')
    parser.add_argument('--reset-nonce', '-r', action='store_true', help='Reset the nonce counter to 0 on startup')
    parser.add_argument('--no-load-nonce', '-n', action='store_true', help='Do not load nonce from file')
    parser.add_argument('--receive-only', '-ro', action='store_true', help='Receive only mode (no sending)')
    args = parser.parse_args()

    identity = args.identity
    
    if args.reset_nonce:
        current_nonce = 0
        last_received_nonce = 0
        print("Nonce counter reset to 0")
    elif not args.no_load_nonce:
        current_nonce, last_received_nonce = load_nonce_from_file(identity)
    else:
        current_nonce = 0
        last_received_nonce = 0

    print(f"=== BD Encrypted Transceiver (Device: {identity}) ===")
    print(f"Current nonce: {current_nonce}")
    
    key = get_latest_derived_key(identity)
    if key is None:
        print("WARNING: No encryption key available. Run key exchange first!")
    else:
        print(f"Found encryption key: {key.hex()}")
    
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        print(f"Connected to {args.port} at {args.baud} baud")
        
        if not args.receive_only:
            print("Enter message to send or press Ctrl+C to exit")
            print("Use '!reload' to reload the encryption key from the database")
            print("Use '!nonce' to display current nonce value")
            print("Use '!reset-nonce' to reset the nonce counter to 0")
            print("Use '!save-nonce' to save the current nonce to a file")
        else:
            print("Running in receive-only mode")
            print("Press Ctrl+C to exit")

        buffer = b""

        while True:
            try:
                if not args.receive_only:
                    key, current_nonce, last_received_nonce = handle_commands(
                        ser, identity, key, current_nonce, last_received_nonce
                    )

                if ser.in_waiting > 0:
                    new_data = ser.read(ser.in_waiting)
                    buffer += new_data
                    
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        try:
                            line_str = line.decode('utf-8', errors='replace').strip()
                            
                            if line_str.startswith("2,"):
                                encrypted_hex = line_str[2:]
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
                                            print(f"Received bus message: {json_str[:60]}...")
                                            current_nonce, last_received_nonce = process_bus_message(
                                                message_data, key, identity, current_nonce, last_received_nonce
                                            )
                                        else:
                                            print(f"Received unrecognized JSON: {json_str}")
                                    
                                    if not found_match:
                                        print(f"Received message: {line_str}")
                                    
                                except json.JSONDecodeError:
                                    print(f"Received non-JSON message: {line_str}")
                                    
                        except Exception as e:
                            print(f"Error processing line: {e}")
                    
                    if len(buffer) > 10000:
                        print("Buffer too large, clearing...")
                        buffer = b""
                
                time.sleep(0.01)
                
            except KeyboardInterrupt:
                print("\nStopping...")
                save_nonce_to_file(identity, current_nonce)
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(1)
    
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial connection closed")
        save_nonce_to_file(identity, current_nonce)

if __name__ == "__main__":
    main()