# messaging.py
# Messaging module for Burmester-Desmedt Key Exchange.
# Handles serial communication, message processing, and retry logic.

import json
import time
import binascii
import re
import config
from key_exchange import key_exchange
from key_exchange import utils

def send_json_response(ser, node, command, data, is_retry=False):
    response = {
        "n": node,
        "c": command,
        "d": str(data)
    }
    response_json = json.dumps(response)
    
    if is_retry:
        print(f"Retrying message (attempt {config.retry_count + 1}): {response_json}")
        config.retry_count += 1
    else:
        print(f"Sending response: {response_json}")
        config.retry_count = 0
    
    config.last_sent_message = response
    config.last_sent_time = time.time()
    
    time.sleep(0.1)
    ser.write(b'2,' + response_json.encode('utf-8'))
    ser.write(b'\n')
    ser.flush()

def check_and_handle_retries(ser):
    if not utils.should_retry_message() or config.last_sent_message is None:
        return
        
    command = config.last_sent_message["c"]
    node = config.last_sent_message["n"]
    
    if command == "ker":
        missing_responses = set(config.PARTICIPANTS) - set(config.public_keys.keys())
        if missing_responses and missing_responses != {config.IDENTITY}:
            print(f"Missing responses from: {missing_responses}")
            send_json_response(ser, node, command, config.last_sent_message["d"], is_retry=True)
    
    elif command in ["kes1", "kes2"]:
        next_expected = utils.get_next_expected_participant(config.IDENTITY, config.key_exchange_requester)
        
        if command == "kes1":
            if next_expected not in config.public_keys:
                print(f"No response from next participant {next_expected}, retrying our message")
                send_json_response(ser, node, command, config.last_sent_message["d"], is_retry=True)
        
        elif command == "kes2":
            if next_expected not in config.t_values:
                print(f"No T-value from next participant {next_expected}, retrying our message")
                send_json_response(ser, node, command, config.last_sent_message["d"], is_retry=True)

def start_key_exchange(ser):
    print("\nInitiating key exchange as VSM...")
    
    key_exchange.reset_key_exchange_state()
    utils.reset_retry_state()
    
    config.key_exchange_requester = config.IDENTITY
    
    key_exchange.gen_private_key()
    key_exchange.gen_public_key()
    
    send_json_response(ser, config.IDENTITY, "ker", config.public_key)

def stage_1(ser, requester):
    print(f"Starting stage 1 key exchange, requester: {requester}")
    
    config.key_exchange_requester = requester
    
    key_exchange.gen_private_key()
    key_exchange.gen_public_key()
    
    requester_idx = config.PARTICIPANTS.index(requester)
    my_idx = config.PARTICIPANTS.index(config.IDENTITY)
    position = (my_idx - requester_idx) % len(config.PARTICIPANTS)
    
    print(f"Our position in the ring: {position}")
    
    if position == 0:
        return
    elif position == 1:
        print("We are first after requester, sending our key")
        send_json_response(ser, config.IDENTITY, "kes1", config.public_key)
    else:
        prev_participant = utils.get_prev_participant_relative_to_requester(config.IDENTITY, requester)
        print(f"We are in position {position}, waiting for {prev_participant} to send their public key before sending ours")

def handle_stage_2_trigger(ser):
    external_participants = set(config.PARTICIPANTS) - {config.IDENTITY}
    all_external_keys_received = all(p in config.public_keys for p in external_participants)
    
    if all_external_keys_received:
        print(f"All public keys collected from external participants: {list(config.public_keys.keys())}")
        
        if config.IDENTITY == config.key_exchange_requester:
            print("We are the requester, sending T-value first")
            stage_2(ser, config.key_exchange_requester)
        else:
            prev_participant = utils.get_prev_participant_relative_to_requester(config.IDENTITY, config.key_exchange_requester)
            print(f"Waiting for {prev_participant} to send their T-value before sending ours")
    else:
        missing = [p for p in external_participants if p not in config.public_keys]
        print(f"Not all public keys collected yet. Missing keys from: {missing}")

def stage_2(ser, requester):
    print(f"Starting stage 2 key exchange, requester: {requester}")
    
    if len(config.public_keys) < len(config.PARTICIPANTS):
        print(f"Cannot start stage 2: missing public keys. Have {len(config.public_keys)}/{len(config.PARTICIPANTS)}")
        return
    
    next_participant = utils.get_next_participant(config.IDENTITY)
    if next_participant not in config.public_keys:
        print(f"Cannot compute t value: missing public key for {next_participant}")
        return
    
    key_exchange.compute_t_value(config.public_keys[next_participant])
    
    send_json_response(ser, config.IDENTITY, "kes2", config.t_value)
    
    print(f"T-value sent. T-values collected so far: {list(config.t_values.keys())}")
    
    if len(config.t_values) == len(config.PARTICIPANTS):
        key_exchange.compute_shared_key()

