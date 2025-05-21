# config.py
# Configuration module for Burmester-Desmedt secure communication.
# Contains constants and configuration variables.


# Device identity - Change this for each device 
IDENTITY = "KLE"

# Participants in the key exchange ring
PARTICIPANTS = ["CLM", "KLE", "IMM"]

# Retry mechanism configuration
MAX_RETRIES = 5  # Maximum number of retries before giving up
RETRY_TIMEOUT = 50.0  # Timeout in seconds before retry

# Diffie-Hellman parameters for the key exchange
MODP_1024_P = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A63A3620FFFFFFFFFFFFFFFF", 16
)
MODP_1024_G = 2

# Encryption parameters
AES_KEY_LENGTH = 16  # 128 bits (16 bytes)
USE_ENCRYPTION = True

# Operation modes
MODE_KEY_EXCHANGE = "key_exchange"  # Run key exchange protocol
MODE_TRANSCEIVER = "transceiver"    # Run encrypted transceiver
MODE_BOTH = "both"                  # Run both in sequence

# Default serial port settings
DEFAULT_PORT = "COM3"
DEFAULT_BAUD = 115200

# Global state variables
# These will be imported and modified by other modules
private_key = None
public_key = None
t_value = None
public_keys = {}
t_values = {}
shared_key = None
key_exchange_requester = None
current_session_id = None

# Retry state
last_sent_message = None
last_sent_time = None
retry_count = 0

# Nonce state
current_nonce = 0
last_received_nonce = 0