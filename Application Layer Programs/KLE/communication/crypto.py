# crypto.py
# Modified functions for encryption and decryption

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
import json

def encrypt_message(plain_text, key, current_nonce):
    try:
        message_dict = json.loads(plain_text)        
        new_nonce = current_nonce + 1        
        message_dict["t"] = new_nonce        
        plain_text = json.dumps(message_dict)
        
        if isinstance(plain_text, str):
            plain_text = plain_text.encode('utf-8')
            
        cipher = AES.new(key, AES.MODE_ECB)
        padded_data = pad(plain_text, AES.block_size)        
        encrypted_data = cipher.encrypt(padded_data)        
        hex_data = encrypted_data.hex()

        return hex_data, new_nonce
        
    except Exception as e:
        print(f"Encryption error: {e}")
        return None, current_nonce

def decrypt_message(encrypted_hex, key):
    try:
        cleaned_hex = ''.join(c for c in encrypted_hex if c.lower() in '0123456789abcdef')
        
        if len(cleaned_hex) % 2 != 0:
            cleaned_hex = '0' + cleaned_hex
        
        encrypted_data = bytes.fromhex(cleaned_hex)
        cipher = AES.new(key, AES.MODE_ECB)        
        decrypted_padded = cipher.decrypt(encrypted_data)
        
        try:
            decrypted_data = unpad(decrypted_padded, AES.block_size)
            
            try:
                plain_text = decrypted_data.decode('utf-8')
                return plain_text
            except UnicodeDecodeError:
                plain_text = decrypted_data.decode('latin-1')
                return plain_text
            
        except ValueError as padding_error:
            try:
                last_brace_pos = decrypted_padded.rfind(b'}')
                if last_brace_pos > 0:
                    potential_json = decrypted_padded[:last_brace_pos+1].decode('utf-8', errors='replace')
                    try:
                        json.loads(potential_json)
                        return potential_json
                    except json.JSONDecodeError:
                        pass
            except Exception:
                pass
                
            return None
        
    except Exception as e:
        return None