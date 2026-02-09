#!/usr/bin/env python3
"""
Wake Word Service for MMM-LLMsAssistant
Uses Picovoice Porcupine for wake word detection
Supports continuous conversation flow with auto-reset
Uses edge-tts for Vietnamese text-to-speech (cross-platform compatible)
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
import queue

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    # Disable VieNeu-TTS emoji warning by suppressing print
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Import agent tools
from agent_tools import AgentTools, get_gemini_tools, TOOL_DECLARATIONS

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

try:
    import numpy as np
except ImportError:
    print(json.dumps({"type": "error", "message": "Please install: pip install numpy"}))
    sys.exit(1)

# Edge-TTS is used for Vietnamese text-to-speech
# It works cross-platform (Windows, Linux ARM, etc.) via Microsoft Azure API
# No local ML models needed, avoiding "Illegal instruction" errors on Pi


class PvRecorderMicrophone:
    """
    Microphone class using PvRecorder for audio capture.
    Creates its own PvRecorder instance for speech capture.
    """
    
    def __init__(self, sample_rate=16000, frame_length=512):
        self.sample_rate = sample_rate
        self.SAMPLE_WIDTH = 2  # 2 bytes for 16-bit
        self.SAMPLE_RATE = sample_rate
        self.frame_length = frame_length
        self.recorder = None
        # Sensitivity settings
        self.energy_threshold = 100
        self.pause_threshold = 1.5  # Seconds of silence to mark end of phrase
        self.phrase_threshold = 0.3  # Minimum seconds of speech
        self.non_speaking_duration = 0.5
        # Calculate chunk duration
        self.chunk_duration = frame_length / sample_rate
    
    def start(self):
        """Start the recorder for speech capture"""
        if self.recorder is None:
            self.recorder = PvRecorder(
                frame_length=self.frame_length,
                device_index=-1
            )
        self.recorder.start()
    
    def stop(self):
        """Stop the recorder"""
        if self.recorder:
            self.recorder.stop()
    
    def cleanup(self):
        """Clean up recorder resources"""
        if self.recorder:
            self.recorder.delete()
            self.recorder = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def adjust_for_ambient_noise(self, duration=1.0):
        """Adjust energy threshold based on ambient noise using PvRecorder"""
        if not self.recorder:
            return
            
        try:
            frames_needed = int(duration * self.sample_rate / self.frame_length)
            energy_samples = []
            
            for _ in range(frames_needed):
                pcm = self.recorder.read()
                audio_array = np.array(pcm, dtype=np.int16)
                energy = np.sqrt(np.mean(audio_array.astype(np.float64) ** 2))
                energy_samples.append(energy)
            
            avg_energy = np.mean(energy_samples)
            # Set threshold slightly above ambient noise
            self.energy_threshold = avg_energy * 1.5 + 50
        except Exception:
            pass
    
    def listen(self, timeout=None, phrase_time_limit=None):
        """
        Listen for speech using PvRecorder and return AudioData when speech ends.
        """
        if not self.recorder:
            raise RuntimeError("PvRecorder not set. Call set_recorder() first.")
        
        pause_chunks = int(self.pause_threshold / self.chunk_duration)
        phrase_chunks = int(self.phrase_threshold / self.chunk_duration)
        
        audio_buffer = []
        silent_chunks = 0
        speech_chunks = 0
        speech_started = False
        start_time = time.time()
        speech_start_time = None
        
        while True:
            # Check timeout
            elapsed = time.time() - start_time
            if timeout and not speech_started and elapsed > timeout:
                raise sr.WaitTimeoutError("Listening timed out while waiting for phrase to start")
            
            # Check phrase time limit
            if phrase_time_limit and speech_start_time:
                if time.time() - speech_start_time > phrase_time_limit:
                    break
            
            # Read audio from PvRecorder
            try:
                pcm = self.recorder.read()
                audio_array = np.array(pcm, dtype=np.int16)
            except Exception:
                continue
            
            # Calculate energy
            energy = np.sqrt(np.mean(audio_array.astype(np.float64) ** 2))
            is_speech = energy > self.energy_threshold
            
            if is_speech:
                if not speech_started:
                    speech_started = True
                    speech_start_time = time.time()
                    # Keep some pre-speech buffer
                    pre_buffer_chunks = int(self.non_speaking_duration / self.chunk_duration)
                    if len(audio_buffer) > pre_buffer_chunks:
                        audio_buffer = audio_buffer[-pre_buffer_chunks:]
                
                audio_buffer.append(audio_array)
                speech_chunks += 1
                silent_chunks = 0
            else:
                if speech_started:
                    audio_buffer.append(audio_array)
                    silent_chunks += 1
                    
                    if silent_chunks >= pause_chunks and speech_chunks >= phrase_chunks:
                        break
                else:
                    # Pre-speech buffer
                    audio_buffer.append(audio_array)
                    max_buffer = int(2.0 / self.chunk_duration)
                    if len(audio_buffer) > max_buffer:
                        audio_buffer.pop(0)
        
        # Combine and convert to AudioData
        if audio_buffer:
            audio_data = np.concatenate(audio_buffer)
            audio_bytes = audio_data.astype(np.int16).tobytes()
            return sr.AudioData(audio_bytes, self.sample_rate, self.SAMPLE_WIDTH)
        
        return None


# Reset command patterns - Only wake word resets conversation
RESET_PATTERNS = [
    r"hey\s*lens",
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
        self.microphone = None  # Will be initialized in start()
        
        # Speech recognition tuning to prevent early cutoff
        # pause_threshold: seconds of silence before considering speech done (default 0.8)
        self.recognizer.pause_threshold = 1.5  # Give user more time to pause between phrases
        # phrase_threshold: minimum seconds of speaking before considering it a phrase (default 0.3)
        self.recognizer.phrase_threshold = 0.3
        # non_speaking_duration: seconds of non-speaking audio to keep before/after phrase (default 0.5)
        self.recognizer.non_speaking_duration = 0.5
        # dynamic_energy_threshold: auto-adjust for ambient noise
        self.recognizer.dynamic_energy_threshold = True
        self.conversation = ConversationManager()
        
        # TTS Queue and Worker
        self.tts_queue = queue.Queue()
        self.stop_tts_flag = threading.Event()
        self.current_tts_process = None
        self.tts_thread = threading.Thread(target=self._process_tts_queue, daemon=True)
        self.tts_thread.start()        
        
        self.agent_tools = AgentTools({
            "holiday_api_url": "http://127.0.0.1:8000/api/holidays",
            "lat": 16.463713,
            "lon": 107.590866,
            "timezone": "Asia/Ho_Chi_Minh"
        })

        # Centralized system prompt
        self.system_prompt = (
            "Bạn là Lens, một trợ lý cá nhân thông minh được lập trình và thực hiện bởi Gia. "
            "Bạn là trợ lý đa năng, có thể giúp đỡ nhiều việc khác nhau:\n"
            "1. Trả lời câu hỏi kiến thức chung về khoa học, lịch sử, văn hóa, toán học, vật lý, v.v.\n"
            "2. Sử dụng các công cụ (tools) để tra cứu thời gian, thời tiết, ngày lễ, điều khiển nhạc.\n"
            "3. Giải đáp thắc mắc, tư vấn và hỗ trợ mọi vấn đề trong cuộc sống.\n"
            "Hãy trả lời một cách tự nhiên, ngắn gọn và hữu ích hoàn toàn bằng tiếng Việt."
        )

    def _process_tts_queue(self):
        """Worker thread to process TTS queue sequentially"""
        while True:
            try:
                text = self.tts_queue.get()
                if text is None: break  # Poison pill
                
                # Check stop flag before speaking
                if not self.stop_tts_flag.is_set():
                    self.speak(text)
                
                self.tts_queue.task_done()
            except Exception as e:
                self.emit("error", message=f"TTS Queue Error: {e}")

    def stop_current_tts(self):
        """Stop current TTS playback and clear queue"""
        self.stop_tts_flag.set()
        
        # Clear queue
        with self.tts_queue.mutex:
            self.tts_queue.queue.clear()
            
        # Kill current process
        if self.current_tts_process:
            try:
                self.current_tts_process.terminate()
                self.current_tts_process.wait(timeout=0.5)
            except:
                pass
            self.current_tts_process = None
        
        # Allow new TTS tasks after a short moment
        # Reset flag in start_conversation would be better, but here is instant stop
        pass

    def reset_tts_state(self):
        """Reset TTS state for new conversation"""
        self.stop_current_tts()
        self.stop_tts_flag.clear()
        
    def emit(self, event_type, **kwargs):
        """Emit JSON event to stdout for Node.js - uses base64 for text to avoid Windows encoding issues"""
        import base64
        event = {"type": event_type}
        # Fields that should NOT be base64 encoded (action commands, etc)
        no_encode_fields = {"action", "data", "command"}
        for key, value in kwargs.items():
            if isinstance(value, str) and key not in no_encode_fields:
                # Base64 encode string values to avoid encoding issues
                event[key] = base64.b64encode(value.encode('utf-8')).decode('ascii')
                event[f"{key}_encoded"] = True
            else:
                event[key] = value
        # Use ASCII-only JSON output
        print(json.dumps(event, ensure_ascii=True), flush=True)
        
    def start(self):
        """Start wake word detection"""
        try:
            # Initialize Porcupine
            self.porcupine = pvporcupine.create(
                access_key=self.access_key,
                keyword_paths=[self.ppn_path]
            )
            
            # Initialize recorder for wake word detection
            self.recorder = PvRecorder(
                frame_length=self.porcupine.frame_length,
                device_index=-1  # Default device
            )
            self.recorder.start()
            
            # Initialize microphone with same frame length for consistency
            self.microphone = PvRecorderMicrophone(
                sample_rate=self.porcupine.sample_rate,
                frame_length=self.porcupine.frame_length
            )
            
            # Pre-adjust for ambient noise once at startup (start microphone temporarily)
            try:
                print("Adjusting for ambient noise...", file=sys.stderr)
                self.recorder.stop()  # Stop wake word recorder
                self.microphone.start()
                self.microphone.adjust_for_ambient_noise(duration=0.8)
                self.microphone.stop()
                self.recorder.start()  # Restart wake word recorder
            except Exception as e:
                print(f"Ambient noise adjustment warning: {e}", file=sys.stderr)
            
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
            # Stop wake word recorder and start microphone recorder
            self.recorder.stop()
            self.microphone.start()
            
            # Start new conversation or reset existing one
            self.reset_tts_state()  # Stop any previous audio
            self.conversation.start_conversation()
            self.emit("conversation_started")
            
            # Lower music volume so AI can hear user better
            self.emit("music_lower_volume")
            
            # Quick ambient noise adjustment after wake word to ensure clear input
            try:
                self.microphone.adjust_for_ambient_noise(duration=0.2)
            except:
                pass
                
            # Enter conversation loop
            self.conversation_loop()
                    
        except Exception as e:
            self.emit("error", message=str(e))
        finally:
            # End conversation and switch back to wake word recorder
            if self.conversation.is_active:
                self.conversation.end_conversation()
                self.emit("conversation_ended")
            self.microphone.stop()
            self.recorder.start()
    
    def conversation_loop(self):
        """Main conversation loop - continues until reset condition met"""
        self.emit("debug", message="Starting conversation loop")
        
        while self.conversation.is_active:
            try:
                # Reduced delay to minimize lost words at start of sentence
                time.sleep(0.15)
                
                # Quick ambient noise adjustment
                self.microphone.adjust_for_ambient_noise(duration=0.1)
                self.emit("listening")
                
                try:
                    # Listen with timeout using PvRecorder
                    audio = self.microphone.listen(
                        timeout=SILENCE_TIMEOUT, 
                        phrase_time_limit=15
                    )
                    if audio is None:
                        # No speech detected
                        self.emit("silence_timeout")
                        break
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
                        self.stop_current_tts() # Stop updated TTS
                        self.speak("Kết thúc hội thoại")
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
                    music_tool_called = False
                    if self.llm_provider == "gemini":
                        # Gemini now handles TTS internally within the streaming function
                        result = self.stream_gemini_response_with_context(text)
                        if isinstance(result, tuple):
                            full_response, music_tool_called = result
                        else:
                            full_response = result
                        if full_response:
                            self.conversation.add_assistant_message(full_response)
                    else:
                        response = self.get_llm_response_with_context(text)
                        self.emit("llm_response", text=response)
                        self.tts_queue.put(response) # Use queue
                        if response:
                            self.conversation.add_assistant_message(response)
                        full_response = response
                    
                    # Wait for TTS queue to empty (conversation turn complete)
                    self.tts_queue.join()
                    
                    # Emit that response is complete and ready for next turn
                    self.emit("response_complete")
                    self.emit("debug", message="Response complete, loop continuing...")
                    
                    # Auto-end conversation for music commands (if response doesn't end with ?)
                    if music_tool_called and full_response and not full_response.strip().endswith("?"):
                        self.emit("debug", message="Music command completed, ending conversation")
                        break
                    
                    # Check if conversation is too long
                    if self.conversation.should_end_due_to_length():
                        self.emit("max_turns_reached")
                        self.speak("Hội thoại đã khá dài, nếu bạn cần tiếp tục, hãy gọi Hey Lens")
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
        
        # Restore music volume when conversation ends
        self.emit("music_restore_volume")
        
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
        """Stream response from Gemini with conversation context and function calling"""
        try:
            from google import genai
            from google.genai import types
            
            self.emit("debug", message="Starting Gemini API call (Streaming)...")
            
            # Create client with API key
            client = genai.Client(api_key=self.llm_api_key)
            
            # System instruction
            import datetime
            now_str = datetime.datetime.now().strftime("%A, %d/%m/%Y %H:%M:%S")
            
            system_instruction = f"""{self.system_prompt}
