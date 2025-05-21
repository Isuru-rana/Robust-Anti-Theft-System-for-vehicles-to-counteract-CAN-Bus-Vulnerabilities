# complete_latency_test.py
# Script to test latency using the complete encryption/decryption process

import serial
import time
import argparse
import statistics
import json
import binascii
import re
from datetime import datetime
import os
import sys

try:
    from communication.crypto import encrypt_message, decrypt_message
    from communication.nonce_manager import update_nonce_from_message
    from communication.message_processor import process_received_message, process_bus_message
    print("Successfully imported actual encryption and processing modules")
except ImportError:
    print("WARNING: Could not import required modules. Make sure they are in your Python path.")
    sys.exit(1)

def create_test_key():
    print("Using fixed 16-byte test key for AES-128 encryption")
    return binascii.unhexlify('0123456789abcdef0123456789abcdef')

class CompleteLatencyTest:
    def __init__(self, tx_port, rx_port, baud=115200, num_messages=50, 
                 message_size=32, timeout=1.0, identity="TEST"):
        self.tx_port = tx_port
        self.rx_port = rx_port
        self.baud = baud
        self.num_messages = num_messages
        self.message_size = message_size
        self.timeout = timeout
        self.identity = identity
        self.ser_tx = None
        self.ser_rx = None
        self.latency_measurements = []
        self.encrypt_times = []
        self.process_times = []
        self.success_count = 0
        self.timeout_count = 0
        self.error_count = 0
        self.current_nonce = 0
        self.last_received_nonce = 0
        self.key = create_test_key()
    
    def start(self):
        try:
            self.ser_tx = serial.Serial(self.tx_port, self.baud, timeout=self.timeout)
            print(f"Connected to {self.tx_port} at {self.baud} baud (transmitter)")
            
            self.ser_rx = serial.Serial(self.rx_port, self.baud, timeout=self.timeout)
            print(f"Connected to {self.rx_port} at {self.baud} baud (receiver)")
            
            self.ser_tx.reset_input_buffer()
            self.ser_tx.reset_output_buffer()
            self.ser_rx.reset_input_buffer()
            self.ser_rx.reset_output_buffer()
            
            time.sleep(0.5)
            
            return True
        except serial.SerialException as e:
            print(f"Error opening serial ports: {e}")
            if self.ser_tx:
                self.ser_tx.close()
            if self.ser_rx:
                self.ser_rx.close()
            return False
    
    def stop(self):
        if self.ser_tx:
            self.ser_tx.close()
        if self.ser_rx:
            self.ser_rx.close()
        print("Serial connections closed")
    
    def send_message(self, message_id):
        timestamp = time.time()
        base_content = f"{timestamp}:{message_id}"
        
        remaining_space = self.message_size - len(base_content)
        if remaining_space > 0:
            padding = "X" * remaining_space
            data = base_content + padding
        else:
            data = base_content[:self.message_size]
        
        message = {
            "n": self.identity,
            "c": "t",
            "d": data
        }
        
        message_json = json.dumps(message)
        
        encrypt_start = time.time()
        encrypted_hex, new_nonce = encrypt_message(message_json, self.key, self.current_nonce)
        encrypt_end = time.time()
        encrypt_time = (encrypt_end - encrypt_start) * 1000
        self.encrypt_times.append(encrypt_time)
        
        if encrypted_hex is None:
            print(f"Failed to encrypt message {message_id}")
            self.error_count += 1
            return False
        
        self.current_nonce = new_nonce
        
        serial_msg = f"2,{encrypted_hex}\n"
        
        self.ser_rx.reset_input_buffer()
        
        send_time = time.time()
        self.ser_tx.write(serial_msg.encode('utf-8'))
        self.ser_tx.flush()
        
        buffer = b""
        start_wait = time.time()
        
        while (time.time() - start_wait) < self.timeout:
            if self.ser_rx.in_waiting > 0:
                data = self.ser_rx.read(self.ser_rx.in_waiting)
                buffer += data
                
                if b'\n' in buffer:
                    response, buffer = buffer.split(b'\n', 1)
                    
                    receive_time = time.time()
                    latency = (receive_time - send_time) * 1000
                    
                    try:
                        line_str = response.decode('utf-8', errors='replace').strip()
                        
                        process_start = time.time()
                        
                        if line_str.startswith("2,"):
                            encrypted_hex = line_str[2:]
                            
                            try:
                                decrypted_json = decrypt_message(encrypted_hex, self.key)
                                if decrypted_json is None:
                                    print(f"Message {message_id}: Decryption failed")
                                    self.error_count += 1
                                    return False
                                
                                response_message = json.loads(decrypted_json)
                                process_end = time.time()
                                process_time = (process_end - process_start) * 1000
                                self.process_times.append(process_time)
                                
                                print(f"Sending test message {message_id}: latency {latency:.2f} ms "
                                      f"(Encrypt: {encrypt_time:.2f} ms, Process: {process_time:.2f} ms)")
                                
                                self.latency_measurements.append(latency)
                                self.success_count += 1
                                return True
                                
                            except Exception as e:
                                print(f"Message {message_id}: Error processing encrypted response: {e}")
                                self.error_count += 1
                                return False
                        else:
                            try:
                                json_pattern = re.compile(r'{.*?}')
                                match = json_pattern.search(line_str)
                                
                                if match:
                                    json_str = match.group(0)
                                    message_data = json.loads(json_str)
                                    
                                    if "pgn" in message_data and "sender" in message_data and "data" in message_data:
                                        hex_data = message_data.get('data', '')
                                        
                                        try:
                                            cleaned_hex = ''.join(c for c in hex_data if c.lower() in '0123456789abcdef')
                                            
                                            if len(cleaned_hex) % 2 != 0:
                                                cleaned_hex = '0' + cleaned_hex
                                            
                                            data_bytes = bytes.fromhex(cleaned_hex)
                                            
                                            try:
                                                ascii_text = data_bytes.decode('ascii', errors='replace')
                                                
                                                decrypted_json = decrypt_message(ascii_text, self.key)
                                                if decrypted_json is not None:
                                                    response_message = json.loads(decrypted_json)
                                                    process_end = time.time()
                                                    process_time = (process_end - process_start) * 1000
                                                    self.process_times.append(process_time)
                                                    
                                                    print(f"Message {message_id}: Round-trip latency {latency:.2f} ms "
                                                          f"(Encrypt: {encrypt_time:.2f} ms, Process: {process_time:.2f} ms)")
                                                    
                                                    self.latency_measurements.append(latency)
                                                    self.success_count += 1
                                                    return True
                                                else:
                                                    decrypted_json = decrypt_message(hex_data, self.key)
                                                    if decrypted_json is not None:
                                                        response_message = json.loads(decrypted_json)
                                                        process_end = time.time()
                                                        process_time = (process_end - process_start) * 1000
                                                        self.process_times.append(process_time)
                                                        
                                                        print(f"Message {message_id}: Round-trip latency {latency:.2f} ms "
                                                              f"(Encrypt: {encrypt_time:.2f} ms, Process: {process_time:.2f} ms)")
                                                        
                                                        self.latency_measurements.append(latency)
                                                        self.success_count += 1
                                                        return True
                                            except UnicodeDecodeError:
                                                decrypted_json = decrypt_message(hex_data, self.key)
                                                if decrypted_json is not None:
                                                    response_message = json.loads(decrypted_json)
                                                    process_end = time.time()
                                                    process_time = (process_end - process_start) * 1000
                                                    self.process_times.append(process_time)
                                                    
                                                    print(f"Message {message_id}: Round-trip latency {latency:.2f} ms "
                                                          f"(Encrypt: {encrypt_time:.2f} ms, Process: {process_time:.2f} ms)")
                                                    
                                                    self.latency_measurements.append(latency)
                                                    self.success_count += 1
                                                    return True
                                        except Exception as e:
                                            print(f"Message {message_id}: Error processing bus message data: {e}")
                                    
                                    print(f"Message {message_id}: Received bus message but couldn't decrypt data: {json_str[:50]}...")
                                    self.error_count += 1
                                    return False
                                else:
                                    print(f"Message {message_id}: Received non-JSON response: {line_str[:50]}...")
                                    self.error_count += 1
                                    return False
                            except json.JSONDecodeError:
                                print(f"Message {message_id}: Invalid JSON in response: {line_str[:50]}...")
                                self.error_count += 1
                                return False
                            except Exception as e:
                                print(f"Message {message_id}: Error processing JSON response: {e}")
                                self.error_count += 1
                                return False
                    except Exception as e:
                        print(f"Message {message_id}: Error processing response: {e}")
                        self.error_count += 1
                        return False
            
            time.sleep(0.001)
        
        print(f"Sending test message {message_id}: Timeout waiting for response")
        self.timeout_count += 1
        return False
    
    def run_test(self):
        print(f"Starting complete latency test: sending {self.num_messages} messages...")
        
        for i in range(self.num_messages):
            message_id = f"{i+1:05d}"
            
            self.send_message(message_id)
            
            time.sleep(0.05)
            
            if (i+1) % 10 == 0:
                print(f"Progress: {i+1}/{self.num_messages} messages processed")
        
        self.print_statistics()
    
    def print_statistics(self):
        if not self.latency_measurements:
            print("\nNo successful measurements recorded!")
            return
        
        min_latency = min(self.latency_measurements)
        max_latency = max(self.latency_measurements)
        avg_latency = sum(self.latency_measurements) / len(self.latency_measurements)
        median_latency = statistics.median(self.latency_measurements)
        
        avg_encrypt = sum(self.encrypt_times) / len(self.encrypt_times)
        avg_process = sum(self.process_times) / len(self.process_times) if self.process_times else 0
        
        p90 = sorted(self.latency_measurements)[int(len(self.latency_measurements) * 0.9)]
        p95 = sorted(self.latency_measurements)[int(len(self.latency_measurements) * 0.95)]
        p99 = sorted(self.latency_measurements)[int(len(self.latency_measurements) * 0.99)]
        
        if len(self.latency_measurements) > 1:
            std_dev = statistics.stdev(self.latency_measurements)
        else:
            std_dev = 0
        
        print("\n--- COMPLETE LATENCY TEST RESULTS ---")
        print(f"Messages sent:       {self.num_messages}")
        print(f"Successful messages: {self.success_count}")
        print(f"Timeouts:            {self.timeout_count}")
        print(f"Errors:              {self.error_count}")
        success_rate = (self.success_count/self.num_messages*100) if self.num_messages > 0 else 0
        print(f"Success rate:        {success_rate:.2f}%")
        
        print("\n--- ROUND-TRIP LATENCY STATISTICS (milliseconds) ---")
        print(f"Minimum:    {min_latency:.2f} ms")
        print(f"Maximum:    {max_latency:.2f} ms")
        print(f"Average:    {avg_latency:.2f} ms")
        print(f"Median:     {median_latency:.2f} ms")
        print(f"Std Dev:    {std_dev:.2f} ms")
        print(f"90th %-ile: {p90:.2f} ms")
        print(f"95th %-ile: {p95:.2f} ms")
        print(f"99th %-ile: {p99:.2f} ms")
        
        print("\n--- PROCESSING TIMES (milliseconds) ---")
        print(f"Average encryption time:   {avg_encrypt:.2f} ms")
        print(f"Average processing time:   {avg_process:.2f} ms")
        total_process = avg_encrypt + avg_process
        print(f"Total processing overhead: {total_process:.2f} ms")
        print(f"Processing percentage:     {(total_process/avg_latency)*100:.2f}%")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_filename = f"complete_latency_{timestamp}.csv"
        
        with open(log_filename, 'w') as f:
            f.write("message_id,round_trip_latency_ms,encryption_time_ms,processing_time_ms\n")
            for i in range(len(self.latency_measurements)):
                process_time = self.process_times[i] if i < len(self.process_times) else 0
                f.write(f"{i+1},{self.latency_measurements[i]:.6f},{self.encrypt_times[i]:.6f},{process_time:.6f}\n")
        
        print(f"\nLatency measurements saved to {log_filename}")

