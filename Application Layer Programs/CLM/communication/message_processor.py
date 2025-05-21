# message_processor.py
# Functions for processing messages

import json
import binascii
from communication.crypto import decrypt_message
from communication.nonce_manager import update_nonce_from_message

def process_received_message(hex_data, key, identity, current_nonce, last_received_nonce):
    if key is None:
        print("Cannot process message: No decryption key available")
        return current_nonce, last_received_nonce
    
    try:
        print("Decrypting data...")
        decrypted_json = decrypt_message(hex_data, key)
        if decrypted_json is None:
            print("Decryption Failed!")
            return current_nonce, last_received_nonce
        else:
            print("Decryption Successful")
        
        message = json.loads(decrypted_json)
        
        sender = message.get("n", "unknown")
        command = message.get("c", "unknown")
        data = message.get("d", "")
        nonce = message.get("t", 0)
        
        new_current, new_last = update_nonce_from_message(nonce, current_nonce, last_received_nonce)
        
        print(f"\nDecrypted Data: {decrypted_json}")
        
        return new_current, new_last
        
    except json.JSONDecodeError as e:
        print("Decryption Failed: Invalid JSON data")
        return current_nonce, last_received_nonce
    except Exception as e:
        print(f"Decryption Failed: {e}")
        return current_nonce, last_received_nonce

def process_bus_message(message_data, key, identity, current_nonce, last_received_nonce):
    try:
        pgn = message_data.get('pgn', 'unknown')
        sender = message_data.get('sender', 'unknown')
        hex_data = message_data.get('data', '')
        size = message_data.get('size', len(hex_data)//2)
        
        print("\nData Received!")
        print("Processing bus message...")
        print("==========================")
        print(f"PGN: {pgn}, Sender: {sender}, Length: {len(hex_data)}")
        print("==========================\n")
        
        print("Analyzing data...")
        valid_hex = all(c in '0123456789abcdefABCDEF' for c in hex_data)
        print(f"Is valid hex: {valid_hex}")
        
        try:
            cleaned_hex = ''.join(c for c in hex_data if c.lower() in '0123456789abcdef')
            
            if len(cleaned_hex) % 2 != 0:
                cleaned_hex = '0' + cleaned_hex
            
            data_bytes = bytes.fromhex(cleaned_hex)
            print(f"Converted to bytes (length: {len(data_bytes)})")
            
            print("Decoding ASCII...")
            try:
                ascii_text = data_bytes.decode('ascii', errors='replace')
                
                return process_received_message(ascii_text, key, identity, current_nonce, last_received_nonce)
                    
            except UnicodeDecodeError:
                print("Failed to decode as ASCII")
                return process_received_message(hex_data, key, identity, current_nonce, last_received_nonce)
                
        except binascii.Error as e:
            print(f"Error in hex data: {e}")
            print("Attempting direct decryption...")
            return process_received_message(hex_data, key, identity, current_nonce, last_received_nonce)
            
    except Exception as e:
        print(f"Error processing message: {e}")
        if 'hex_data' in locals():
            print("Attempting direct decryption...")
            return process_received_message(hex_data, key, identity, current_nonce, last_received_nonce)
    
    return current_nonce, last_received_nonce