def process_message(json_data, ser):
    try:
        if all(key in json_data for key in ["n", "c", "d"]):
            node = json_data["n"]
            command = json_data["c"]
            data = json_data["d"]
            
            print(f"Received message from {node}, command: {command}")
            
            if command == "ker":
                print(f"Received key exchange request from {node}")
                
                key_exchange.reset_key_exchange_state()
                utils.reset_retry_state()

                try:
                    requester_public_key = int(data)
                    config.public_keys[node] = requester_public_key
                    print(f"Stored {node} public key: {requester_public_key}")
                    
                    stage_1(ser, node)
                except ValueError as e:
                    print(f"Error processing public key: {e}")
            
            elif command == "kes1":
                print(f"Received stage 1 key from {node}")
                
                if config.key_exchange_requester is None:
                    print(f"Ignoring kes1: no key exchange in progress")
                    return
                    
                if node == config.key_exchange_requester:
                    print(f"Ignoring kes1 from requester {node} (should only send ker)")
                    return
                
                requester_idx = config.PARTICIPANTS.index(config.key_exchange_requester)
                sender_idx = config.PARTICIPANTS.index(node)
                sender_position = (sender_idx - requester_idx) % len(config.PARTICIPANTS)
                
                my_idx = config.PARTICIPANTS.index(config.IDENTITY)
                my_position = (my_idx - requester_idx) % len(config.PARTICIPANTS)
                
                print(f"Sender {node} position: {sender_position}, Our position: {my_position}")
                
                try:
                    other_public_key = int(data)
                    config.public_keys[node] = other_public_key
                    print(f"Stored {node} public key: {other_public_key}")
                    print(f"Public keys collected: {list(config.public_keys.keys())}")
                    
                    key_sent = False
                    
                    if my_position != 0:
                        if my_position == 1 and sender_position == 0:
                            print("We are first after requester, sending our key")
                            send_json_response(ser, config.IDENTITY, "kes1", config.public_key)
                            key_sent = True
                        elif my_position > 1 and sender_position == my_position - 1:
                            print(f"Previous participant {node} has sent their key, now sending ours")
                            send_json_response(ser, config.IDENTITY, "kes1", config.public_key)
                            key_sent = True
                    
                    external_participants = set(config.PARTICIPANTS) - {config.IDENTITY}
                    all_external_keys_received = all(p in config.public_keys for p in external_participants)
                    
                    if all_external_keys_received:
                        if my_position == 0 or key_sent:
                            print(f"Received all public keys from all participants and sent our own.")
                            handle_stage_2_trigger(ser)
                        else:
                            print(f"Have all external keys but haven't sent our key yet. Waiting for our turn.")
                except ValueError as e:
                    print(f"Error processing public key: {e}")
            
            elif command == "kes2":
                print(f"Received stage 2 key (t value) from {node}")
                
                external_participants = set(config.PARTICIPANTS) - {config.IDENTITY}
                all_external_keys_received = all(p in config.public_keys for p in external_participants)
                
                if not all_external_keys_received:
                    print(f"Ignoring premature kes2: stage 1 not complete with external participants")
                    return
                    
                requester_idx = config.PARTICIPANTS.index(config.key_exchange_requester)
                sender_idx = config.PARTICIPANTS.index(node)
                sender_position = (sender_idx - requester_idx) % len(config.PARTICIPANTS)
                my_idx = config.PARTICIPANTS.index(config.IDENTITY)
                my_position = (my_idx - requester_idx) % len(config.PARTICIPANTS)
                
                try:
                    other_t_value = int(data)
                    config.t_values[node] = other_t_value
                    print(f"Stored {node} t value: {other_t_value}")
                    print(f"T-values collected: {list(config.t_values.keys())}")
                    
                    t_value_sent = config.IDENTITY in config.t_values
                    
                    if not t_value_sent:
                        if my_position == 0:
                            print("We are the requester, sending T-value first")
                            stage_2(ser, config.key_exchange_requester)
                            t_value_sent = True
                        elif my_position == 1 and node == config.key_exchange_requester:
                            print(f"Received T-value from requester, sending our T-value")
                            stage_2(ser, config.key_exchange_requester)
                            t_value_sent = True
                        elif my_position > 1 and sender_position == my_position - 1:
                            print(f"Previous participant {node} has sent their T-value, now sending ours")
                            stage_2(ser, config.key_exchange_requester)
                            t_value_sent = True
                    
                    all_external_t_values = all(p in config.t_values for p in external_participants)
                    if all_external_t_values and t_value_sent:
                        print(f"Have all T-values and sent our own. Computing shared key.")
                        key_exchange.compute_shared_key()
                except ValueError as e:
                    print(f"Error processing t value: {e}")

        elif all(key in json_data for key in ["pgn", "sender", "data"]):
            try:
                pgn = json_data.get('pgn', 'unknown')
                sender = json_data.get('sender', 'unknown')
                hex_data = json_data.get('data', '')
                
                hex_data = ''.join(c for c in hex_data if c.lower() in '0123456789abcdef')
                
                if len(hex_data) % 2 != 0:
                    hex_data = hex_data.rjust(len(hex_data) + 1, '0')
                
                data_bytes = binascii.unhexlify(hex_data)
                
                ascii_text = data_bytes.decode('ascii', errors='replace')
                
                print(f"Message from sender {sender}, PGN: {pgn}")
                print(f"Decoded data: '{ascii_text}'")
                
                try:
                    inner_json = json.loads(ascii_text)
                    process_message(inner_json, ser)
                except json.JSONDecodeError:
                    print(f"Decoded data is not valid JSON: {ascii_text}")
            except binascii.Error as e:
                print(f"Invalid hex data: {hex_data[:30]}..., Error: {e}")
            except UnicodeDecodeError as e:
                print(f"Cannot decode as ASCII: {data_bytes[:30]}..., Error: {e}")
        else:
            print(f"Message does not contain required fields: {json_data}")
    except Exception as e:
        print(f"Error processing message: {e}")