class CompleteEchoResponder:
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
        self.last_received_nonce = 0
        self.message_count = 0
        self.success_count = 0
        self.error_count = 0
        
    def start(self):
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"Complete Echo Responder connected to {self.port} at {self.baud} baud")
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
        print("Complete Echo Responder stopped")
    
    def run_loop(self):
        print("Listening for encrypted messages... Press Ctrl+C to exit")
        
        while self.running:
            try:
                if self.ser.in_waiting > 0:
                    new_data = self.ser.read(self.ser.in_waiting)
                    self.buffer += new_data
                    
                    while b'\n' in self.buffer:
                        message, self.buffer = self.buffer.split(b'\n', 1)
                        
                        try:
                            message_str = message.decode('utf-8', errors='replace').strip()
                            
                            if message_str.startswith("2,"):
                                self.message_count += 1
                                
                                encrypted_hex = message_str[2:]
                                
                                try:
                                    decrypted_json = decrypt_message(encrypted_hex, self.key)
                                    if decrypted_json is None:
                                        print(f"Message {self.message_count}: Decryption failed")
                                        self.error_count += 1
                                        continue
                                    
                                    message_data = json.loads(decrypted_json)
                                    
                                    sender = message_data.get("n", "unknown")
                                    command = message_data.get("c", "unknown")
                                    data = message_data.get("d", "")
                                    nonce = message_data.get("t", 0)
                                    
                                    self.current_nonce, self.last_received_nonce = update_nonce_from_message(
                                        nonce, self.current_nonce, self.last_received_nonce
                                    )
                                    
                                    if self.message_count % 10 == 0:
                                        print(f"Processed {self.message_count} messages, last from: {sender}")
                                    
                                    if self.response_delay > 0:
                                        time.sleep(self.response_delay)
                                    
                                    response = {
                                        "n": self.identity,
                                        "c": "r",
                                        "d": data
                                    }
                                    
                                    response_json = json.dumps(response)
                                    
                                    encrypted_response, self.current_nonce = encrypt_message(
                                        response_json, self.key, self.current_nonce
                                    )
                                    
                                    if encrypted_response is None:
                                        print(f"Message {self.message_count}: Failed to encrypt response")
                                        self.error_count += 1
                                        continue
                                    
                                    response_msg = f"2,{encrypted_response}\n"
                                    
                                    self.ser.write(response_msg.encode('utf-8'))
                                    self.ser.flush()
                                    self.success_count += 1
                                    
                                except Exception as e:
                                    print(f"Message {self.message_count}: Processing error: {e}")
                                    self.error_count += 1
                            else:
                                response = f"ECHO:{message_str}\n"
                                
                                if self.response_delay > 0:
                                    time.sleep(self.response_delay)
                                    
                                self.ser.write(response.encode('utf-8'))
                                self.ser.flush()
                                
                        except Exception as e:
                            print(f"Error processing message: {e}")
                
                if len(self.buffer) > 10000:
                    print("Buffer too large, clearing...")
                    self.buffer = b""
                
                time.sleep(0.001)
                
            except KeyboardInterrupt:
                print("\nStopping...")
                self.print_statistics()
                self.stop()
                break
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(0.1)
    
    def print_statistics(self):
        print("\n--- ECHO RESPONDER STATISTICS ---")
        print(f"Total messages received: {self.message_count}")
        print(f"Successfully processed:  {self.success_count}")
        print(f"Errors:                  {self.error_count}")
        success_rate = (self.success_count/self.message_count*100) if self.message_count > 0 else 0
        print(f"Success rate:            {success_rate:.2f}%")

