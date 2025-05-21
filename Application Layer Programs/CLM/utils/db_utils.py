# db_utils.py
# Database utility functions for key retrieval and management.

import sqlite3

def get_latest_derived_key(identity):
    try:
        conn = sqlite3.connect(f'key_exchange_{identity}.db')
        c = conn.cursor()
        
        c.execute('''SELECT derived_key 
                    FROM key_exchange_sessions 
                    WHERE derived_key IS NOT NULL 
                    ORDER BY timestamp DESC LIMIT 1''')
        
        result = c.fetchone()
        conn.close()
        
        if result is None:
            print("No derived key found in database!")
            return None
            
        key_bytes = bytes.fromhex(result[0])
        
        return key_bytes[:16]
        
    except Exception as e:
        print(f"Error retrieving derived key: {e}")
        return None

def get_key_exchange_history(identity, limit=5):
    try:
        conn = sqlite3.connect(f'key_exchange_{identity}.db')
        c = conn.cursor()
        
        c.execute('''SELECT session_id, timestamp, requester, derived_key 
                    FROM key_exchange_sessions 
                    WHERE derived_key IS NOT NULL 
                    ORDER BY timestamp DESC LIMIT ?''', (limit,))
        
        results = c.fetchall()
        conn.close()
        
        return results
    except Exception as e:
        print(f"Error retrieving key exchange history: {e}")
        return []