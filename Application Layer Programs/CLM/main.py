# main_fixed.py
# Improved main entry point with reliable fix for integration

import serial
import argparse
import time
import json
import re
import msvcrt
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    import config
    
    from key_exchange.database import init_database
    from key_exchange.messaging import start_key_exchange, process_message, check_and_handle_retries
    
    from utils.db_utils import get_latest_derived_key
    from communication.nonce_manager import load_nonce_from_file, save_nonce_to_file
    
    from integration_fixes import get_key_info, fix_transceiver_loop
    
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure all required modules are in the correct directories.")
    print("Use absolute imports from the project root directory.")
    sys.exit(1)

def run_key_exchange(ser, auto_start=False):
    print(f"\n=== Burmester-Desmedt Key Exchange (Device: {config.IDENTITY}) ===")
    
    config.key_exchange_requester = None
    config.current_session_id = None
    
    buffer = b""
    last_retry_check = time.time()
    
    try:
        if auto_start:
            print("Auto-start enabled, will initiate key exchange in 5 seconds...")
            time.sleep(5)
            start_key_exchange(ser)
        else:
            print("Press 'Enter' to start key exchange, or wait for incoming requests...")
        
        while True:
            try:
                if not auto_start and msvcrt.kbhit():
                    key = msvcrt.getch()
                    if key[0] == 13 if isinstance(key, bytes) else key == 13:
                        start_key_exchange(ser)
                
                if ser.in_waiting > 0:
                    new_data = ser.read(ser.in_waiting)
                    buffer += new_data
                    
                    json_pattern = re.compile(rb'{.*?}')
                    matches = json_pattern.finditer(buffer)
                    
                    last_end = 0
                    found_any = False
                    
                    for match in matches:
                        found_any = True
                        start, end = match.span()
                        last_end = end
                        
                        json_bytes = buffer[start:end]
                        try:
                            json_data = json.loads(json_bytes.decode('utf-8'))
                            process_message(json_data, ser)
                        except json.JSONDecodeError:
                            print(f"Invalid JSON: {json_bytes}")
                        except Exception as e:
                            print(f"Error processing JSON: {e}")
                    
                    if found_any:
                        buffer = buffer[last_end:]
                    
                    if len(buffer) > 10000:
                        print("Buffer too large, clearing...")
                        buffer = b""
                
                current_time = time.time()
                if current_time - last_retry_check >= 0.1:
                    check_and_handle_retries(ser)
                    last_retry_check = current_time
                
                time.sleep(0.01)
                
                if config.shared_key is not None:
                    print("\nKey exchange completed successfully!")
                    derived_key = get_latest_derived_key(config.IDENTITY)
                    print(f"Derived encryption key: {derived_key.hex()}")
                    input("\nPress Enter to return to main menu...")
                    return True
                    
            except KeyboardInterrupt:
                print("\nKey exchange interrupted...")
                return False
            
    except Exception as e:
        print(f"Error in key exchange: {e}")
        return False

def run_fixed_transceiver(ser, receive_only=False, reset_nonce=False, no_load_nonce=False):
    print(f"\n=== BD Encrypted Transceiver (Device: {config.IDENTITY}) ===")
    
    if reset_nonce:
        current_nonce = 0
        last_received_nonce = 0
        print("Nonce counter reset to 0")
    elif not no_load_nonce:
        current_nonce, last_received_nonce = load_nonce_from_file(config.IDENTITY)
    else:
        current_nonce = 0
        last_received_nonce = 0

    print(f"Current nonce: {current_nonce}")
    
    key = get_latest_derived_key(config.IDENTITY)
    if key is None:
        print("WARNING: No encryption key available. Run key exchange first!")
        input("\nPress Enter to return to main menu...")
        return False
    else:
        print(f"Found encryption key: {key.hex()}")
        
    current_nonce, last_received_nonce = fix_transceiver_loop(
        ser, config.IDENTITY, current_nonce, last_received_nonce, key
    )
    
    save_nonce_to_file(config.IDENTITY, current_nonce)
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Burmester-Desmedt Secure Communication System'
    )
    
    parser.add_argument('--identity', '-i', default='CLM', 
                        help='Device identity (CLM, KLE, ECU)')
    parser.add_argument('--port', '-p', default=config.DEFAULT_PORT, 
                        help='Serial port to use')
    parser.add_argument('--baud', '-b', type=int, default=config.DEFAULT_BAUD, 
                        help='Baud rate')
    
    parser.add_argument('--mode', '-m', choices=[config.MODE_KEY_EXCHANGE, 
                                               config.MODE_TRANSCEIVER, 
                                               config.MODE_BOTH],
                        default=None, 
                        help='Operation mode')
    
    parser.add_argument('--auto-start', '-a', action='store_true', 
                        help='Automatically start key exchange after delay')
    
    parser.add_argument('--reset-nonce', '-r', action='store_true', 
                        help='Reset the nonce counter to 0 on startup')
    parser.add_argument('--no-load-nonce', '-n', action='store_true', 
                        help='Do not load nonce from file')
    parser.add_argument('--receive-only', '-ro', action='store_true', 
                        help='Receive only mode (no sending)')
    
    args = parser.parse_args()
    
    config.IDENTITY = args.identity
    print(f"Setting identity to: {config.IDENTITY}")
    
    init_database()
    
    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
        print(f"Connected to {args.port} at {args.baud} baud")
        
        if args.mode is None:
            while True:
                print("\n=== Burmester-Desmedt Secure Communication System ===")
                print(f"Device: {config.IDENTITY}")
                print("\nSelect operation mode:")
                print("1. Run key exchange")
                print("2. Run encrypted transceiver")
                print("3. Run key exchange, then transceiver")
                print("4. Display key information")
                print("5. Exit")
                
                choice = input("\nEnter choice (1-5): ")
                
                if choice == '1':
                    run_key_exchange(ser, args.auto_start)
                elif choice == '2':
                    run_fixed_transceiver(ser, args.receive_only, args.reset_nonce, args.no_load_nonce)
                elif choice == '3':
                    success = run_key_exchange(ser, args.auto_start)
                    if success:
                        run_fixed_transceiver(ser, args.receive_only, args.reset_nonce, args.no_load_nonce)
                elif choice == '4':
                    get_key_info(config.IDENTITY)
                elif choice == '5':
                    print("Exiting...")
                    break
                else:
                    print("Invalid choice, please try again.")
        else:
            if args.mode == config.MODE_KEY_EXCHANGE:
                run_key_exchange(ser, args.auto_start)
            elif args.mode == config.MODE_TRANSCEIVER:
                run_fixed_transceiver(ser, args.receive_only, args.reset_nonce, args.no_load_nonce)
            elif args.mode == config.MODE_BOTH:
                success = run_key_exchange(ser, args.auto_start)
                if success:
                    run_fixed_transceiver(ser, args.receive_only, args.reset_nonce, args.no_load_nonce)
    
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial connection closed")

if __name__ == "__main__":
    main()