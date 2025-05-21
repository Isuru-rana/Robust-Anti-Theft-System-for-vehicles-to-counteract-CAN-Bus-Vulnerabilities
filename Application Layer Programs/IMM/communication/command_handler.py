# command_handler.py
# Functions for handling user commands

import msvcrt
from utils.db_utils import get_latest_derived_key
from communication.sender import send_encrypted_message
from communication.nonce_manager import save_nonce_to_file

def handle_commands(ser, identity, key, current_nonce, last_received_nonce):
    if msvcrt.kbhit():
        try:
            input_line = input("\nEnter message: ")
            
            if input_line.lower() == "!reload":
                new_key = get_latest_derived_key(identity)
                if new_key:
                    print(f"Reloaded encryption key: {new_key.hex()}")
                    return new_key, current_nonce, last_received_nonce
                else:
                    print("No encryption key available!")
            elif input_line.lower() == "!nonce":
                print(f"Current nonce: {current_nonce}")
                print(f"Last received nonce: {last_received_nonce}")
            elif input_line.lower() == "!reset-nonce":
                print("Nonce counter reset to 0")
                return key, 0, 0
            elif input_line.lower() == "!save-nonce":
                save_nonce_to_file(identity, current_nonce)
            else:
                new_nonce, success = send_encrypted_message(
                    ser, identity, "ALL", "s", input_line, key, current_nonce
                )
                if success:
                    return key, new_nonce, last_received_nonce
        except Exception as e:
            print(f"Error handling input: {e}")
    
    return key, current_nonce, last_received_nonce