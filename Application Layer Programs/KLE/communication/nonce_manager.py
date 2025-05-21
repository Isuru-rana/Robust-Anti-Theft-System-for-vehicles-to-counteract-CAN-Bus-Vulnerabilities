# nonce_manager.py
# Functions for managing nonces

import os

def update_nonce_from_message(nonce_value, current_nonce, last_received_nonce):
    try:
        nonce_value = int(nonce_value)
        
        new_last_received = last_received_nonce
        new_current = current_nonce
        
        if nonce_value > new_last_received:
            new_last_received = nonce_value
            
            if nonce_value >= new_current:
                new_current = nonce_value
                print(f"Updated current nonce to: {new_current}")
                
        return new_current, new_last_received
        
    except (ValueError, TypeError):
        print(f"Invalid nonce value: {nonce_value}")
        return current_nonce, last_received_nonce

def save_nonce_to_file(identity, current_nonce):
    try:
        nonce_file = f'nonce_{identity}.txt'
        with open(nonce_file, 'w') as f:
            f.write(str(current_nonce))
        print(f"Saved current nonce ({current_nonce}) to {nonce_file}")
        return True
    except Exception as e:
        print(f"Error saving nonce to file: {e}")
        return False

def load_nonce_from_file(identity):
    try:
        nonce_file = f'nonce_{identity}.txt'
        if os.path.exists(nonce_file):
            with open(nonce_file, 'r') as f:
                saved_nonce = int(f.read().strip())
                print(f"Loaded nonce from file: {saved_nonce}")
                return saved_nonce, saved_nonce
        else:
            print("No saved nonce file found, starting with nonce 0")
            return 0, 0
    except Exception as e:
        print(f"Error loading nonce from file: {e}")
        return 0, 0