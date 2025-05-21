# sender.py
# Functions for sending encrypted messages

import json
from communication.crypto import encrypt_message

def send_encrypted_message(ser, identity, recipient, command, data, key, current_nonce):
    if key is None:
        print("Cannot send message: No encryption key available")
        return current_nonce, False
    
    message = {
        "n": identity,
        "c": command,
        "d": data
    }
    
    message_json = json.dumps(message)
    
    print(f"Sending message: {message_json}")
    
    encrypted_hex, new_nonce = encrypt_message(message_json, key, current_nonce)
    if encrypted_hex is None:
        print("Failed to encrypt message")
        return current_nonce, False
    
    serial_msg = f"2,{encrypted_hex}\n"
    
    ser.write(serial_msg.encode('utf-8'))
    ser.flush()
    
    print(f"Sent encrypted message: {encrypted_hex[:20]}...")
    return new_nonce, True