def main():
    parser = argparse.ArgumentParser(description='Complete Latency Test with Real Encryption Process')
    parser.add_argument('--mode', choices=['test', 'echo'], default='test', 
                       help='Run in test mode or echo responder mode')
    parser.add_argument('--tx-port', default='COM13', help='Transmitter COM port (for test mode)')
    parser.add_argument('--rx-port', default='COM14', help='Receiver COM port (for test mode)')
    parser.add_argument('--port', default='COM14', help='COM port for echo responder mode')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate')
    parser.add_argument('--messages', type=int, default=50, help='Number of messages to send (test mode)')
    parser.add_argument('--size', type=int, default=32, 
                       help='Message data size in bytes (test mode), default=32')
    parser.add_argument('--timeout', type=float, default=5.0, 
                       help='Timeout for responses in seconds (test mode), default=5.0')
    parser.add_argument('--delay', type=float, default=0.0, 
                       help='Artificial delay in seconds (for echo responder)')
    parser.add_argument('--identity', default='TEST', help='Device identity')
    args = parser.parse_args()
    
    if args.mode == 'echo':
        print(f"=== Complete Echo Responder Mode ===")
        responder = CompleteEchoResponder(
            args.port, args.baud, args.identity, args.delay
        )
        try:
            responder.start()
        except Exception as e:
            print(f"Error: {e}")
        finally:
            responder.stop()
    else:
        print(f"=== Complete Latency Test Mode ===")
        print(f"Testing between {args.tx_port} (TX) and {args.rx_port} (RX)")
        print(f"Baud rate: {args.baud}")
        print(f"Sending {args.messages} messages of size {args.size} bytes")
        print(f"Response timeout: {args.timeout} seconds")
        print(f"Identity: {args.identity}")
        
        test = CompleteLatencyTest(
            args.tx_port, args.rx_port, args.baud,
            args.messages, args.size, args.timeout, args.identity
        )
        
        if test.start():
            try:
                test.run_test()
            except KeyboardInterrupt:
                print("\nTest interrupted by user")
            except Exception as e:
                print(f"Error during test: {e}")
            finally:
                test.stop()
        else:
            print("Failed to start the test. Make sure both COM ports are available.")

if __name__ == "__main__":
    main()