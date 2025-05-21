# loopback_latency_test.py
# Script to test latency using loopback devices between two COM ports

import serial
import time
import argparse
import threading
import statistics
from datetime import datetime
import sys

def create_virtual_com_pair():
    """
    Information about creating a virtual COM port pair for testing
    This function doesn't actually create the ports, just prints instructions
    """
    print("This script requires two COM ports that are connected to each other.")
    print("For testing on a single computer, you can create a virtual COM port pair:")
    print("\n1. Using com0com (Windows):")
    print("   - Download from: https://sourceforge.net/projects/com0com/")
    print("   - Install and use the setup tool to create a pair (e.g., COM13 and COM14)")
    print("\n2. Using socat (Linux):")
    print("   - Install socat: sudo apt-get install socat")
    print("   - Create virtual ports: socat -d -d pty,raw,echo=0,link=/dev/ttyS13 pty,raw,echo=0,link=/dev/ttyS14")
    print("\n3. Using virtual serial port emulator software")
    
    print("\nEnsure your virtual COM ports are properly set up before running this test.")

class LoopbackLatencyTest:
    def __init__(self, port1, port2, baud=115200, num_messages=100, message_size=32, delay=0.1):
        self.port1 = port1
        self.port2 = port2
        self.baud = baud
        self.num_messages = num_messages
        self.message_size = message_size
        self.delay = delay
        self.ser1 = None
        self.ser2 = None
        self.running = False
        self.latency_measurements = []
        self.message_count = 0
        self.message_received = 0
        
    def start(self):
        """Connect to both serial ports"""
        try:
            self.ser1 = serial.Serial(self.port1, self.baud, timeout=1)
            print(f"Connected to {self.port1} at {self.baud} baud (sender)")
            
            self.ser2 = serial.Serial(self.port2, self.baud, timeout=1)
            print(f"Connected to {self.port2} at {self.baud} baud (receiver)")
            
            # Clear any data in the buffers
            self.ser1.reset_input_buffer()
            self.ser1.reset_output_buffer()
            self.ser2.reset_input_buffer()
            self.ser2.reset_output_buffer()
            
            return True
        except serial.SerialException as e:
            print(f"Error opening serial ports: {e}")
            if self.ser1:
                self.ser1.close()
            if self.ser2:
                self.ser2.close()
            return False
    
    def stop(self):
        """Close the serial connections"""
        self.running = False
        if self.ser1:
            self.ser1.close()
        if self.ser2:
            self.ser2.close()
        print("Serial connections closed")
    
    def receiver_thread(self):
        """Thread for receiving messages and measuring latency"""
        buffer = b""
        
        while self.running:
            try:
                # Check for data
                if self.ser2.in_waiting > 0:
                    # Read data
                    data = self.ser2.read(self.ser2.in_waiting)
                    buffer += data
                    
                    # Process complete messages (ending with newline)
                    while b'\n' in buffer:
                        message, buffer = buffer.split(b'\n', 1)
                        
                        # Process the message
                        try:
                            # Decode the message
                            message_str = message.decode('utf-8').strip()
                            
                            # Check if it's a test message with timestamp
                            if message_str.startswith("TEST:"):
                                # Extract timestamp and calculate latency
                                parts = message_str.split(":", 2)
                                if len(parts) >= 3:
                                    send_timestamp = float(parts[1])
                                    receive_timestamp = time.time()
                                    latency = (receive_timestamp - send_timestamp) * 1000  # ms
                                    
                                    # Record the latency
                                    self.latency_measurements.append(latency)
                                    self.message_received += 1
                                    
                                    # Print progress occasionally
                                    if self.message_received % 10 == 0 or self.message_received == 1:
                                        print(f"Received message {self.message_received}/{self.num_messages}, "
                                              f"latency: {latency:.2f} ms")
                        except Exception as e:
                            print(f"Error processing message: {e}")
                
                # Prevent buffer overflow
                if len(buffer) > 10000:
                    print("Buffer too large, clearing...")
                    buffer = b""
                
                time.sleep(0.001)  # Small delay to prevent CPU hogging
                
            except Exception as e:
                print(f"Error in receiver thread: {e}")
                time.sleep(0.1)
    
    def run_test(self):
        """Run the latency test"""
        self.running = True
        
        # Start the receiver thread
        receiver = threading.Thread(target=self.receiver_thread)
        receiver.daemon = True
        receiver.start()
        
        # Wait a moment for the receiver to start
        time.sleep(0.5)
        
        print(f"Starting latency test: sending {self.num_messages} messages...")
        
        try:
            # Send test messages
            for i in range(self.num_messages):
                # Create test message with timestamp
                timestamp = time.time()
                message_id = f"{i+1:05d}"
                base_message = f"TEST:{timestamp}:{message_id}"
                
                # Add padding to reach desired message size
                padding = "X" * (self.message_size - len(base_message) - 1)  # -1 for newline
                message = f"{base_message}{padding}\n"
                
                # Send the message
                self.ser1.write(message.encode('utf-8'))
                self.ser1.flush()
                self.message_count += 1
                
                # Wait between messages
                time.sleep(self.delay)
            
            # Wait for all messages to be processed
            print("Finished sending, waiting for processing to complete...")
            wait_time = min(5.0, self.delay * self.num_messages * 0.2)  # Wait proportional to the test time
            time.sleep(wait_time)
            
            # Stop the test
            self.running = False
            receiver.join(timeout=2.0)
            
            # Print statistics
            self.print_statistics()
            
        except KeyboardInterrupt:
            print("\nTest interrupted by user")
            self.running = False
            receiver.join(timeout=2.0)
        except Exception as e:
            print(f"Error during test: {e}")
        finally:
            self.stop()
    
    def print_statistics(self):
        """Print statistics about the latency test"""
        if not self.latency_measurements:
            print("\nNo measurements recorded!")
            return
        
        # Calculate statistics
        min_latency = min(self.latency_measurements)
        max_latency = max(self.latency_measurements)
        avg_latency = sum(self.latency_measurements) / len(self.latency_measurements)
        median_latency = statistics.median(self.latency_measurements)
        
        # Calculate percentiles
        p90 = sorted(self.latency_measurements)[int(len(self.latency_measurements) * 0.9)]
        p95 = sorted(self.latency_measurements)[int(len(self.latency_measurements) * 0.95)]
        p99 = sorted(self.latency_measurements)[int(len(self.latency_measurements) * 0.99)]
        
        # Calculate standard deviation if we have enough measurements
        if len(self.latency_measurements) > 1:
            std_dev = statistics.stdev(self.latency_measurements)
        else:
            std_dev = 0
        
        # Print results
        print("\n--- LOOPBACK LATENCY TEST RESULTS ---")
        print(f"Messages sent:     {self.message_count}")
        print(f"Messages received: {self.message_received}")
        print(f"Success rate:      {self.message_received/self.message_count*100:.2f}% if self.message_count > 0 else 0")
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
        log_filename = f"loopback_latency_{timestamp}.csv"
        
        # Save measurements to CSV file
        with open(log_filename, 'w') as f:
            f.write("measurement_index,latency_ms\n")
            for i, latency in enumerate(self.latency_measurements):
                f.write(f"{i+1},{latency:.6f}\n")
        
        print(f"\nLatency measurements saved to {log_filename}")

