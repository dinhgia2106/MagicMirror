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

# Force UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

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
        self.microphone = sr.Microphone()
        self.conversation = ConversationManager()
        
        # Initialize agent tools for function calling
        self.agent_tools = AgentTools({
            "holiday_api_url": "http://192.168.1.11:8000/api/holidays",
            "lat": 16.463713,
            "lon": 107.590866,
            "timezone": "Asia/Ho_Chi_Minh"
        })
        
    def emit(self, event_type, **kwargs):
        """Emit JSON event to stdout for Node.js - uses base64 for text to avoid Windows encoding issues"""
        import base64
        event = {"type": event_type}
        for key, value in kwargs.items():
            if isinstance(value, str):
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
            
            # Initialize recorder
            self.recorder = PvRecorder(
                frame_length=self.porcupine.frame_length,
                device_index=-1  # Default device
            )
            self.recorder.start()
            
            # Pre-adjust for ambient noise once at startup
            try:
                print("Adjusting for ambient noise...", file=sys.stderr)
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.8)
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
            # Stop Porcupine recorder temporarily
            self.recorder.stop()
            
            # Start new conversation or reset existing one
            self.conversation.start_conversation()
            self.emit("conversation_started")
            
            # Quick ambient noise adjustment after wake word to ensure clear input
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.2)
            except:
                pass
                
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
                # Reduced delay to minimize lost words at start of sentence
                time.sleep(0.15)
                
                # Use pre-initialized microphone
                with self.microphone as source:
                    # Very short adjustment to handle immediate room noise changes
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.1)
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
        """Stream response from Gemini with conversation context and function calling"""
        try:
            import google.generativeai as genai
            from google.generativeai.types import content_types
            
            self.emit("debug", message="Starting Gemini API call with function calling...")
            
            genai.configure(api_key=self.llm_api_key)
            
            # System instruction
            system_instruction = """Bạn là Lens, một trợ lý cá nhân thông minh và thân thiện được tạo bởi Gia.
Bạn có quyền truy cập vào các công cụ để lấy ngày/giờ hiện tại, thời tiết và thông tin ngày lễ.

QUY TẮC QUAN TRỌNG:
- Luôn trả lời bằng ngôn ngữ của người dùng (thường là tiếng Việt).
- KHÔNG sử dụng định dạng markdown (không dùng *, **, _, v.v.) vì đây là đầu ra giọng nói.
- Trả lời một cách tự nhiên, đầy đủ và thân thiện như đang trò chuyện trực diện. 
- Hãy là một người bạn đồng hành hữu ích, tránh trả lời quá ngắn gọn hoặc cụt lủn.
- Khi người dùng hỏi về thời gian, ngày tháng, thời tiết hoặc ngày lễ, hãy LUÔN SỬ DỤNG CÔNG CỤ PHÙ HỢP trước.
- Sau khi nhận được kết quả từ công cụ, hãy tóm tắt thông tin một cách tự nhiên bằng tiếng Việt.
"""

            # Create model with tools
            model = genai.GenerativeModel(
                'gemini-2.5-flash',
                tools=[get_gemini_tools()],
                system_instruction=system_instruction
            )
            
            # Build proper conversation history for Gemini
            gemini_history = []
            for msg in self.conversation.history[:-1]: # History except current message
                role = "user" if msg["role"] == "user" else "model"
                gemini_history.append({"role": role, "parts": [msg["content"]]})
            
            # Start chat with history
            chat = model.start_chat(history=gemini_history, enable_automatic_function_calling=False)
            
            self.emit("debug", message=f"Calling Gemini API with {len(gemini_history)} turns of history...")
            response = chat.send_message(
                text,
                generation_config={"max_output_tokens": 800}
            )
            
            # Check if Gemini wants to call a function
            full_response = None
            
            # Process response - may contain function calls
            if response.candidates and len(response.candidates) > 0:
                candidate = response.candidates[0]
                
                # Check for function calls in the response
                function_calls = []
                text_parts = []
                
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            function_calls.append(part.function_call)
                        elif hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
                
                # If there are function calls, execute them
                if function_calls:
                    self.emit("debug", message=f"Found {len(function_calls)} function call(s)")
                    
                    # Process each function call
                    function_responses = []
                    for fc in function_calls:
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        
                        self.emit("debug", message=f"Executing tool: {tool_name} with args: {tool_args}")
                        
                        # Execute the tool
                        tool_result = self.agent_tools.execute_tool(tool_name, tool_args)
                        self.emit("debug", message=f"Tool result: {json.dumps(tool_result, ensure_ascii=False)[:200]}...")
                        
                        function_responses.append({
                            "name": tool_name,
                            "response": tool_result
                        })
                    
                    # Send function results back to Gemini
                    self.emit("debug", message="Getting final response after tool execution...")
                    
                    # Build function response parts
                    parts_to_send = []
                    for fr in function_responses:
                        parts_to_send.append({
                            "function_response": {
                                "name": fr["name"],
                                "response": {"result": json.dumps(fr["response"], ensure_ascii=False)}
                            }
                        })
                    
                    try:
                        final_response = chat.send_message(
                            parts_to_send,
                            generation_config={"max_output_tokens": 500}
                        )
                    except Exception as e:
                        self.emit("debug", message=f"Error sending function response: {e}, using fallback")
                        tool_summary = f"Kết quả công cụ: {json.dumps(function_responses[0]['response'], ensure_ascii=False)}"
                        final_response = chat.send_message(
                            f"Kết quả tra cứu là: {tool_summary}. Hãy trả lời người dùng một cách tự nhiên và đầy đủ.",
                            generation_config={"max_output_tokens": 500}
                        )
                    
                    # Extract text from final response
                    if final_response.candidates and len(final_response.candidates) > 0:
                        final_candidate = final_response.candidates[0]
                        if final_candidate.content and final_candidate.content.parts:
                            for part in final_candidate.content.parts:
                                if hasattr(part, 'text') and part.text:
                                    full_response = part.text
                                    break
                
                # If no function calls, use the text response directly
                if not full_response and text_parts:
                    full_response = " ".join(text_parts)
            
            # Fallback if no response
            if not full_response:
                try:
                    full_response = response.text
                except:
                    full_response = "Xin lỗi, tôi không thể trả lời lúc này."
            
            self.emit("debug", message=f"Got response: {full_response[:100] if full_response else 'None'}...")
            
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
                generation_config={"max_output_tokens": 700}
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
