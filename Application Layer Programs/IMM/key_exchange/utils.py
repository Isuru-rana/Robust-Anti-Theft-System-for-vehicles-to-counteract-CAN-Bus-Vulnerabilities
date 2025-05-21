# utils.py
# Utility functions for Burmester-Desmedt Key Exchange.

import time
import config

def reset_retry_state():
    config.last_sent_message = None
    config.last_sent_time = None
    config.retry_count = 0

def should_retry_message():
    if config.last_sent_message is None or config.last_sent_time is None:
        return False
        
    current_time = time.time()
    if current_time - config.last_sent_time >= config.RETRY_TIMEOUT:
        if config.retry_count < config.MAX_RETRIES:
            return True
        else:
            print(f"Maximum retries ({config.MAX_RETRIES}) reached. Key exchange failed.")
            reset_retry_state()
            return False
    
    return False

def get_next_participant(current):
    idx = config.PARTICIPANTS.index(current)
    next_idx = (idx + 1) % len(config.PARTICIPANTS)
    return config.PARTICIPANTS[next_idx]

def get_prev_participant(current):
    idx = config.PARTICIPANTS.index(current)
    prev_idx = (idx - 1) % len(config.PARTICIPANTS)
    return config.PARTICIPANTS[prev_idx]

def get_prev_participant_relative_to_requester(current, requester):
    sequence = []
    temp = requester
    for _ in range(len(config.PARTICIPANTS)):
        sequence.append(temp)
        temp = get_next_participant(temp)
    
    current_idx = sequence.index(current)
    if current_idx == 0:
        return sequence[-1]
    return sequence[current_idx - 1]

def get_next_expected_participant(current_sender, requester):
    sequence = []
    temp = requester
    for _ in range(len(config.PARTICIPANTS)):
        sequence.append(temp)
        temp = get_next_participant(temp)
    
    try:
        current_idx = sequence.index(current_sender)
        next_idx = (current_idx + 1) % len(config.PARTICIPANTS)
        return sequence[next_idx]
    except ValueError:
        return None