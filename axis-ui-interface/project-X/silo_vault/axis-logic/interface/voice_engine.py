# interface/voice_engine.py
import pyttsx3

class VoiceBridge:
    def __init__(self):
        self.engine = pyttsx3.init()

    def speak(self, text):
        print(f"AXIS: {text}")
        self.engine.say(text)
        self.engine.runAndWait()