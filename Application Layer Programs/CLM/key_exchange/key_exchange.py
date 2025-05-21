# key_exchange.py
# Key exchange module for Burmester-Desmedt Key Exchange.

import hashlib
from secrets import randbits
import config
from key_exchange import database
from key_exchange import utils

def reset_key_exchange_state():
    config.current_session_id = database.generate_session_id()

    config.private_key = None
    config.public_key = None
    config.t_value = None
    config.public_keys = {}
    config.t_values = {}
    config.shared_key = None
    
    print("Key exchange state reset")
    print(f"New session ID: {config.current_session_id}")

def gen_private_key():
    config.private_key = randbits(256)
    print(f"Generated private key: {config.private_key}")

def gen_public_key():
    config.public_key = pow(config.MODP_1024_G, config.private_key, config.MODP_1024_P)
    print(f"Generated public key: {config.public_key}")
    config.public_keys[config.IDENTITY] = config.public_key
    return config.public_key

def compute_t_value(next_public_key):
    config.t_value = pow(next_public_key, config.private_key, config.MODP_1024_P)
    print(f"Computed T value: {config.t_value}")
    config.t_values[config.IDENTITY] = config.t_value
    return config.t_value

def compute_shared_key():
    if not config.t_value or len(config.t_values) < len(config.PARTICIPANTS):
        print("Cannot compute shared key: missing t values")
        return None
    
    config.shared_key = config.t_value
    
    for participant, t in config.t_values.items():
        if participant != config.IDENTITY:
            config.shared_key = (config.shared_key * t) % config.MODP_1024_P
    
    print(f"Computed shared key: {config.shared_key}")
    
    database.save_session_data(config.current_session_id, config.key_exchange_requester)

    derived_key = hashlib.sha256(str(config.shared_key).encode()).digest()
    print(f"Derived encryption key (hex): {derived_key.hex()}")
    
    return config.shared_key