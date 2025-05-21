# echo_responder.py
# Script to create an echo responder for testing serial bus latency

import serial
import time
import argparse
import json
import binascii
import threading

def create_test_key():
    print("Using hardcoded test key for encryption")
    return binascii.unhexlify('0123456789abcdef0123456789abcdef')

def encrypt_message(plain_text, key, current_nonce):
    try:
        if isinstance(plain_text, str):
            plain_text = plain_text.encode('utf-8')
        
        nonce_bytes = current_nonce.to_bytes(4, byteorder='big')
        data_with_nonce = nonce_bytes + plain_text
        
        return data_with_nonce.hex(), current_nonce + 1
    except Exception as e:
        print(f"Encryption error: {e}")
        if isinstance(plain_text, str):
            return plain_text.encode('utf-8').hex(), current_nonce + 1
        return plain_text.hex(), current_nonce + 1

def decrypt_message(encrypted_hex, key):
    try:
        data_bytes = bytes.fromhex(encrypted_hex)
        
        if len(data_bytes) > 4:
            actual_data = data_bytes[4:]
            return actual_data.decode('utf-8')
        else:
            return None
    except Exception as e:
        print(f"Decryption error: {e}")
        return None

class EchoResponder:
    def __init__(self, port, baud=115200, identity="ECH", response_delay=0.0):
        self.port = port
        self.baud = baud
        self.identity = identity
        self.response_delay = response_delay
        self.ser = None
        self.running = False
        self.buffer = b""
        self.key = create_test_key()
        self.current_nonce = 0
        self.message_count = 0
        
    def start(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"Echo Responder connected to {self.port} at {self.baud} baud")
            print(f"Using identity: {self.identity}")
            print(f"Response delay: {self.response_delay} seconds")
            
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            
            self.running = True
            
            self.run_loop()
            
            return True
        except serial.SerialException as e:
            print(f"Error opening serial port: {e}")
            return False
    
    def stop(self):
        self.running = False
        if self.ser:
            self.ser.close()
        print("Echo Responder stopped")
    
    def run_loop(self):
        print("Listening for messages... Press Ctrl+C to exit")
        
        while self.running:
            try:
                if self.ser.in_waiting > 0:
                    new_data = self.ser.read(self.ser.in_waiting)
                    self.buffer += new_data
                    
                    while b'\n' in self.buffer:
                        message, self.buffer = self.buffer.split(b'\n', 1)
                        
                        try:
                            message_str = message.decode('utf-8').strip()
                            
                            if message_str.startswith("2,"):
                                self.process_encrypted_message(message_str[2:])
                            else:
                                response = f"ECHO:{message_str}\n"
                                
                                if self.response_delay > 0:
                                    time.sleep(self.response_delay)
                                    
                                self.ser.write(response.encode('utf-8'))
                                self.ser.flush()
                                self.message_count += 1
                                
                        except Exception as e:
                            print(f"Error processing message: {e}")
                
                if len(self.buffer) > 10000:
                    print("Buffer too large, clearing...")
                    self.buffer = b""
                
                time.sleep(0.001)
                
            except KeyboardInterrupt:
                print("\nStopping...")
                self.stop()
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(0.1)
    
    def process_encrypted_message(self, encrypted_hex):
        decrypted_json = decrypt_message(encrypted_hex, self.key)
        if decrypted_json is None:
            print("Decryption Failed!")
            return
        
        try:
            message = json.loads(decrypted_json)
            
            sender = message.get("n", "unknown")
            command = message.get("c", "unknown")
            data = message.get("d", "")
            
            self.message_count += 1
            if self.message_count % 10 == 0:
                print(f"Processed {self.message_count} messages")
            
            response = {
                "n": self.identity,
                "c": "r",
                "d": data
            }
            
            response_json = json.dumps(response)
            
            if self.response_delay > 0:
                time.sleep(self.response_delay)
            
            encrypted_response, self.current_nonce = encrypt_message(
                response_json, self.key, self.current_nonce
            )
            
            response_msg = f"2,{encrypted_response}\n"
            
            self.ser.write(response_msg.encode('utf-8'))
            self.ser.flush()
            
        except json.JSONDecodeError:
            print("Invalid JSON data in decrypted message")
        except Exception as e:
            print(f"Error processing message: {e}")

def main():
    parser = argparse.ArgumentParser(description='Echo Responder for Serial Bus Latency Testing')
    parser.add_argument('--port', default='COM14', help='COM port to use')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate')
    parser.add_argument('--identity', default='ECH', help='Device identity')
    parser.add_argument('--delay', type=float, default=0.0, help='Artificial delay for responses (seconds)')
    args = parser.parse_args()
    
    print(f"=== Echo Responder for Serial Bus Latency Testing ===")
    
    responder = EchoResponder(
        args.port, args.baud, args.identity, args.delay
    )
    
    try:
        responder.start()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        responder.stop()

if __name__ == "__main__":
    main()