# integration_fixes.py
# Fixes for integrating key exchange and transceiver

import sqlite3
import json
import os
import msvcrt
import time
import re

def get_key_info(identity):
    try:
        conn = sqlite3.connect(f'key_exchange_{identity}.db')
        c = conn.cursor()
        
        c.execute('''SELECT session_id, timestamp, requester, derived_key 
                    FROM key_exchange_sessions 
                    WHERE derived_key IS NOT NULL 
                    ORDER BY timestamp DESC LIMIT 1''')
        
        result = c.fetchone()
        conn.close()
        
        if result is None:
            print("No key information found in the database!")
            return None
        
        session_id, timestamp, requester, derived_key_hex = result
        
        print("\n=== KEY INFORMATION ===")
        print(f"Session ID: {session_id}")
        print(f"Timestamp: {timestamp}")
        print(f"Requester: {requester}")
        print(f"Derived key (hex): {derived_key_hex}")
        
        derived_key = bytes.fromhex(derived_key_hex)
        aes_key = derived_key[:16]
        
        print(f"AES-128 key (hex): {aes_key.hex()}")
        print("=== END KEY INFO ===\n")
        
        return aes_key
    
    except Exception as e:
        print(f"Error retrieving key info: {e}")
        return None

def fix_transceiver_loop(ser, identity, current_nonce, last_received_nonce, key):
    from communication.sender import send_encrypted_message
    from communication.message_processor import process_received_message, process_bus_message
    
    buffer = b""
    
    print("\n=== IMPROVED TRANSCEIVER LOOP ===")
    print(f"Identity: {identity}")
    print(f"Current nonce: {current_nonce}")
    print(f"Last received nonce: {last_received_nonce}")
    
    if key:
        print(f"Using key: {key.hex()}")
    else:
        print("No key available!")
        return current_nonce, last_received_nonce
    
    print("\nCommands:")
    print("  !key     - Display current key info")
    print("  !reload  - Reload encryption key")
    print("  !nonce   - Display nonce values")
    print("  !reset   - Reset nonce counters")
    print("  !quit    - Exit transceiver")
    print("  [text]   - Send encrypted message")
    
    while True:
        try:
            if msvcrt.kbhit():
                input_line = input("\nEnter command or message: ")
                
                if input_line.lower() == "!key":
                    key = get_key_info(identity)
                elif input_line.lower() == "!reload":
                    from utils.db_utils import get_latest_derived_key
                    key = get_latest_derived_key(identity)
                    if key:
                        print(f"Reloaded key: {key.hex()}")
                    else:
                        print("No key available!")
                elif input_line.lower() == "!nonce":
                    print(f"Current nonce: {current_nonce}")
                    print(f"Last received nonce: {last_received_nonce}")
                elif input_line.lower() == "!reset":
                    current_nonce = 0
                    last_received_nonce = 0
                    print("Nonce counters reset to 0")
                elif input_line.lower() == "!quit":
                    print("Exiting transceiver...")
                    break
                else:
                    if key:
                        from communication.crypto import encrypt_message
                        
                        message = {
                            "n": identity,
                            "c": "s",
                            "d": input_line
                        }
                        message_json = json.dumps(message)
                        
                        print(f"Sending message as {identity}: {message_json}")
                        encrypted_hex, new_nonce = encrypt_message(message_json, key, current_nonce)
                        
                        if encrypted_hex:
                            serial_msg = f"2,{encrypted_hex}\n"
                            ser.write(serial_msg.encode('utf-8'))
                            ser.flush()
                            print(f"Message sent (encrypted): {encrypted_hex[:50]}...")
                            current_nonce = new_nonce
                        else:
                            print("Failed to encrypt message!")
                    else:
                        print("Cannot send message: No encryption key available")
            
            if ser.in_waiting > 0:
                new_data = ser.read(ser.in_waiting)
                buffer += new_data
                
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    
                    try:
                        line_str = line.decode('utf-8', errors='replace').strip()
                        
                        if line_str.startswith("2,"):
                            encrypted_hex = line_str[2:].strip()
                            print("\nData Received!")
                            print("Processing direct encrypted message...")
                            print("==========================")
                            print(f"Length: {len(encrypted_hex)}")
                            print("==========================\n")
                            
                            from communication.crypto import decrypt_message
                            print("Decrypting data...")
                            decrypted_json = decrypt_message(encrypted_hex, key)
                            
                            if decrypted_json:
                                print("Decryption Successful")
                                try:
                                    message = json.loads(decrypted_json)
                                    
                                    sender = message.get("n", "unknown")
                                    command = message.get("c", "unknown")
                                    data = message.get("d", "")
                                    nonce = message.get("t", 0)
                                    
                                    if nonce > last_received_nonce:
                                        last_received_nonce = nonce
                                        if nonce > current_nonce:
                                            current_nonce = nonce
                                    
                                    print(f"\nDecrypted Data: {decrypted_json}")
                                    
                                except json.JSONDecodeError as e:
                                    print("Decryption Failed: Invalid JSON data")
                            else:
                                print("Decryption Failed!")
                        
                        elif line_str.startswith("{") and line_str.endswith("}"):
                            try:
                                message_data = json.loads(line_str)
                                
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
                            except json.JSONDecodeError:
                                print(f"Invalid JSON received: {line_str[:50]}...")
                        else:
                            print(f"Unrecognized message format: {line_str[:50]}...")
                    
                    except Exception as e:
                        print(f"Error processing received data: {type(e).__name__}: {e}")
                
                if len(buffer) > 10000:
                    print("Buffer too large, clearing...")
                    buffer = b""
            
            time.sleep(0.01)
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error in transceiver loop: {type(e).__name__}: {e}")
            time.sleep(1)
    
    return current_nonce, last_received_nonce