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
                    
                    # Use streaming LLM + realtime TTS for fast response
                    if self.llm_provider == "gemini":
                        self.stream_gemini_response(text)
                    else:
                        # Fallback to non-streaming
                        response = self.get_llm_response(text)
                        self.emit("llm_response", text=response)
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
    
    def stream_gemini_response(self, text):
        """Stream response from Gemini and speak sentence by sentence for realtime"""
        try:
            import google.generativeai as genai
            import re
            
            genai.configure(api_key=self.llm_api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # Use streaming response with token limit
            response = model.generate_content(
                f"You are Lens, a smart personal assistant created by Gia. Respond concisely. User: {text}",
                stream=True,
                generation_config={"max_output_tokens": 500}
            )
            
            buffer = ""
            full_response = ""
            # Pattern to detect sentence endings
            sentence_end = re.compile(r'[.!?。]\s*')
            
            for chunk in response:
                if chunk.text:
                    buffer += chunk.text
                    full_response += chunk.text
                    
                    # Check for complete sentences
                    while True:
                        match = sentence_end.search(buffer)
                        if match:
                            # Extract complete sentence
                            sentence = buffer[:match.end()].strip()
                            buffer = buffer[match.end():]
                            
                            if sentence:
                                # Speak this sentence immediately
                                self.speak(sentence)
                        else:
                            break
            
            # Speak any remaining text
            if buffer.strip():
                self.speak(buffer.strip())
            
            # Emit full response for display
            self.emit("llm_response", text=full_response)
            
        except Exception as e:
            error_msg = str(e).lower()
            if "quota" in error_msg or "429" in str(e):
                self.speak("API quota exceeded. Please try again later.")
            elif "api_key" in error_msg or "401" in str(e):
                self.speak("Invalid API key.")
            else:
                self.speak("Cannot connect to AI service.")
            self.emit("error", message=str(e))
            
    def get_llm_response(self, text):
        """Get response from LLM (non-streaming fallback)"""
        if self.llm_provider == "gemini":
            return self.get_gemini_response(text)
        elif self.llm_provider == "openai":
            return self.get_openai_response(text)
        else:
            return "LLM provider not configured"
            
    def get_gemini_response(self, text):
        """Get response from Google Gemini (non-streaming)"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.llm_api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            response = model.generate_content(
                f"You are Lens, a smart Vietnamese personal assistant created by Gia. Respond concisely. User: {text}",
                generation_config={"max_output_tokens": 500}
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
        """Text-to-speech using edge-tts with true realtime streaming playback"""
        import asyncio
        
        async def stream_tts_realtime():
            try:
                import edge_tts
                
                # Use edge-tts streaming API
                communicate = edge_tts.Communicate(text, self.voice_id)
                
                # Try to use mpv for true streaming playback
                # mpv can read from stdin and play immediately as data arrives
                try:
                    mpv_process = subprocess.Popen(
                        ["mpv", "--no-terminal", "--no-video", "-"],
                        stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            mpv_process.stdin.write(chunk["data"])
                            mpv_process.stdin.flush()
                    
                    mpv_process.stdin.close()
                    mpv_process.wait()
                    
                except FileNotFoundError:
                    # mpv not found, fallback to buffered pygame playback
                    import pygame
                    pygame.mixer.init(frequency=24000)
                    
                    temp_path = tempfile.mktemp(suffix=".mp3")
                    
                    with open(temp_path, "wb") as f:
                        async for chunk in communicate.stream():
                            if chunk["type"] == "audio":
                                f.write(chunk["data"])
                    
                    pygame.mixer.music.load(temp_path)
                    pygame.mixer.music.play()
                    while pygame.mixer.music.get_busy():
                        pygame.time.wait(50)
                    pygame.mixer.quit()
                    
                    os.unlink(temp_path)
                    
            except ImportError as e:
                # Fallback to subprocess if edge_tts module not installed
                self._speak_subprocess(text)
            except Exception as e:
                self.emit("error", message=f"TTS error: {str(e)}")
        
        # Run async function
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(stream_tts_realtime())
            loop.close()
        except Exception as e:
            self.emit("error", message=f"TTS async error: {str(e)}")
    
    def _speak_subprocess(self, text):
        """Fallback TTS using subprocess"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                temp_path = f.name
                
            # Generate speech with edge-tts CLI
            subprocess.run([
                "edge-tts",
                "--voice", self.voice_id,
                "--text", text,
                "--write-media", temp_path
            ], check=True, capture_output=True)
            
            # Play audio using pygame
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(100)
                pygame.mixer.quit()
            except ImportError:
                if sys.platform == "win32":
                    subprocess.run(["ffplay", "-nodisp", "-autoexit", temp_path], 
                                  capture_output=True)
                elif sys.platform == "darwin":
                    os.system(f'afplay "{temp_path}"')
                else:
                    os.system(f'mpg123 -q "{temp_path}" 2>/dev/null || ffplay -nodisp -autoexit "{temp_path}" 2>/dev/null')
                
            os.unlink(temp_path)
        except Exception as e:
            self.emit("error", message=f"TTS subprocess error: {str(e)}")
            
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
