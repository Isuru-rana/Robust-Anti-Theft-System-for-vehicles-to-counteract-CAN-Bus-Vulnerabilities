# latency_test.py
# Script to test latency between two COM ports using the encrypted transceiver

import serial
import time
import json
import threading
import statistics
import argparse
import os
import sys
import binascii
from datetime import datetime

# Import necessary modules from your encrypted transceiver
# The script assumes these files are in the same directory or in the Python path
try:
    from communication.crypto import encrypt_message, decrypt_message
    from communication.nonce_manager import update_nonce_from_message
    from utils.db_utils import get_latest_derived_key
except ImportError:
    print("Error importing required modules. Make sure the encrypted transceiver modules are in your Python path.")
    print("Required modules: crypto.py, nonce_manager.py, db_utils.py")
    sys.exit(1)

# Global variables for latency measurements
latency_measurements = []
test_complete = threading.Event()
message_count = 0
message_success = 0
message_failed = 0

# Create a mock key for testing if the database isn't available
def create_test_key():
    return binascii.unhexlify('0123456789abcdef0123456789abcdef')  # 16-byte key for AES-128

class LatencyReceiver:
    def __init__(self, port, baud, identity, sender_identity):
        self.port = port
        self.baud = baud
        self.identity = identity
        self.sender_identity = sender_identity
        self.current_nonce = 0
        self.last_received_nonce = 0
        self.ser = None
        self.key = get_latest_derived_key(identity) or create_test_key()
        self.running = False
        self.buffer = b""
        
    def start(self):
        """Start the receiver thread"""
        self.running = True
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"[RECEIVER] Connected to {self.port} at {self.baud} baud")
            
            # Start the receiver thread
            self.thread = threading.Thread(target=self.receive_loop)
            self.thread.daemon = True
            self.thread.start()
            return True
        except serial.SerialException as e:
            print(f"[RECEIVER] Error opening serial port {self.port}: {e}")
            return False
    
    def stop(self):
        """Stop the receiver thread"""
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=2.0)
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"[RECEIVER] {self.port} connection closed")
    
    def receive_loop(self):
        """Main receiving loop"""
        while self.running:
            try:
                # Process incoming data
                if self.ser.in_waiting > 0:
                    new_data = self.ser.read(self.ser.in_waiting)
                    self.buffer += new_data
                    
                    # Look for complete messages (ending with newline)
                    while b'\n' in self.buffer:
                        line, self.buffer = self.buffer.split(b'\n', 1)
                        
                        # Decode line
                        line_str = line.decode('utf-8', errors='replace').strip()
                        
                        # Check if it's a direct encrypted message (format ID 2)
                        if line_str.startswith("2,"):
                            encrypted_hex = line_str[2:]  # Skip the '2,' prefix
                            self.process_received_message(encrypted_hex)
                
                # Prevent buffer overflow
                if len(self.buffer) > 10000:
                    print("[RECEIVER] Buffer too large, clearing...")
                    self.buffer = b""
                
                time.sleep(0.001)  # Small delay to prevent CPU hogging
                
            except Exception as e:
                print(f"[RECEIVER] Error in receive loop: {e}")
    
    def process_received_message(self, encrypted_hex):
        """Process a received encrypted message and measure latency"""
        global message_count, message_success, message_failed
        
        try:
            # Decrypt the message
            decrypted_json = decrypt_message(encrypted_hex, self.key)
            if decrypted_json is None:
                print("[RECEIVER] Decryption Failed!")
                message_failed += 1
                return
            
            # Parse the JSON
            message = json.loads(decrypted_json)
            
            # Extract fields
            sender = message.get("n", "unknown")
            command = message.get("c", "unknown")
            data = message.get("d", "")
            nonce = message.get("t", 0)
            
            # Only process messages from our sender
            if sender != self.sender_identity:
                return
                
            # Update nonce
            self.current_nonce, self.last_received_nonce = update_nonce_from_message(
                nonce, self.current_nonce, self.last_received_nonce
            )
            
            # Check if this is a test message
            if command == "test" and isinstance(data, str) and ":" in data:
                # Extract timestamp and calculate latency
                try:
                    send_time, msg_id = data.split(":", 1)
                    send_time = float(send_time)
                    receive_time = time.time()
                    latency = (receive_time - send_time) * 1000  # Convert to milliseconds
                    
                    # Record the latency
                    latency_measurements.append(latency)
                    message_success += 1
                    
                    if len(latency_measurements) % 10 == 0:
                        print(f"[RECEIVER] Received {len(latency_measurements)} messages, "
                              f"latest latency: {latency:.2f} ms")
                    
                    # Send acknowledgment if required
                    # Not implemented for basic test
                    
                except ValueError:
                    print(f"[RECEIVER] Invalid timestamp format in message: {data}")
            
        except json.JSONDecodeError:
            print("[RECEIVER] Invalid JSON data in decrypted message")
            message_failed += 1
        except Exception as e:
            print(f"[RECEIVER] Error processing message: {e}")
            message_failed += 1

