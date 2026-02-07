#!/usr/bin/env python3
"""
Wake Word Service for MMM-LLMsAssistant
Uses Picovoice Porcupine for wake word detection
Supports continuous conversation flow with auto-reset
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
import re
import time

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


# Reset command patterns (Vietnamese and English)
RESET_PATTERNS = [
    r"hey\s*lens",
    r"reset",
    r"tắt\s*(hội\s*thoại)?",
    r"dừng\s*(hội\s*thoại)?",
    r"kết\s*thúc\s*(hội\s*thoại)?",
    r"stop",
    r"end\s*(conversation)?",
    r"bye",
    r"tạm\s*biệt",
    r"cảm\s*ơn.*xong",
    r"ok.*xong",
    r"được\s*rồi",
]

# Noise/meaningless input patterns
NOISE_PATTERNS = [
    r"^[\s]*$",  # Empty or whitespace only
    r"^[^\w\s]+$",  # Only punctuation/symbols
    r"^(.)\1{3,}$",  # Repeated single character (e.g., "aaaa")
    r"^(uh|um|ah|eh|ơ|à|ừ|hả)+[\s]*$",  # Filler sounds
]

# Maximum conversation turns before auto-reset
MAX_CONVERSATION_TURNS = 20
# Maximum silence timeout (seconds) before ending conversation
SILENCE_TIMEOUT = 8
# Number of consecutive noise inputs before ending conversation
MAX_CONSECUTIVE_NOISE = 2


class ConversationManager:
    """Manages conversation history and context"""
    
    def __init__(self):
        self.history = []  # List of {"role": "user"/"assistant", "content": str}
        self.is_active = False
        self.consecutive_noise_count = 0
        self.turn_count = 0
    
    def start_conversation(self):
        """Start a new conversation"""
        self.history = []
        self.is_active = True
        self.consecutive_noise_count = 0
        self.turn_count = 0
    
    def end_conversation(self):
        """End the current conversation"""
        self.history = []
        self.is_active = False
        self.consecutive_noise_count = 0
        self.turn_count = 0
    
    def add_user_message(self, text):
        """Add user message to history"""
        self.history.append({"role": "user", "content": text})
        self.turn_count += 1
        self.consecutive_noise_count = 0  # Reset noise count on valid input
    
    def add_assistant_message(self, text):
        """Add assistant message to history"""
        self.history.append({"role": "assistant", "content": text})
    
    def increment_noise(self):
        """Increment noise counter"""
        self.consecutive_noise_count += 1
    
    def get_context_prompt(self):
        """Get conversation history as context for LLM"""
        if not self.history:
            return ""
        
        context = "Previous conversation:\n"
        for msg in self.history[-10:]:  # Keep last 10 messages for context
            role = "User" if msg["role"] == "user" else "Lens"
            context += f"{role}: {msg['content']}\n"
        return context
    
    def should_end_due_to_noise(self):
        """Check if conversation should end due to too much noise"""
        return self.consecutive_noise_count >= MAX_CONSECUTIVE_NOISE
    
    def should_end_due_to_length(self):
        """Check if conversation should end due to too many turns"""
        return self.turn_count >= MAX_CONVERSATION_TURNS


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
        self.conversation = ConversationManager()
        
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
            
    def is_reset_command(self, text):
        """Check if text is a reset/end conversation command"""
        text_lower = text.lower().strip()
        for pattern in RESET_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        return False
    
    def is_noise_input(self, text):
        """Check if text is noise/meaningless input"""
        if not text or len(text.strip()) < 2:
            return True
        text = text.strip()
        for pattern in NOISE_PATTERNS:
            if re.match(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def handle_wake_word(self):
        """Handle wake word detection - start conversation flow"""
        try:
            # Stop Porcupine recorder temporarily
            self.recorder.stop()
            
            # Start new conversation or reset existing one
            self.conversation.start_conversation()
            self.emit("conversation_started")
            
            # Enter conversation loop
            self.conversation_loop()
                    
        except Exception as e:
            self.emit("error", message=str(e))
        finally:
            # End conversation and restart Porcupine recorder
            if self.conversation.is_active:
                self.conversation.end_conversation()
                self.emit("conversation_ended")
            self.recorder.start()
    
    def conversation_loop(self):
        """Main conversation loop - continues until reset condition met"""
        self.emit("debug", message="Starting conversation loop")
        
        while self.conversation.is_active:
            try:
                # Small delay to let audio system settle after TTS
                time.sleep(0.8)
                
                # Create new microphone instance each iteration
                mic = sr.Microphone()
                
                with mic as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
                    self.emit("listening")
                    
                    try:
                        # Listen with timeout
                        audio = self.recognizer.listen(
                            source, 
                            timeout=SILENCE_TIMEOUT, 
                            phrase_time_limit=15
                        )
                    except sr.WaitTimeoutError:
                        # Silence timeout - end conversation
                        self.emit("silence_timeout")
                        break
                
                # Process audio outside of microphone context to release it
                try:
                    text = self.recognizer.recognize_google(audio, language="vi-VN")
                    
                    # Check for reset command
                    if self.is_reset_command(text):
                        self.emit("reset_detected", text=text)
                        self.speak("Ket thuc hoi thoai")
                        break
                    
                    # Check for noise/meaningless input
                    if self.is_noise_input(text):
                        self.conversation.increment_noise()
                        if self.conversation.should_end_due_to_noise():
                            self.emit("noise_timeout")
                            break
                        continue  # Try listening again
                    
                    # Valid input - process it
                    self.emit("speech", text=text)
                    self.conversation.add_user_message(text)
                    
                    # Get and speak LLM response
                    self.emit("debug", message="Getting LLM response...")
                    if self.llm_provider == "gemini":
                        response = self.stream_gemini_response_with_context(text)
                    else:
                        response = self.get_llm_response_with_context(text)
                        self.emit("llm_response", text=response)
                        self.speak(response)
                    
                    self.emit("debug", message=f"LLM done, response length: {len(response) if response else 0}")
                    
                    if response:
                        self.conversation.add_assistant_message(response)
                    
                    # Emit that response is complete and ready for next turn
                    self.emit("response_complete")
                    self.emit("debug", message="Response complete, loop continuing...")
                    
                    # Check if conversation is too long
                    if self.conversation.should_end_due_to_length():
                        self.emit("max_turns_reached")
                        self.speak("Hoi thoai da kha dai, neu ban can tiep tuc, hay goi Hey Lens")
                        break
                    
                except sr.UnknownValueError:
                    # Could not understand - treat as noise
                    self.conversation.increment_noise()
                    if self.conversation.should_end_due_to_noise():
                        self.emit("noise_timeout")
                        break
                    # Otherwise continue listening
                        
            except Exception as e:
                self.emit("error", message=str(e))
                break
        
        # Emit conversation complete
        self.emit("speech_complete")
    
    def clean_text_for_tts(self, text):
        """Clean text for TTS - remove markdown and special characters"""
        if not text:
            return ""
        # Remove markdown formatting
        text = re.sub(r'\*+', '', text)  # Remove asterisks
        text = re.sub(r'_+', '', text)   # Remove underscores
        text = re.sub(r'`+', '', text)   # Remove backticks
        text = re.sub(r'#+\s*', '', text)  # Remove headers
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)  # Remove links
        text = re.sub(r'\n+', '. ', text)  # Replace newlines with periods
        text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
        return text.strip()
    
    def stream_gemini_response_with_context(self, text):
        """Stream response from Gemini with conversation context"""
        try:
            import google.generativeai as genai
            
            self.emit("debug", message="Starting Gemini API call...")
            
            genai.configure(api_key=self.llm_api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            # Build prompt with conversation context
            context = self.conversation.get_context_prompt()
            system_prompt = "You are Lens, a smart Vietnamese personal assistant created by Gia. Respond concisely and naturally in Vietnamese. Do NOT use markdown formatting. Keep the conversation flowing."
            
            if context:
                prompt = f"{system_prompt}\n\n{context}\nUser: {text}\nLens:"
            else:
                prompt = f"{system_prompt}\n\nUser: {text}\nLens:"
            
            # Use NON-streaming to avoid TTS conflicts
            self.emit("debug", message="Calling Gemini API...")
            response = model.generate_content(
                prompt,
                generation_config={"max_output_tokens": 300}
            )
            
            # Check if response was blocked
            full_response = None
            try:
                # Try to get response text
                if response.candidates and len(response.candidates) > 0:
                    candidate = response.candidates[0]
                    if candidate.content and candidate.content.parts:
                        full_response = candidate.content.parts[0].text
                    else:
                        # Response blocked - check safety ratings
                        self.emit("debug", message=f"Response blocked. Safety ratings: {candidate.safety_ratings if hasattr(candidate, 'safety_ratings') else 'N/A'}")
                        full_response = "Xin loi, toi khong the tra loi cau hoi nay."
                else:
                    full_response = response.text  # Fallback to simple accessor
            except Exception as text_err:
                self.emit("debug", message=f"Error getting response text: {text_err}")
                full_response = "Xin loi, toi khong the tra loi cau hoi nay."
            
            self.emit("debug", message=f"Got response: {full_response[:50] if full_response else 'None'}...")
            
            # Emit full response for display
            self.emit("llm_response", text=full_response)
            
            # Clean and speak the response
            clean_response = self.clean_text_for_tts(full_response)
            self.emit("debug", message=f"Speaking cleaned response...")
            
            try:
                self.speak(clean_response)
                self.emit("debug", message="Done speaking")
            except Exception as speak_err:
                self.emit("debug", message=f"TTS error (continuing): {speak_err}")
            
            return full_response
            
        except Exception as e:
            self.emit("debug", message=f"Gemini Error: {str(e)}")
            error_msg = str(e).lower()
            fallback_response = "Không thể kết nối AI."
            try:
                if "quota" in error_msg or "429" in str(e):
                    fallback_response = "API hết hạn mức."
                    self.speak(fallback_response)
                elif "api_key" in error_msg or "401" in str(e):
                    fallback_response = "API key không hợp lệ."
                    self.speak(fallback_response)
                else:
                    self.speak(fallback_response)
            except:
                pass
            self.emit("error", message=str(e))
            return fallback_response
    
    def get_llm_response_with_context(self, text):
        """Get response from LLM with conversation context (non-streaming)"""
        if self.llm_provider == "gemini":
            return self.get_gemini_response_with_context(text)
        elif self.llm_provider == "openai":
            return self.get_openai_response_with_context(text)
        else:
            return "LLM provider not configured"
    
    def get_gemini_response_with_context(self, text):
        """Get response from Gemini with context (non-streaming)"""
        try:
            import google.generativeai as genai
            
            genai.configure(api_key=self.llm_api_key)
            model = genai.GenerativeModel('gemini-2.5-flash')
            
            context = self.conversation.get_context_prompt()
            system_prompt = "You are Lens, a smart Vietnamese personal assistant created by Gia. Respond concisely."
            
            if context:
                prompt = f"{system_prompt}\n\n{context}\nUser: {text}\nLens:"
            else:
                prompt = f"{system_prompt}\n\nUser: {text}\nLens:"
            
            response = model.generate_content(
                prompt,
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
    
    def get_openai_response_with_context(self, text):
        """Get response from OpenAI with context"""
        try:
            from openai import OpenAI
            
            client = OpenAI(api_key=self.llm_api_key)
            
            # Build messages with conversation history
            messages = [
                {"role": "system", "content": "You are Lens, a smart Vietnamese assistant created by Gia. Respond concisely."}
            ]
            
            # Add conversation history
            for msg in self.conversation.history[-10:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            
            # Add current user message
            messages.append({"role": "user", "content": text})
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"
    
    def stream_gemini_response(self, text):
        """Stream response from Gemini and speak sentence by sentence for realtime (legacy)"""
        return self.stream_gemini_response_with_context(text)
            
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
                    
                    try:
                        os.unlink(temp_path)
                    except:
                        pass
                    
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
        except Exception as e:
            self.emit("error", message=f"TTS async error: {str(e)}")
        finally:
            try:
                loop.close()
            except:
                pass
    
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
