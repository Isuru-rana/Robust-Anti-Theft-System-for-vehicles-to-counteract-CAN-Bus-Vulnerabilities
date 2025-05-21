# database.py
# Database operations for Burmester-Desmedt Key Exchange.

import sqlite3
import hashlib
from datetime import datetime
import config

def get_derived_key(session_id=None):
    conn = sqlite3.connect(f'key_exchange_{config.IDENTITY}.db')
    c = conn.cursor()
    
    if session_id:
        c.execute('''SELECT derived_key 
                    FROM key_exchange_sessions 
                    WHERE session_id = ? AND derived_key IS NOT NULL''', (session_id,))
    else:
        c.execute('''SELECT derived_key 
                    FROM key_exchange_sessions 
                    WHERE derived_key IS NOT NULL 
                    ORDER BY timestamp DESC LIMIT 1''')
    
    result = c.fetchone()
    conn.close()
    
    if result:
        return bytes.fromhex(result[0])
    else:
        return None

def init_database():
    conn = sqlite3.connect(f'key_exchange_{config.IDENTITY}.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS key_exchange_sessions
                 (session_id TEXT PRIMARY KEY,
                  timestamp TEXT,
                  requester TEXT,
                  own_private_key TEXT,
                  own_public_key TEXT,
                  own_t_value TEXT,
                  shared_key TEXT,
                  derived_key TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS participant_keys
                 (session_id TEXT,
                  participant TEXT,
                  public_key TEXT,
                  t_value TEXT,
                  FOREIGN KEY(session_id) REFERENCES key_exchange_sessions(session_id),
                  PRIMARY KEY(session_id, participant))''')
    
    conn.commit()
    conn.close()
    print("Database initialized")

def generate_session_id():
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"{config.IDENTITY}_{timestamp}"

def save_session_data(session_id, requester):
    conn = sqlite3.connect(f'key_exchange_{config.IDENTITY}.db')
    c = conn.cursor()

    timestamp = datetime.now().isoformat()
    priv_key_str = str(config.private_key) if config.private_key is not None else None
    pub_key_str = str(config.public_key) if config.public_key is not None else None
    t_val_str = str(config.t_value) if config.t_value is not None else None
    shared_str = str(config.shared_key) if config.shared_key is not None else None
    
    derived_key_str = None
    if config.shared_key is not None:
        derived_key = hashlib.sha256(str(config.shared_key).encode()).digest()
        derived_key_str = derived_key.hex()
    
    c.execute('''INSERT OR REPLACE INTO key_exchange_sessions
                 (session_id, timestamp, requester, own_private_key, 
                  own_public_key, own_t_value, shared_key, derived_key)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                 (session_id, timestamp, requester, priv_key_str,
                  pub_key_str, t_val_str, shared_str, derived_key_str))
    
    for participant, pub_key in config.public_keys.items():
        if participant != config.IDENTITY:
            t_val = config.t_values.get(participant)
            c.execute('''INSERT OR REPLACE INTO participant_keys
                         (session_id, participant, public_key, t_value)
                         VALUES (?, ?, ?, ?)''',
                         (session_id, participant, str(pub_key),
                          str(t_val) if t_val is not None else None))
    
    conn.commit()
    conn.close()
    print(f"Session data saved to database (Session ID: {session_id})")

def display_database_contents():
    conn = sqlite3.connect(f'key_exchange_{config.IDENTITY}.db')
    c = conn.cursor()
    
    print("\n=== Database Contents ===")
    
    print("\nKey Exchange Sessions:")
    c.execute('''SELECT session_id, timestamp, requester, shared_key, derived_key 
                 FROM key_exchange_sessions ORDER BY timestamp DESC''')
    sessions = c.fetchall()
    for session in sessions:
        print(f"\nSession ID: {session[0]}")
        print(f"Timestamp: {session[1]}")
        print(f"Requester: {session[2]}")
        print(f"Shared Key: {session[3]}")
        print(f"Derived Key (SHA-256): {session[4]}")
        
        print("\nParticipant Keys:")
        c.execute('''SELECT participant, public_key, t_value 
                     FROM participant_keys WHERE session_id = ?''', (session[0],))
        participants = c.fetchall()
        for p in participants:
            print(f"{p[0]}: Public Key = {p[1]}, T-Value = {p[2]}")
    
    conn.close()