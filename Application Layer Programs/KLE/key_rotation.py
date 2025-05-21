# key_rotation.py
# Module for handling automatic key rotation based on nonce thresholds

import time
import logging
import threading
from communication.nonce_manager import save_nonce_to_file
import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('key_rotation')

# Default threshold value - change this to control how often keys rotate
DEFAULT_NONCE_THRESHOLD = 10

# Global state variables
key_exchange_in_progress = False
key_exchange_timer = None

def check_nonce_threshold(current_nonce, last_received_nonce, identity, ser):
    """
    Check if the nonce value has reached or exceeded the threshold,
    and trigger key exchange if needed
    
    Args:
        current_nonce: The local device's current nonce value
        last_received_nonce: The highest nonce received from other devices
        identity: The local device's identity
        ser: The serial port object for communication
    
    Returns:
        tuple: (nonce_threshold_reached, should_initiate_exchange)
    """
    # Get threshold from config or use default
    threshold = getattr(config, 'NONCE_THRESHOLD', DEFAULT_NONCE_THRESHOLD)
    
    # Check if we've reached the threshold with our sent messages
    if current_nonce >= threshold:
        logger.info(f"Nonce threshold {threshold} reached with our sent messages (current_nonce={current_nonce})")
        return True, True
    
    # Check if we've received a message with nonce at or above threshold
    if last_received_nonce >= threshold:
        logger.info(f"Nonce threshold {threshold} reached via received message (last_received_nonce={last_received_nonce})")
        return True, False
    
    # Threshold not reached
    return False, False

def schedule_key_exchange(ser, delay=5.0):
    """
    Schedule a key exchange to occur after a delay
    
    Args:
        ser: The serial port object for communication
        delay: Delay in seconds before initiating key exchange
    """
    global key_exchange_timer, key_exchange_in_progress
    
    if key_exchange_in_progress:
        logger.info("Key exchange already in progress, not scheduling another one")
        return
    
    if key_exchange_timer is not None and key_exchange_timer.is_alive():
        logger.info("Key exchange already scheduled, not scheduling another one")
        return
    
    logger.info(f"Scheduling key exchange to occur in {delay} seconds")
    key_exchange_in_progress = True
    
    def initiate_exchange():
        try:
            logger.info("Initiating scheduled key exchange")
            from key_exchange.messaging import start_key_exchange
            
            # Reset nonce counters before starting key exchange
            config.current_nonce = 0
            config.last_received_nonce = 0
            save_nonce_to_file(config.IDENTITY, 0)
            
            # Start the key exchange process
            start_key_exchange(ser)
        except Exception as e:
            logger.error(f"Error initiating key exchange: {e}")
        finally:
            global key_exchange_in_progress
            key_exchange_in_progress = False
    
    # Create and start timer
    key_exchange_timer = threading.Timer(delay, initiate_exchange)
    key_exchange_timer.daemon = True
    key_exchange_timer.start()

def handle_nonce_threshold_check(ser, current_nonce, last_received_nonce, identity):
    """
    Handle checking and responding to nonce thresholds
    
    Args:
        ser: The serial port object
        current_nonce: Current local nonce value
        last_received_nonce: Highest received nonce value
        identity: This device's identity
        
    Returns:
        tuple: Updated (current_nonce, last_received_nonce)
    """
    # Check if we've reached a threshold
    threshold_reached, should_initiate = check_nonce_threshold(
        current_nonce, last_received_nonce, identity, ser
    )
    
    if threshold_reached:
        logger.info(f"Nonce threshold reached. Current nonce: {current_nonce}, Last received: {last_received_nonce}")
        
        if should_initiate:
            # We reached the threshold with our sent messages, so we should initiate exchange
            logger.info("We are the sender who hit the threshold, scheduling key exchange...")
            schedule_key_exchange(ser)
            
            # Notify other participants that we're going to initiate key exchange
            try:
                from communication.sender import send_notification
                send_notification(ser, identity, "key_rotation", "Nonce threshold reached, initiating key exchange", current_nonce)
            except Exception as e:
                logger.error(f"Error sending key rotation notification: {e}")
        else:
            # We received a message with nonce at/above threshold, wait for the sender to initiate
            logger.info("Received threshold message from another device, waiting for them to initiate key exchange...")
            
            # Log but don't increment nonce since we're about to reset it anyway
            try:
                from communication.sender import send_notification
                send_notification(
                    ser, identity, "key_rotation_ack",
                    f"Ready for key exchange from threshold initiator",
                    current_nonce, increment_nonce=False
                )
            except Exception as e:
                logger.error(f"Error sending key rotation acknowledgment: {e}")
    
    return current_nonce, last_received_nonce

def is_key_exchange_in_progress():
    """
    Check if a key exchange is currently in progress
    
    Returns:
        bool: True if key exchange is in progress, False otherwise
    """
    global key_exchange_in_progress
    return key_exchange_in_progress

def cancel_scheduled_key_exchange():
    """Cancel any scheduled key exchange"""
    global key_exchange_timer, key_exchange_in_progress
    
    if key_exchange_timer is not None and key_exchange_timer.is_alive():
        logger.info("Cancelling scheduled key exchange")
        key_exchange_timer.cancel()
    
    key_exchange_in_progress = False