class LatencySender:
    def __init__(self, port, baud, identity, num_messages=100, message_size=32):
        self.port = port
        self.baud = baud
        self.identity = identity
        self.current_nonce = 0
        self.ser = None
        self.key = get_latest_derived_key(identity) or create_test_key()
        self.num_messages = num_messages
        self.message_size = message_size
    
    def start(self):
        """Connect to the serial port"""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=1)
            print(f"[SENDER] Connected to {self.port} at {self.baud} baud")
            return True
        except serial.SerialException as e:
            print(f"[SENDER] Error opening serial port {self.port}: {e}")
            return False
    
    def stop(self):
        """Close the serial connection"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"[SENDER] {self.port} connection closed")
    
    def send_test_messages(self, delay=0.1):
        """Send a batch of test messages with the specified delay"""
        global message_count
        
        print(f"[SENDER] Starting to send {self.num_messages} messages with {delay:.3f}s delay")
        
        for i in range(self.num_messages):
            # Generate test message with timestamp
            timestamp = time.time()
            # Create message with timestamp and padding to reach desired size
            msg_id = f"{i+1:05d}"
            base_content = f"{timestamp}:{msg_id}"
            padding = "X" * (self.message_size - len(base_content))
            data = base_content + padding
            
            success = self.send_encrypted_message("test", data)
            if success:
                message_count += 1
            
            if (i+1) % 10 == 0:
                print(f"[SENDER] Sent {i+1}/{self.num_messages} messages")
            
            # Wait between messages
            time.sleep(delay)
        
        # Allow time for last messages to be received
        print("[SENDER] Finished sending messages, waiting for processing to complete...")
        time.sleep(1.0)
        test_complete.set()
    
    def send_encrypted_message(self, command, data):
        """Send an encrypted message to the serial port"""
        if self.key is None:
            print("[SENDER] Cannot send message: No encryption key available")
            return False
        
        # Create the message JSON
        message = {
            "n": self.identity,  # sender's name
            "c": command,        # command
            "d": data            # data
        }
        
        # Convert to JSON string
        message_json = json.dumps(message)
        
        # Encrypt the message
        encrypted_hex, new_nonce = encrypt_message(message_json, self.key, self.current_nonce)
        if encrypted_hex is None:
            print("[SENDER] Failed to encrypt message")
            return False
        
        # Update nonce
        self.current_nonce = new_nonce
        
        # Format for serial transmission (format ID 2 for encrypted data)
        serial_msg = f"2,{encrypted_hex}\n"
        
        # Send to serial port
        self.ser.write(serial_msg.encode('utf-8'))
        self.ser.flush()
        
        return True

def print_statistics():
    """Print statistics about the latency test"""
    if not latency_measurements:
        print("\nNo measurements recorded!")
        return
    
    # Calculate statistics
    min_latency = min(latency_measurements)
    max_latency = max(latency_measurements)
    avg_latency = sum(latency_measurements) / len(latency_measurements)
    median_latency = statistics.median(latency_measurements)
    
    # Calculate percentiles
    p90 = sorted(latency_measurements)[int(len(latency_measurements) * 0.9)]
    p95 = sorted(latency_measurements)[int(len(latency_measurements) * 0.95)]
    p99 = sorted(latency_measurements)[int(len(latency_measurements) * 0.99)]
    
    # Calculate standard deviation if we have enough measurements
    if len(latency_measurements) > 1:
        std_dev = statistics.stdev(latency_measurements)
    else:
        std_dev = 0
    
    # Print results
    print("\n--- LATENCY TEST RESULTS ---")
    print(f"Messages sent:     {message_count}")
    print(f"Messages received: {message_success}")
    print(f"Messages failed:   {message_failed}")
    print(f"Success rate:      {message_success/message_count*100:.2f}% if {message_count} > 0 else 0")
    print("\n--- LATENCY STATISTICS (milliseconds) ---")
    print(f"Minimum:    {min_latency:.2f} ms")
    print(f"Maximum:    {max_latency:.2f} ms")
    print(f"Average:    {avg_latency:.2f} ms")
    print(f"Median:     {median_latency:.2f} ms")
    print(f"Std Dev:    {std_dev:.2f} ms")
    print(f"90th %-ile: {p90:.2f} ms")
    print(f"95th %-ile: {p95:.2f} ms")
    print(f"99th %-ile: {p99:.2f} ms")
    
    # Create timestamp for log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"latency_test_{timestamp}.csv"
    
    # Save measurements to CSV file
    with open(log_filename, 'w') as f:
        f.write("measurement_index,latency_ms\n")
        for i, latency in enumerate(latency_measurements):
            f.write(f"{i+1},{latency:.6f}\n")
    
    print(f"\nLatency measurements saved to {log_filename}")

def main():
    parser = argparse.ArgumentParser(description='Test latency between two COM ports using the encrypted transceiver')
    parser.add_argument('--sender-port', default='COM13', help='Sender COM port')
    parser.add_argument('--receiver-port', default='COM14', help='Receiver COM port')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate for both ports')
    parser.add_argument('--sender-id', default='BCM', help='Sender identity')
    parser.add_argument('--receiver-id', default='PCM', help='Receiver identity')
    parser.add_argument('--messages', type=int, default=100, help='Number of messages to send')
    parser.add_argument('--size', type=int, default=32, help='Message size in bytes')
    parser.add_argument('--delay', type=float, default=0.1, help='Delay between messages in seconds')
    args = parser.parse_args()
    
    print(f"=== Encrypted Transceiver Latency Test ===")
    print(f"Testing latency between {args.sender_port} and {args.receiver_port}")
    print(f"Sending {args.messages} messages of size {args.size} bytes with {args.delay:.3f}s delay")
    
    # Create and start receiver
    receiver = LatencyReceiver(args.receiver_port, args.baud, args.receiver_id, args.sender_id)
    if not receiver.start():
        print("Failed to start receiver. Exiting.")
        return
    
    # Create and start sender
    sender = LatencySender(args.sender_port, args.baud, args.sender_id, args.messages, args.size)
    if not sender.start():
        print("Failed to start sender. Exiting.")
        receiver.stop()
        return
    
    try:
        # Wait a moment for receiver to fully start
        time.sleep(1.0)
        
        # Start sending test messages
        sender_thread = threading.Thread(target=sender.send_test_messages, args=(args.delay,))
        sender_thread.start()
        
        # Wait for test to complete or timeout
        test_complete.wait(timeout=args.messages * args.delay * 2 + 10)
        
        # Print statistics
        print_statistics()
        
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
    finally:
        # Stop the sender and receiver
        sender.stop()
        receiver.stop()
        
        # Make sure the sender thread is done
        if 'sender_thread' in locals() and sender_thread.is_alive():
            sender_thread.join(timeout=2.0)

if __name__ == "__main__":
    main()