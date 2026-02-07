#!/usr/bin/env python3
"""
Wake Word Service for MMM-LLMsAssistant
Uses Picovoice Porcupine for wake word detection
"""

import argparse
import json
import sys
import os
import struct
import wave
import tempfile
import subprocess
import threading

try:
    import pvporcupine
    from pvrecorder import PvRecorder
except ImportError:
    print(json.dumps({"type": "error", "message": "Please install: pip install pvporcupine pvrecorder"}))
    sys.exit(1)

try:
    import speech_recognition as sr
except ImportError:
    print(json.dumps({"type": "error", "message": "Please install: pip install SpeechRecognition"}))
    sys.exit(1)


class WakeWordService:
    def __init__(self, access_key, ppn_path, llm_provider, llm_api_key, voice_id):
        self.access_key = access_key
        self.ppn_path = ppn_path
        self.llm_provider = llm_provider
        self.llm_api_key = llm_api_key
        self.voice_id = voice_id
        
        self.porcupine = None
        self.recorder = None
        self.recognizer = sr.Recognizer()
        
    def emit(self, event_type, **kwargs):
        """Emit JSON event to stdout for Node.js"""
        event = {"type": event_type, **kwargs}
        print(json.dumps(event), flush=True)
        
    def start(self):
        """Start wake word detection"""
        try:
            # Initialize Porcupine
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                keyword_paths=[self.ppn_path]
            )
            
            # Initialize recorder
            self.recorder = PvRecorder(
                frame_length=self.porcupine.frame_length,
                device_index=-1  # Default device
            )
            self.recorder.start()
            
            print(f"Listening for wake word... (sample rate: {self.porcupine.sample_rate})", file=sys.stderr)
            
            while True:
                pcm = self.recorder.read()
                keyword_index = self.porcupine.process(pcm)
                
                if keyword_index >= 0:
                    self.emit("wake_word")
                    self.handle_wake_word()
                    
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.emit("error", message=str(e))
        finally:
            self.cleanup()
            
    def handle_wake_word(self):
        """Handle wake word detection - listen for command"""
        try:
            # Stop Porcupine recorder temporarily
            self.recorder.stop()
            
            # Use speech recognition
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                    text = self.recognizer.recognize_google(audio, language="vi-VN")
                    self.emit("speech", text=text)
                    
                    # Get LLM response
                    response = self.get_llm_response(text)
                    self.emit("llm_response", text=response)
                    
                    # Speak response
                    self.speak(response)
                    self.emit("speech_complete")
                    
                except sr.WaitTimeoutError:
                    self.emit("error", message="No speech detected")
                except sr.UnknownValueError:
                    self.emit("error", message="Could not understand audio")
                    
        except Exception as e:
            self.emit("error", message=str(e))
        finally:
            # Restart Porcupine recorder
            self.recorder.start()
            
    def get_llm_response(self, text):
        """Get response from LLM"""
        if self.llm_provider == "gemini":
            return self.get_gemini_response(text)
        elif self.llm_provider == "openai":
            return self.get_openai_response(text)
        else:
            return "LLM provider not configured"
            
    def get_gemini_response(self, text):
        """Get response from Google Gemini"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.llm_api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            response = model.generate_content(
                f"You are Lens, a smart Vietnamese personal assistant created by Gia. User: {text}"
            )
            return response.text
        except Exception as e:
            error_msg = str(e).lower()
            if "quota" in error_msg or "429" in str(e):
                return "API quota exceeded. Please try again later."
            elif "api_key" in error_msg or "401" in str(e):
                return "Invalid API key."
            else:
                return "Cannot connect to AI service."
            
    def get_openai_response(self, text):
        """Get response from OpenAI"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.llm_api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are Lens, a smart assistant created by Gia. Respond concisely and helpfully in Vietnamese."},
                    {"role": "user", "content": text}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"
            
    def speak(self, text):
        """Text-to-speech using edge-tts"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name
                
            # Generate speech with edge-tts
            subprocess.run([
                "edge-tts",
                "--voice", self.voice_id,
                "--text", text,
                "--write-media", temp_path
            ], check=True, capture_output=True)
            
            # Play audio using pygame (cross-platform)
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
                pygame.mixer.quit()
            except ImportError:
                # Fallback to playsound
                try:
                    from playsound import playsound
                    playsound(temp_path)
                except ImportError:
                    # Last fallback - platform specific
                    if sys.platform == "win32":
                        import winsound
                        # Convert mp3 to wav for winsound (or use ffplay)
                        subprocess.run(["ffplay", "-nodisp", "-autoexit", temp_path], 
                                      capture_output=True)
                    elif sys.platform == "darwin":
                        os.system(f'afplay "{temp_path}"')
                    else:
                        os.system(f'mpg123 -q "{temp_path}" 2>/dev/null || ffplay -nodisp -autoexit "{temp_path}" 2>/dev/null')
                
            os.unlink(temp_path)
        except Exception as e:
            self.emit("error", message=f"TTS error: {str(e)}")
            
    def cleanup(self):
        """Cleanup resources"""
        if self.recorder:
            self.recorder.delete()
        if self.porcupine:
            self.porcupine.delete()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--access-key", required=True, help="Picovoice access key")
    parser.add_argument("--ppn-path", required=True, help="Path to .ppn wake word file")
    parser.add_argument("--llm-provider", default="gemini", help="LLM provider (gemini/openai)")
    parser.add_argument("--llm-api-key", required=True, help="LLM API key")
    parser.add_argument("--voice-id", default="vi-VN-NamMinhNeural", help="Edge TTS voice ID")
    args = parser.parse_args()
    
    service = WakeWordService(
        access_key=args.access_key,
        ppn_path=args.ppn_path,
        llm_provider=args.llm_provider,
        llm_api_key=args.llm_api_key,
        voice_id=args.voice_id
    )
    service.start()


if __name__ == "__main__":
    main()
