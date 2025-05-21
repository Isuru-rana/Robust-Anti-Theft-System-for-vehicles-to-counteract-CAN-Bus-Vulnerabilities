# engine_control_gui.py
import tkinter as tk
from tkinter import ttk, messagebox
import serial
import time
import json
import threading
import os
import sys
import paho.mqtt.client as mqtt
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.db_utils import get_latest_derived_key
from communication.crypto import encrypt_message
from communication.sender import send_encrypted_message
class EngineControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Engine Control Interface")
        self.root.geometry("600x400")
        self.root.resizable(False, False)
        try:
            self.root.iconbitmap("engine_icon.ico")
        except:
            pass
        self.engine_on = False
        self.doors_locked = False
        self.ser = None
        self.identity = "CLM"
        self.current_nonce = 0
        self.connected = False
        self.key = None
        self.mqtt_client = None
        self.mqtt_connected = False
        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except:
            pass
        main_frame = ttk.Frame(root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        conn_frame = ttk.LabelFrame(main_frame, text="Serial Connection", padding="10")
        conn_frame.pack(fill=tk.X, padx=20, pady=(20, 10))
        ttk.Label(conn_frame, text="Port:", width=8).grid(row=0, column=0, sticky=tk.W, padx=(5, 0), pady=5)
        self.port_var = tk.StringVar(value="COM3")
        self.port_entry = ttk.Entry(conn_frame, textvariable=self.port_var, width=10)
        self.port_entry.grid(row=0, column=1, sticky=tk.W, padx=(0, 20), pady=5)
        ttk.Label(conn_frame, text="Baud Rate:", width=10).grid(row=0, column=2, sticky=tk.W, padx=0, pady=5)
        self.baud_var = tk.IntVar(value=115200)
        self.baud_entry = ttk.Entry(conn_frame, textvariable=self.baud_var, width=10)
        self.baud_entry.grid(row=0, column=3, sticky=tk.W, padx=(0, 20), pady=5)
        self.connect_btn = ttk.Button(conn_frame, text="Connect", command=self.toggle_connection, width=10)
        self.connect_btn.grid(row=0, column=4, padx=0, pady=5)
        self.status_var = tk.StringVar(value="Disconnected")
        ttk.Label(conn_frame, text="Status:", width=8).grid(row=1, column=0, sticky=tk.W, padx=(5, 0), pady=5)
        self.status_label = ttk.Label(conn_frame, textvariable=self.status_var, foreground="red")
        self.status_label.grid(row=1, column=1, columnspan=4, sticky=tk.W, padx=0, pady=5)
        control_frame = ttk.LabelFrame(main_frame, text="Vehicle Control", padding="10")
        control_frame.pack(fill=tk.X, padx=20, pady=10)
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(fill=tk.X, pady=20)
        self.engine_btn = tk.Button(button_frame, text="ENGINE IGNITION",
                                  bg="white", fg="black",
                                  font=("Arial", 11, "bold"),
                                  relief=tk.RIDGE, bd=2,
                                  width=22, height=1,
                                  highlightbackground="red", highlightcolor="red", highlightthickness=2,
                                  command=self.toggle_engine)
        self.engine_btn.grid(row=0, column=0, padx=10, pady=10)
        self.doors_btn = tk.Button(button_frame, text="DOORS UNLOCK",
                                 bg="white", fg="black",
                                 font=("Arial", 11, "bold"),
                                 relief=tk.RIDGE, bd=2,
                                 width=22, height=1,
                                 highlightbackground="blue", highlightcolor="blue", highlightthickness=2,
                                 command=self.toggle_doors)
        self.doors_btn.grid(row=0, column=1, padx=10, pady=10)
        if not self.connected:
            self.engine_btn.config(state=tk.DISABLED)
            self.doors_btn.config(state=tk.DISABLED)
        self.status_bar = tk.Label(main_frame, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=(0, 10))
        self.setup_mqtt_client()
    def setup_mqtt_client(self):
        try:
            self.mqtt_client = mqtt.Client()
            self.mqtt_client.username_pw_set("mqtt_home", "Senaka123")
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            threading.Thread(target=self.connect_mqtt).start()
        except Exception:
            pass
    def connect_mqtt(self):
        try:
            self.mqtt_client.connect("iizo.duckdns.org", 1883, 60)
            self.mqtt_client.loop_start()
        except Exception:
            pass
    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.mqtt_connected = True
        else:
            self.mqtt_connected = False
    def on_mqtt_disconnect(self, client, userdata, rc):
        self.mqtt_connected = False
    def toggle_connection(self):
        if not self.connected:
            try:
                port = self.port_var.get()
                baud = self.baud_var.get()
                self.ser = serial.Serial(port, baud, timeout=1)
                self.connected = True
                self.key = get_latest_derived_key(self.identity)
                if self.key is None:
                    messagebox.showwarning("Key Error", "No encryption key available. Engine control will still work, but encrypted messages may fail.")
                else:
                    self.log(f"Loaded encryption key: {self.key.hex()[:10]}...")
                self.status_var.set("Connected")
                self.status_label.config(foreground="green")
                self.connect_btn.config(text="Disconnect")
                self.engine_btn.config(state=tk.NORMAL)
                self.doors_btn.config(state=tk.NORMAL)
                self.log(f"Connected to {port} at {baud} baud")
            except Exception as e:
                messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
                self.log(f"Connection error: {str(e)}")
        else:
            if self.ser and self.ser.is_open:
                self.ser.close()
            self.connected = False
            self.status_var.set("Disconnected")
            self.status_label.config(foreground="red")
            self.connect_btn.config(text="Connect")
            self.engine_btn.config(state=tk.DISABLED)
            self.doors_btn.config(state=tk.DISABLED)
            self.log("Disconnected from serial port")
    def toggle_engine(self):
        if not self.connected or not self.ser or not self.ser.is_open:
            messagebox.showerror("Error", "Not connected to serial port")
            return
        self.engine_on = not self.engine_on
        if self.engine_on:
            self.engine_btn.config(bg="green", fg="white",
                                  highlightbackground="green", highlightcolor="green")
            threading.Thread(target=self.send_engine_state_messages, args=("Engine ON", "Ignition ON")).start()
        else:
            self.engine_btn.config(bg="white", fg="black",
                                  highlightbackground="red", highlightcolor="red")
            threading.Thread(target=self.send_engine_state_messages, args=("Engine OFF", "Ignition OFF")).start()
    def toggle_doors(self):
        if not self.connected or not self.ser or not self.ser.is_open:
            messagebox.showerror("Error", "Not connected to serial port")
            return
        self.doors_locked = not self.doors_locked
        if self.doors_locked:
            self.doors_btn.config(bg="red", fg="white",
                                text="DOORS LOCK",
                                highlightbackground="red", highlightcolor="red")
            threading.Thread(target=self.send_door_state_messages, args=("DoorsLock", "doorslock")).start()
        else:
            self.doors_btn.config(bg="white", fg="black",
                                text="DOORS UNLOCK",
                                highlightbackground="blue", highlightcolor="blue")
            threading.Thread(target=self.send_door_state_messages, args=("DoorsUnlock", "doorsunlock")).start()
    def send_engine_state_messages(self, encrypted_msg, direct_msg):
        try:
            if self.key:
                success = self.send_encrypted_message(encrypted_msg)
                if success:
                    self.log(f"Sent encrypted message: {encrypted_msg}")
                else:
                    self.log(f"Failed to send encrypted message: {encrypted_msg}")
            else:
                self.log("No encryption key available, skipping encrypted message")
            time.sleep(0.01)
            self.send_direct_message(direct_msg)
            self.log(f"Sent direct message: {direct_msg}")
            time.sleep(1.0)
            mqtt_payload = "Engine_ON" if "ON" in encrypted_msg else "Engine_OFF"
            self.send_mqtt_message(mqtt_payload)
        except Exception as e:
            self.log(f"Error sending messages: {str(e)}")
            messagebox.showerror("Communication Error", f"Failed to send messages: {str(e)}")
    def send_door_state_messages(self, encrypted_msg, mqtt_payload):
        try:
            if self.key:
                success = self.send_encrypted_message(encrypted_msg)
                if success:
                    self.log(f"Sent encrypted door message: {encrypted_msg}")
                else:
                    self.log(f"Failed to send encrypted door message: {encrypted_msg}")
            else:
                self.log("No encryption key available, skipping encrypted message")
            time.sleep(1.0)
            self.send_mqtt_door_message(mqtt_payload)
        except Exception as e:
            self.log(f"Error sending door messages: {str(e)}")
            messagebox.showerror("Communication Error", f"Failed to send door messages: {str(e)}")
    def send_mqtt_message(self, payload):
        if not self.mqtt_connected:
            self.connect_mqtt()
            time.sleep(0.5)
        try:
            topic = "IMM/status/engine"
            self.mqtt_client.publish(topic, payload, qos=1)
            return True
        except Exception:
            return False
    def send_mqtt_door_message(self, payload):
        if not self.mqtt_connected:
            self.connect_mqtt()
            time.sleep(0.5)
        try:
            topic = "CLM/status/doors"
            self.mqtt_client.publish(topic, payload, qos=1)
            return True
        except Exception:
            return False
    def send_encrypted_message(self, data):
        if not self.key:
            return False
        try:
            message = {
                "n": self.identity,
                "c": "s",
                "d": data
            }
            message_json = json.dumps(message)
            encrypted_hex, new_nonce = encrypt_message(message_json, self.key, self.current_nonce)
            if encrypted_hex is None:
                return False
            self.current_nonce = new_nonce
            serial_msg = f"2,{encrypted_hex}\n"
            self.ser.write(serial_msg.encode('utf-8'))
            self.ser.flush()
            return True
        except Exception as e:
            self.log(f"Encryption error: {str(e)}")
            return False
    def send_direct_message(self, data):
        try:
            message = {
                "c": "np",
                "d": data
            }
            message_json = json.dumps(message)
            serial_msg = message_json + "\n"
            self.ser.write(serial_msg.encode('utf-8'))
            self.ser.flush()
            return True
        except Exception as e:
            self.log(f"Direct message error: {str(e)}")
            return False
    def log(self, message):
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        log_entry = f"[{timestamp}] {message}"
        self.status_bar.config(text=log_entry)
    def __del__(self):
        if hasattr(self, 'ser') and self.ser and self.ser.is_open:
            self.ser.close()
        if hasattr(self, 'mqtt_client') and self.mqtt_client:
            try:
                self.mqtt_client.loop_stop()
                self.mqtt_client.disconnect()
            except:
                pass
def main():
    root = tk.Tk()
    app = EngineControlGUI(root)
    root.mainloop()
if __name__ == "__main__":
    main()