THONG TIN HIEN TAI: {now_str}
QUY TAC PHAN HOI:
- KHONG su dung dinh dang markdown (nhu *, _, `).
- Luon su dung cac cong cu (tools) duoc cung cap de tra cuu thoi tiet hoac cac ngay le neu can.
- Neu thong tin hien tai co ve khong chinh xac, hay chu dong kiem tra lai bang cong cu."""

            # Build conversation history for the new SDK format
            history = []
            for msg in self.conversation.history[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                history.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
            
            # Create chat session
            chat = client.chats.create(
                model='gemini-2.5-flash',
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[get_gemini_tools()],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    max_output_tokens=2048
                ),
                history=history
            )
            
            full_text = ""
            function_calls = []
            music_tool_called = False
            
            # Stream the response - collect all text first
            for chunk in chat.send_message_stream(text):
                # Check for function calls
                if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                    for part in chunk.candidates[0].content.parts:
                        if part.function_call:
                            function_calls.append(part.function_call)
                
                # If we found function calls, drain the rest of the stream and continue
                if function_calls:
                    continue
                
                # Collect text content
                if chunk.text:
                    full_text += chunk.text
            
            # If there were function calls, execute them and get the final answer
            if function_calls:
                self.emit("debug", message=f"Processing {len(function_calls)} function call(s)...")
                
                # Execute tools
                function_responses = []
                for fc in function_calls:
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}
                    self.emit("debug", message=f"Calling {tool_name} with {tool_args}...")
                    result = self.agent_tools.execute_tool(tool_name, tool_args)
                    
                    # If it's a music tool, emit the action for frontend control
                    if result.get("action") and result["action"].startswith("MUSIC_"):
                        self.emit("music_action", action=result["action"], data=result.get("data", {}))
                        music_tool_called = True
                    
                    function_responses.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"result": json.dumps(result, ensure_ascii=False)}
                        )
                    )
                
                # Reset and get final response
                full_text = ""
                
                # Send tool results back to Gemini - collect all
                for chunk in chat.send_message_stream(function_responses):
                    if chunk.text:
                        full_text += chunk.text
            
            # Clean and send to TTS once
            if full_text:
                clean_text = self.clean_text_for_tts(full_text)
                if clean_text:
                    self.emit("llm_response", text=clean_text)
                    self.tts_queue.put(clean_text)
            
            return full_text, music_tool_called

        except Exception as e:
            self.emit("error", message=f"Gemini Streaming Error: {e}")
            fallback = "Xin loi, co loi xay ra."
            self.tts_queue.put(fallback)
            return fallback, False    
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
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=self.llm_api_key)
            
            context = self.conversation.get_context_prompt()
            system_prompt = self.system_prompt
            
            if context:
                prompt = f"{system_prompt}\n\n{context}\nUser: {text}\nLens:"
            else:
                prompt = f"{system_prompt}\n\nUser: {text}\nLens:"
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=700)
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
                {"role": "system", "content": self.system_prompt}
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
            from google import genai
            from google.genai import types
            
            client = genai.Client(api_key=self.llm_api_key)
            
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=f"{self.system_prompt} User yeu cau: {text}",
                config=types.GenerateContentConfig(max_output_tokens=500)
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
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text}
                ]
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"
            
    def speak(self, text):
        """Text-to-speech using edge-tts (cross-platform compatible)"""
        import asyncio
        
        async def stream_tts():
            try:
                import edge_tts
                communicate = edge_tts.Communicate(text, self.voice_id)
                
                temp_path = tempfile.mktemp(suffix=".mp3")
                with open(temp_path, "wb") as f:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                
                # Play with mpv or pygame
                try:
                    self.current_tts_process = subprocess.Popen(
                        ["mpv", "--no-terminal", "--no-video", temp_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self.current_tts_process.wait()
                    self.current_tts_process = None
                except FileNotFoundError:
                    try:
                        import pygame
                        pygame.mixer.init(frequency=24000)
                        pygame.mixer.music.load(temp_path)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.wait(50)
                        pygame.mixer.quit()
                    except ImportError:
                        if sys.platform == "win32":
                            subprocess.run(["ffplay", "-nodisp", "-autoexit", temp_path],
                                          capture_output=True)
                        else:
                            os.system(f'mpg123 -q "{temp_path}" 2>/dev/null || ffplay -nodisp -autoexit "{temp_path}" 2>/dev/null')
                
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
            except Exception as e:
                self.emit("error", message=f"Edge-TTS error: {str(e)}")
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(stream_tts())
        finally:
            try:
                loop.close()
            except:
                pass
            
    def cleanup(self):
        """Cleanup resources"""
        if self.microphone:
            self.microphone.cleanup()
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
