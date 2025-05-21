# analyzer.py
# Functions for analyzing and processing data formats
import binascii

def analyze_hex_data(hex_data):
    valid_hex = all(c in '0123456789abcdefABCDEF' for c in hex_data)
    print(f"Is valid hex: {valid_hex}")
    
    try:
        cleaned_hex = ''.join(c for c in hex_data if c.lower() in '0123456789abcdef')
        if len(cleaned_hex) % 2 != 0:
            cleaned_hex = '0' + cleaned_hex
            
        data_bytes = bytes.fromhex(cleaned_hex)
        print(f"Converted to bytes (length: {len(data_bytes)})")
        
        printable_bytes = sum(32 <= b <= 126 for b in data_bytes)
        ascii_percent = printable_bytes/len(data_bytes)*100 if data_bytes else 0
        
        if ascii_percent > 75:
            print("Data appears to be ASCII text")
        else:
            print("Data appears to be binary")
        
    except Exception as e:
        print(f"Analysis error: {e}")
    
    return