def main():
    parser = argparse.ArgumentParser(description='Test latency between two COM ports using loopback')
    parser.add_argument('--port1', default='COM13', help='First COM port (sender)')
    parser.add_argument('--port2', default='COM14', help='Second COM port (receiver)')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate for both ports')
    parser.add_argument('--messages', type=int, default=100, help='Number of messages to send')
    parser.add_argument('--size', type=int, default=32, help='Message size in bytes')
    parser.add_argument('--delay', type=float, default=0.1, help='Delay between messages in seconds')
    parser.add_argument('--info', action='store_true', help='Show information about setting up virtual COM ports')
    args = parser.parse_args()
    
    if args.info:
        create_virtual_com_pair()
        return
    
    print(f"=== Serial Port Loopback Latency Test ===")
    print(f"Testing latency between {args.port1} (sender) and {args.port2} (receiver)")
    print(f"Baud rate: {args.baud}")
    print(f"Sending {args.messages} messages of size {args.size} bytes with {args.delay:.3f}s delay")
    
    test = LoopbackLatencyTest(
        args.port1, args.port2, args.baud, 
        args.messages, args.size, args.delay
    )
    
    if test.start():
        test.run_test()
    else:
        print("Failed to start the test. Make sure both COM ports are available.")
        print("Run with --info for information about setting up virtual COM ports.")

if __name__ == "__main__":
    main()