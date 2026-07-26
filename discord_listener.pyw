import os
import sys
import time
import json
import queue
import threading
import psutil
import sounddevice as sd
import customtkinter as ctk
from vosk import Model, KaldiRecognizer, SetLogLevel
from thefuzz import fuzz

# --- Configuration & PyInstaller Pathing ---
SetLogLevel(-1)

# This block allows the script to find its files whether it's a .py script or a compiled .exe
if getattr(sys, 'frozen', False):
    # Running as a compiled .exe
    app_path = os.path.dirname(sys.executable)
    bundle_path = sys._MEIPASS # This is the secret temp folder where the .exe unpacks the model
else:
    # Running as a normal script
    app_path = os.path.dirname(os.path.abspath(__file__))
    bundle_path = app_path

# Force the working directory to where the .exe physically sits so phrases.txt saves next to it
os.chdir(app_path)

PHRASES_FILE = "phrases.txt"
MODEL_PATH = os.path.join(bundle_path, "model")

def load_phrases():
    if not os.path.exists(PHRASES_FILE):
        defaults = [
            "have you guys heard", "did you guys see", "have you guys seen", 
            "did you guys hear", "have you guys heard about", 
            "did you guys see that", "have you guys seen that"
        ]
        with open(PHRASES_FILE, "w") as f:
            f.write("\n".join(defaults))
        return defaults
    
    with open(PHRASES_FILE, "r") as f:
        return [line.strip().lower() for line in f if line.strip()]

TRIGGER_PHRASES = load_phrases()

# --- Utility Functions ---
audio_queue = queue.Queue()
is_running = True 

def clear_queue():
    with audio_queue.mutex:
        audio_queue.queue.clear()

def is_discord_running():
    return any('discord' in (p.info['name'] or '').lower() for p in psutil.process_iter(['name']))

def kill_discord():
    for p in psutil.process_iter(['name']):
        if 'discord' in (p.info['name'] or '').lower():
            try:
                p.kill()
            except psutil.AccessDenied:
                pass 

def audio_callback(indata, frames, time, status):
    if status:
        pass # Silenced the error printout for the final exe
    audio_queue.put(bytes(indata))

# --- Core Audio Loop ---
def listen_loop(app_gui):
    try:
        # Point to the dynamically located model folder
        recognizer = KaldiRecognizer(Model(MODEL_PATH), 16000)
    except Exception as e:
        app_gui.update_status(f"Error: {e}", "red")
        return

    was_running = False

    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16', channels=1, callback=audio_callback):
        while is_running:
            running = is_discord_running()
            
            if running and not was_running:
                clear_queue()
                    
            was_running = running
            
            if running:
                app_gui.update_status("Discord is open. Listening...", "#2ECC71")
                data = audio_queue.get()
                
                if recognizer.AcceptWaveform(data):
                    text = json.loads(recognizer.Result()).get("text", "").lower()
                    if text:
                        app_gui.update_log(f"Heard: '{text}'")
                        
                        for phrase in TRIGGER_PHRASES:
                            score = fuzz.partial_ratio(phrase, text)
                            if score >= 80:
                                app_gui.update_log(f"💥 Match! ({score}% similar to '{phrase}')\nClosing Discord...")
                                kill_discord()
                                clear_queue()
                                break 
            else:
                app_gui.update_status("Waiting for Discord to open...", "#F39C12")
                clear_queue()
                time.sleep(1)

# --- User Interface ---
class VoiceMonitorUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        self.title("Discord Escape Button")
        self.geometry("450x420")
        self.resizable(False, False)
        
        self.title_label = ctk.CTkLabel(self, text="Discord Voice Monitor", font=("Segoe UI", 22, "bold"))
        self.title_label.pack(pady=(20, 5))
        
        self.status_label = ctk.CTkLabel(self, text="Starting up...", font=("Segoe UI", 14), text_color="gray")
        self.status_label.pack(pady=5)
        
        self.log_box = ctk.CTkTextbox(self, width=400, height=140, state="disabled", font=("Consolas", 12))
        self.log_box.pack(pady=10)
        
        self.input_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.input_frame.pack(pady=5, padx=20, fill="x")
        
        self.phrase_entry = ctk.CTkEntry(self.input_frame, placeholder_text="Type a new trigger phrase here...")
        self.phrase_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.add_btn = ctk.CTkButton(self.input_frame, text="Add Phrase", width=80, command=self.add_new_phrase)
        self.add_btn.pack(side="right")
        
        self.stop_btn = ctk.CTkButton(self, text="Stop Monitoring & Exit", fg_color="#C0392B", hover_color="#922B21", command=self.close_app)
        self.stop_btn.pack(pady=15)
        
        self.update_log(f"Loaded {len(TRIGGER_PHRASES)} trigger phrases from file.")
        
        threading.Thread(target=listen_loop, args=(self,), daemon=True).start()

    def add_new_phrase(self):
        new_phrase = self.phrase_entry.get().strip().lower()
        if not new_phrase:
            return
            
        if new_phrase in TRIGGER_PHRASES:
            self.update_log(f"⚠️ You already added '{new_phrase}'!")
            self.phrase_entry.delete(0, "end")
            return
            
        TRIGGER_PHRASES.append(new_phrase)
        with open(PHRASES_FILE, "a") as f:
            f.write("\n" + new_phrase)
            
        self.update_log(f"➕ Saved new phrase: '{new_phrase}'")
        self.phrase_entry.delete(0, "end")

    def update_status(self, text, color):
        self.status_label.configure(text=text, text_color=color)

    def update_log(self, text):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end") 
        self.log_box.configure(state="disabled")

    def close_app(self):
        global is_running
        is_running = False
        self.destroy()

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    VoiceMonitorUI().mainloop()