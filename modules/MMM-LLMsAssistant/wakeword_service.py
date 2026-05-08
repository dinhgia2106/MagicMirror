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
import concurrent.futures

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

# WebRTC VAD - accurate voice activity detection (same as XiaoZhi-ESP32)
# Falls back to energy-based VAD if not installed
try:
    import webrtcvad
    WEBRTC_VAD_AVAILABLE = True
except ImportError:
    WEBRTC_VAD_AVAILABLE = False

# Edge-TTS is used for Vietnamese text-to-speech
# It works cross-platform (Windows, Linux ARM, etc.) via Microsoft Azure API
# No local ML models needed, avoiding "Illegal instruction" errors on Pi


class MicBoostProcessor:
    """Stateful boost pipeline for I2S MEMS mics whose raw signal is too quiet.

    Pipeline per frame:
      1. 1-pole DC-block / HPF (removes I2S DC offset + sub-bass rumble)
      2. Frame-RMS noise gate with hysteresis + attack/release envelope
         (block-level, NOT per-sample, so fricatives stay intact)
      3. Linear gain (boost_db)
      4. tanh soft-clip (replaces hard clip to avoid distortion when loud)

    Detection (VAD/energy threshold/Porcupine on raw) is unaffected — call this
    only on the audio you actually want amplified (STT buffer, Porcupine input).
    """

    def __init__(self, sample_rate=16000, boost_db=30, hpf_cutoff_hz=80,
                 default_noise_floor=80.0, closed_floor=0.05,
                 open_ratio=2.5, close_ratio=1.5,
                 attack_per_frame=1.0, release_per_frame=1.0/6.0):
        self.sample_rate = sample_rate
        self.gain = float(10 ** (boost_db / 20))

        # IIR HPF: y[n] = x[n] - x[n-1] + R*y[n-1], pole at R = exp(-2π·fc/fs)
        self.hpf_R = float(np.exp(-2.0 * np.pi * hpf_cutoff_hz / sample_rate))
        self._hpf_x_prev = 0.0
        self._hpf_y_prev = 0.0

        # Gate thresholds derived from measured noise floor (RMS of raw int16)
        self.noise_floor = float(default_noise_floor)
        self.open_ratio = open_ratio
        self.close_ratio = close_ratio
        self._gate_open = False
        self._gain_env = 0.0
        self._closed_floor = closed_floor
        self._attack = attack_per_frame
        self._release = release_per_frame

    def set_noise_floor(self, rms):
        """Seed gate thresholds from measured ambient RMS (run on RAW audio)."""
        if rms and rms > 0:
            self.noise_floor = float(rms)

    def reset(self):
        self._hpf_x_prev = 0.0
        self._hpf_y_prev = 0.0
        self._gate_open = False
        self._gain_env = 0.0

    def process(self, audio_int16, gate_enabled=True):
        if audio_int16 is None or len(audio_int16) == 0:
            return audio_int16
        x = np.asarray(audio_int16, dtype=np.float32)

        # 1) DC-block / low-shelf rumble removal
        R = self.hpf_R
        x_prev = self._hpf_x_prev
        y_prev = self._hpf_y_prev
        y = np.empty_like(x)
        for i in range(x.shape[0]):
            yi = x[i] - x_prev + R * y_prev
            y[i] = yi
            x_prev = x[i]
            y_prev = yi
        self._hpf_x_prev = x_prev
        self._hpf_y_prev = y_prev
        x = y

        # 2) Frame-level RMS gate with hysteresis (open > close prevents flutter)
        if gate_enabled:
            rms = float(np.sqrt(np.mean(x * x)))
            open_th = self.noise_floor * self.open_ratio
            close_th = self.noise_floor * self.close_ratio
            if not self._gate_open and rms > open_th:
                self._gate_open = True
            elif self._gate_open and rms < close_th:
                self._gate_open = False

            target = 1.0 if self._gate_open else self._closed_floor
            if target > self._gain_env:
                self._gain_env = min(target, self._gain_env + self._attack)
            else:
                self._gain_env = max(target, self._gain_env - self._release)
            x = x * self._gain_env

        # 3) Linear gain
        x = x * self.gain

        # 4) Soft-clip: tanh saturates smoothly at ±32767 instead of hard cut
        clip = 32767.0
        x = np.tanh(x / clip) * clip

        return x.astype(np.int16)


class PvRecorderMicrophone:
    """
    Microphone class using PvRecorder for audio capture.
    Uses WebRTC VAD (like XiaoZhi-ESP32) for accurate speech detection,
    with energy-based fallback if webrtcvad is not installed.
    """
    
    def __init__(self, sample_rate=16000, frame_length=512):
        self.sample_rate = sample_rate
        self.SAMPLE_WIDTH = 2  # 2 bytes for 16-bit
        self.SAMPLE_RATE = sample_rate
        self.frame_length = frame_length
        self.recorder = None
        self.on_speech_start = None  # Callback when speech starts
        
        # === WebRTC VAD (used with energy for hybrid detection) ===
        self.use_webrtc_vad = WEBRTC_VAD_AVAILABLE
        if self.use_webrtc_vad:
            self.vad = webrtcvad.Vad(3)  # Aggressiveness 3 = strictest, best noise rejection
            self.vad_frame_ms = 30       # 30ms frames (webrtcvad accepts 10/20/30)
            self.vad_frame_samples = int(sample_rate * self.vad_frame_ms / 1000)  # 480
            self._vad_sample_buffer = np.array([], dtype=np.int16)
            self._vad_decisions = []     # Rolling window of recent VAD decisions
            self._vad_decision_window = 5  # Smooth over 5 VAD frames (~150ms) to prevent flicker
        
        # === Energy-based VAD (fallback + end-of-speech helper) ===
        self.energy_threshold = 100
        self.dynamic_energy_ratio = 1.8  # Multiplier for ambient noise
        
        # Adaptive pause detection - starts short, extends if still speaking
        self.min_pause_threshold = 0.6   # Minimum silence to end (faster response)
        self.max_pause_threshold = 1.2   # Maximum silence to end
        self.pause_threshold = 0.8       # Current/default pause threshold
        
        self.phrase_threshold = 0.2      # Minimum seconds of speech (reduced for quick commands)
        self.non_speaking_duration = 0.3 # Pre-speech buffer (reduced)
        
        # Energy drop detection for natural end-of-speech
        self.energy_drop_ratio = 0.3     # If energy drops to 30% of peak, likely end of speech
        self.trailing_silence_chunks = 0 # Track consecutive low-energy frames
        
        # Calculate chunk duration
        self.chunk_duration = frame_length / sample_rate
        
        # Statistics for adaptive adjustment
        self.recent_speech_energies = []  # Track energy levels during speech
        self.peak_speech_energy = 0       # Peak energy in current utterance

        # Boost pipeline for STT (gate ON — clean speech, suppress hiss)
        self.boost = MicBoostProcessor(sample_rate=sample_rate, boost_db=30)
    
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
    
    def _check_vad(self, audio_array):
        """Check speech using WebRTC VAD with frame re-chunking and smoothing.
        
        PvRecorder gives 512-sample frames (32ms), but webrtcvad needs 480 samples (30ms).
        This method buffers samples and processes complete 30ms chunks.
        
        Returns: True (speech), False (silence), or None (not enough data / VAD unavailable)
        """
        if not self.use_webrtc_vad:
            return None
        
        # Accumulate samples from PvRecorder frame
        self._vad_sample_buffer = np.concatenate([self._vad_sample_buffer, audio_array])
        
        # Process all complete 30ms VAD frames
        processed_any = False
        while len(self._vad_sample_buffer) >= self.vad_frame_samples:
            frame = self._vad_sample_buffer[:self.vad_frame_samples]
            self._vad_sample_buffer = self._vad_sample_buffer[self.vad_frame_samples:]
            
            frame_bytes = frame.astype(np.int16).tobytes()
            try:
                is_speech = self.vad.is_speech(frame_bytes, self.sample_rate)
                self._vad_decisions.append(is_speech)
                if len(self._vad_decisions) > self._vad_decision_window:
                    self._vad_decisions.pop(0)
                processed_any = True
            except Exception:
                pass
        
        if not processed_any or not self._vad_decisions:
            return None
        
        # Smoothing: speech if supermajority (>=60%) of recent frames detected speech
        # This prevents ambient noise flicker from triggering false speech start
        speech_count = sum(self._vad_decisions)
        return speech_count >= max(2, int(len(self._vad_decisions) * 0.6))
    
    def _reset_vad_state(self):
        """Reset WebRTC VAD buffers for a new listening session"""
        if self.use_webrtc_vad:
            self._vad_sample_buffer = np.array([], dtype=np.int16)
            self._vad_decisions = []
    
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
            
            if not energy_samples:
                return
                
            # Use median instead of mean to be more robust to occasional spikes
            median_energy = np.median(energy_samples)
            # Also calculate standard deviation for adaptive threshold
            std_energy = np.std(energy_samples)
            
            # Set threshold: median + 2*std gives ~95% confidence above noise
            # but also use dynamic_energy_ratio as minimum multiplier
            threshold_from_std = median_energy + 2 * std_energy
            threshold_from_ratio = median_energy * self.dynamic_energy_ratio
            
            # Use the higher of the two methods, with a minimum floor
            self.energy_threshold = max(
                max(threshold_from_std, threshold_from_ratio),
                80  # Absolute minimum threshold
            )

            # Seed boost gate with the measured RAW ambient floor
            self.boost.set_noise_floor(median_energy)

            # Reset peak energy for new utterance
            self.peak_speech_energy = 0
            self.recent_speech_energies = []
        except Exception:
            pass
    
    def listen(self, timeout=None, phrase_time_limit=None):
        """
        Listen for speech using PvRecorder and return AudioData when speech ends.
        Uses WebRTC VAD (primary) or energy-based VAD (fallback) with
        adaptive end-of-speech detection via energy drop analysis.
        """
        if not self.recorder:
            raise RuntimeError("PvRecorder not set. Call set_recorder() first.")
        
        # Calculate chunk thresholds
        min_pause_chunks = int(self.min_pause_threshold / self.chunk_duration)
        max_pause_chunks = int(self.max_pause_threshold / self.chunk_duration)
        phrase_chunks = int(self.phrase_threshold / self.chunk_duration)
        
        audio_buffer = []
        silent_chunks = 0
        speech_chunks = 0
        speech_started = False
        start_time = time.time()
        speech_start_time = None
        hard_timeout = 20  # Absolute max seconds to prevent infinite hang
        
        # Reset VAD and energy state for new listening session
        self._reset_vad_state()
        self.recent_speech_energies = []
        self.peak_speech_energy = 0
        energy_window = []  # Rolling window for smoothing
        window_size = 3     # Smooth over 3 frames (~96ms at 512 frame_length)
        
        while True:
            # Hard safety timeout - prevent infinite hang regardless of state
            total_elapsed = time.time() - start_time
            if total_elapsed > hard_timeout:
                if speech_started and audio_buffer:
                    break  # Return whatever audio we have
                raise sr.WaitTimeoutError("Listening hard timeout reached")
            
            # Check timeout (no speech detected yet)
            elapsed = time.time() - start_time
            if timeout and not speech_started and elapsed > timeout:
                raise sr.WaitTimeoutError("Listening timed out while waiting for phrase to start")
            
            # Check phrase time limit
            if phrase_time_limit and speech_start_time:
                if time.time() - speech_start_time > phrase_time_limit:
                    break
            
            # Safety timeout: if speech "started" but very few actual speech chunks
            # accumulated (false start from noise), reset and treat as timeout
            if speech_started and timeout and speech_start_time:
                time_since_speech_start = time.time() - speech_start_time
                if time_since_speech_start > timeout and speech_chunks < phrase_chunks:
                    raise sr.WaitTimeoutError("Listening timed out - false speech start from noise")
            
            # Read audio from PvRecorder
            try:
                pcm = self.recorder.read()
                audio_array = np.array(pcm, dtype=np.int16)
                # Boosted copy for the STT buffer; detection still uses raw below
                audio_array_boosted = self.boost.process(audio_array, gate_enabled=True)
            except Exception:
                continue

            # Calculate energy on RAW (boost would inflate the threshold)
            energy = np.sqrt(np.mean(audio_array.astype(np.float64) ** 2))
            energy_window.append(energy)
            if len(energy_window) > window_size:
                energy_window.pop(0)
            smoothed_energy = np.mean(energy_window)

            # Speech detection: HYBRID approach
            # - WebRTC VAD + energy must BOTH agree = speech (prevents noise false positives)
            # - If WebRTC VAD unavailable, fall back to energy-only
            energy_says_speech = smoothed_energy > self.energy_threshold
            vad_result = self._check_vad(audio_array)
            
            if vad_result is not None:
                # Hybrid: both VAD and energy must agree for speech start
                # For ongoing speech, be slightly more lenient (either can sustain)
                if not speech_started:
                    is_speech = vad_result and energy_says_speech
                else:
                    is_speech = vad_result or energy_says_speech
            else:
                is_speech = energy_says_speech
            
            if is_speech:
                if not speech_started:
                    speech_started = True
                    speech_start_time = time.time()
                    # Notify that user started speaking
                    if self.on_speech_start:
                        self.on_speech_start()
                    # Keep some pre-speech buffer
                    pre_buffer_chunks = int(self.non_speaking_duration / self.chunk_duration)
                    if len(audio_buffer) > pre_buffer_chunks:
                        audio_buffer = audio_buffer[-pre_buffer_chunks:]

                audio_buffer.append(audio_array_boosted)
                speech_chunks += 1
                silent_chunks = 0
                
                # Track energy for adaptive end detection
                self.recent_speech_energies.append(smoothed_energy)
                if len(self.recent_speech_energies) > 30:  # ~1 second window
                    self.recent_speech_energies.pop(0)
                if smoothed_energy > self.peak_speech_energy:
                    self.peak_speech_energy = smoothed_energy
            else:
                if speech_started:
                    audio_buffer.append(audio_array_boosted)
                    silent_chunks += 1
                    
                    # === ADAPTIVE END-OF-SPEECH DETECTION ===
                    # Calculate dynamic pause threshold based on speech characteristics
                    
                    # 1. Energy drop detection - if energy dropped significantly, end sooner
                    energy_drop_detected = False
                    if self.peak_speech_energy > 0:
                        current_ratio = smoothed_energy / self.peak_speech_energy
                        if current_ratio < self.energy_drop_ratio:
                            energy_drop_detected = True
                    
                    # 2. Adaptive pause threshold based on speech length
                    # Short commands (< 1s): use shorter pause
                    # Longer speech: use longer pause
                    speech_duration = time.time() - speech_start_time if speech_start_time else 0
                    if speech_duration < 1.0:
                        # Quick command - respond faster
                        adaptive_pause_chunks = min_pause_chunks
                    elif speech_duration < 3.0:
                        # Medium utterance
                        adaptive_pause_chunks = int((min_pause_chunks + max_pause_chunks) / 2)
                    else:
                        # Longer speech - allow more pauses
                        adaptive_pause_chunks = max_pause_chunks
                    
                    # 3. If energy dropped significantly, reduce required pause
                    if energy_drop_detected:
                        adaptive_pause_chunks = max(min_pause_chunks, adaptive_pause_chunks - 2)
                    
                    # End speech if conditions met
                    if silent_chunks >= adaptive_pause_chunks and speech_chunks >= phrase_chunks:
                        break
                else:
                    # Pre-speech buffer
                    audio_buffer.append(audio_array_boosted)
                    max_buffer = int(1.5 / self.chunk_duration)  # Reduced pre-buffer
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
SILENCE_TIMEOUT = 5  # Reduced from 8s for faster response
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
        self.streaming_player = None  # Detected in start() for low-latency TTS

        # Boost for Porcupine — DC-block + gain + soft-clip, NO gate so the
        # 'h' onset of "hey lens" isn't chopped while the gate ramps open.
        self.wake_boost = MicBoostProcessor(boost_db=30)
        
        # Manual activation via stdin (click on orb)
        self.manual_activate_event = threading.Event()
        
        # Speech recognition tuning - matched to PvRecorderMicrophone VAD settings
        # These are backup settings; primary VAD is in PvRecorderMicrophone
        self.recognizer.pause_threshold = 0.8   # Reduced from 1.5 for faster response
        self.recognizer.phrase_threshold = 0.2  # Minimum speech duration
        self.recognizer.non_speaking_duration = 0.3  # Reduced buffer
        self.recognizer.dynamic_energy_threshold = True
        self.conversation = ConversationManager()
        
        # TTS Queue and Worker
        self.tts_queue = queue.Queue()
        self.stop_tts_flag = threading.Event()
        self.current_tts_process = None
        self.tts_thread = threading.Thread(target=self._process_tts_queue, daemon=True)
        self.tts_thread.start()        
        
        # Wake word interrupt during TTS/LLM response
        self.interrupted_by_wakeword = threading.Event()
        self._wakeword_monitor_stop = threading.Event()
        self._wakeword_monitor_thread = None
        
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
            "1. Trò chuyện, dạy học (ngôn ngữ, kiến thức), và trả lời mọi câu hỏi của người dùng bằng kiến thức rộng lớn của bạn.\n"
            "2. Sử dụng các công cụ (tools) ĐƯỢC CUNG CẤP để tra cứu thời gian, thời tiết, ngày lễ, điều khiển nhạc KHI CẦN THIẾT.\n"
            "3. TÌM KIẾM INTERNET: Dùng web_search khi cần thông tin mới nhất (tin tức, giá cả, sự kiện, người nổi tiếng, sản phẩm, v.v.) hoặc khi không chắc chắn câu trả lời. Dùng web_read để đọc chi tiết trang web nếu snippet chưa đủ.\n"
            "4. Giải đáp thắc mắc, tư vấn và hỗ trợ mọi vấn đề trong cuộc sống.\n"
            "LƯU Ý: Bạn KHÔNG bị giới hạn chỉ trong các công cụ trên. Hãy thoải mái dạy ngoại ngữ, kể chuyện, làm thơ, hoặc thảo luận bất kỳ chủ đề nào người dùng muốn.\n"
            "Hãy trả lời một cách tự nhiên, ngắn gọn và hữu ích hoàn toàn bằng tiếng Việt.\n"
            "\n"
            "=== KÝ ỨC CỤC BỘ (BẮT BUỘC) ===\n"
            "Bạn có bộ nhớ dài hạn qua file soul.md. Đây là TÍNH NĂNG QUAN TRỌNG NHẤT của bạn.\n"
            "\n"
            "QUY TẮC LƯU KÝ ỨC (KHÔNG ĐƯỢC BỎ QUA):\n"
            "1. Khi người dùng KỂ CHUYỆN, CHIA SẺ sự kiện, cảm xúc, trải nghiệm, những điều muốn ghi nhớ lâu dài chứ không phải xã giao vu vơ -> GỌI memory_save NGAY LẬP TỨC, TRƯỚC KHI trả lời.\n"
            "   Ví dụ: 'Hôm nay tôi bị gì đó...' -> Gọi memory_save TRƯỚC, rồi mới hỏi han/động viên.\n"
            "   Ví dụ: 'Tôi vừa đi du lịch Đà Lạt về' -> Gọi memory_save TRƯỚC, rồi mới hỏi chuyện.\n"
            "   Ví dụ: 'Tôi thích uống cà phê' -> Gọi memory_save TRƯỚC.\n"
            "   Ví dụ: 'Tôi là AI engineer' -> Gọi memory_save TRƯỚC.\n"
            "2. Khi lưu sự kiện có thời gian (hôm nay, hôm qua, tuần trước), PHẢI dùng NGÀY CỤ THỂ (vd: 2026-02-11) thay vì 'hôm nay'.\n"
            "   Lấy ngày từ THÔNG TIN HIỆN TẠI trong system prompt.\n"
            "3. Khi người dùng HỎI VỀ BẢN THÂN HỌ (bạn biết gì về tôi? hôm nay tôi thế nào? tôi đã làm gì?):\n"
            "   -> GỌI memory_list TRƯỚC, rồi dùng ký ức để trả lời. TUYỆT ĐỐI KHÔNG trả lời 'tôi không biết' mà không check memory trước.\n"
            "4. Khi người dùng nói 'quên đi' hoặc sửa thông tin cũ -> gọi memory_remove rồi memory_save.\n"
            "5. KHÔNG cần xin phép trước khi lưu -- hãy làm TỰ ĐỘNG và TỰ NHIÊN.\n"
            "6. Section phù hợp: 'user profile' cho thông tin cá nhân, 'learned facts' cho kiến thức, 'conversation notes' cho sự kiện/nhật ký.\n"
            "7. Hỏi về gì dù có tool call cụ thể nhưng vẫn LUÔN kiểm tra PERSISTENT MEMORY ở trên xem có gì liên quan đến người dùng không (sinh nhật, sự kiện cá nhân, kỷ niệm). Nếu có, PHẢI đề cập.\n"
        )

    def _process_tts_queue(self):
        """Worker thread to process TTS queue sequentially with phase-based async TTS"""
        while True:
            try:
                text = self.tts_queue.get()
                if text is None: break  # Poison pill
                
                # Check stop flag before speaking
                if not self.stop_tts_flag.is_set():
                    # Use phase-based async TTS for long text
                    self.process_phases_async(text)
                
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

    def _start_wakeword_monitor(self):
        """Start monitoring for wake word during TTS/LLM to allow interruption"""
        self._wakeword_monitor_stop.clear()
        self.interrupted_by_wakeword.clear()
        self._wakeword_monitor_thread = threading.Thread(
            target=self._monitor_wakeword_during_tts, daemon=True
        )
        self._wakeword_monitor_thread.start()

    def _stop_wakeword_monitor(self):
        """Stop the wake word monitoring thread"""
        self._wakeword_monitor_stop.set()
        if self._wakeword_monitor_thread and self._wakeword_monitor_thread.is_alive():
            self._wakeword_monitor_thread.join(timeout=1.0)
        self._wakeword_monitor_thread = None

    def _monitor_wakeword_during_tts(self):
        """Background thread: listen for wake word during TTS/LLM to allow interruption.
        Reads audio from the microphone's PvRecorder and checks with Porcupine."""
        try:
            while not self._wakeword_monitor_stop.is_set():
                try:
                    if not self.microphone or not self.microphone.recorder:
                        break
                    pcm = self.microphone.recorder.read()
                    keyword_index = self.porcupine.process(pcm)
                    if keyword_index >= 0:
                        self.emit("debug", message="Wake word detected during response - interrupting!")
                        self.emit("wake_word")  # Immediately update frontend orb color
                        self.interrupted_by_wakeword.set()
                        self.stop_current_tts()
                        break
                except Exception:
                    break
        except Exception:
            pass

    def _detect_streaming_player(self):
        """Detect if a streaming-capable audio player is available.
        Returns command list for Popen if found, None otherwise."""
        # Try mpv first (best stdin streaming support)
        try:
            subprocess.run(["mpv", "--version"], capture_output=True, timeout=5)
            return ["mpv", "--no-terminal", "--no-video", "--demuxer=lavf", "-"]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        # Try ffplay as fallback
        try:
            subprocess.run(["ffplay", "-version"], capture_output=True, timeout=5)
            return ["ffplay", "-nodisp", "-autoexit", "-i", "pipe:0"]
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return None

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
        
    def _stdin_listener(self):
        """Background thread to listen for commands from Node.js via stdin"""
        try:
            for line in sys.stdin:
                command = line.strip()
                if command == "ACTIVATE":
                    print("Manual activation received via stdin", file=sys.stderr)
                    self.manual_activate_event.set()
        except Exception:
            pass  # stdin closed or error

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
            # Set callback to emit listening_active when user starts speaking
            self.microphone.on_speech_start = lambda: self.emit("listening_active")
            
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
            
            # Detect streaming-capable audio player for low-latency TTS
            self.streaming_player = self._detect_streaming_player()
            if self.streaming_player:
                print(f"Streaming TTS enabled with: {self.streaming_player[0]}", file=sys.stderr)
            else:
                print("Streaming TTS not available, using file-based TTS", file=sys.stderr)
            
            print(f"Listening for wake word... (sample rate: {self.porcupine.sample_rate})", file=sys.stderr)
            
            # Start stdin listener for manual activation from frontend
            stdin_thread = threading.Thread(target=self._stdin_listener, daemon=True)
            stdin_thread.start()
            
            while True:
                # Check for manual activation (user clicked orb)
                if self.manual_activate_event.is_set():
                    self.manual_activate_event.clear()
                    self.emit("wake_word")
                    self.handle_wake_word()
                    continue
                
                pcm = self.recorder.read()
                # DC-block + 30dB + soft-clip (gate off to preserve onset)
                pcm_boosted = self.wake_boost.process(
                    np.array(pcm, dtype=np.int16), gate_enabled=False
                ).tolist()
                keyword_index = self.porcupine.process(pcm_boosted)

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
        consecutive_errors = 0
        max_consecutive_errors = 2
        
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
                    consecutive_errors = 0  # Reset on valid input
                    self.emit("speech", text=text)
                    self.conversation.add_user_message(text)
                    
                    # Start wake word monitoring (allows interrupt during LLM/TTS)
                    self._start_wakeword_monitor()
                    
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
                    
                    # Stop wake word monitoring
                    self._stop_wakeword_monitor()
                    
                    # Check if interrupted by wake word
                    if self.interrupted_by_wakeword.is_set():
                        self.interrupted_by_wakeword.clear()
                        self.stop_tts_flag.clear()  # Reset for next TTS
                        self.emit("debug", message="Interrupted by wake word, ready for new input")
                        # Quick re-adjust mic for listening
                        try:
                            self.microphone.adjust_for_ambient_noise(duration=0.15)
                        except:
                            pass
                        continue  # Go back to listening
                    
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
                    consecutive_errors += 1
                    self.conversation.increment_noise()
                    if self.conversation.should_end_due_to_noise():
                        self.emit("noise_timeout")
                        break
                    if consecutive_errors >= max_consecutive_errors:
                        self.emit("debug", message="Too many consecutive errors, ending conversation")
                        break
                    # Otherwise continue listening
                        
            except Exception as e:
                consecutive_errors += 1
                self.emit("error", message=str(e))
                if consecutive_errors >= max_consecutive_errors:
                    self.emit("debug", message="Too many consecutive errors, ending conversation")
                    break
                # Fallback: go back to activated (blue) state and retry listening
                self.emit("debug", message=f"Recoverable error ({consecutive_errors}/{max_consecutive_errors}), retrying...")
                self.emit("listening")  # Signal frontend to show blue (activated) state
                time.sleep(0.3)  # Brief pause before retry
                continue
        
        # Ensure wake word monitor is stopped when conversation ends
        self._stop_wakeword_monitor()
        
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
    
    def split_into_phases(self, text, target_words=20):
        """
        Split text into phases of approximately target_words each.
        If word N belongs to a sentence, include the whole sentence in current phase.
        
        Returns list of text phases.
        """
        if not text:
            return []
        
        # Split into sentences (Vietnamese/English punctuation)
        sentence_pattern = r'(?<=[.!?;:])\s+'
        sentences = re.split(sentence_pattern, text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return [text] if text.strip() else []
        
        phases = []
        current_phase = []
        current_word_count = 0
        
        for sentence in sentences:
            sentence_words = len(sentence.split())
            
            if current_word_count == 0:
                # First sentence always goes to current phase
                current_phase.append(sentence)
                current_word_count += sentence_words
            elif current_word_count + sentence_words <= target_words:
                # Still fits within target
                current_phase.append(sentence)
                current_word_count += sentence_words
            elif current_word_count >= target_words:
                # Current phase is full, start new phase
                phases.append(' '.join(current_phase))
                current_phase = [sentence]
                current_word_count = sentence_words
            else:
                # Adding this sentence would exceed target, but we haven't reached target yet
                # Include it anyway (as per requirement: complete the sentence)
                current_phase.append(sentence)
                current_word_count += sentence_words
                # If now at or over target, finalize this phase
                if current_word_count >= target_words:
                    phases.append(' '.join(current_phase))
                    current_phase = []
                    current_word_count = 0
        
        # Don't forget the last phase
        if current_phase:
            phases.append(' '.join(current_phase))
        
        return phases
    
    def generate_tts_audio(self, text):
        """
        Generate TTS audio file for given text and return the file path.
        Returns None if generation fails.
        """
        import asyncio
        
        async def generate():
            try:
                import edge_tts
                communicate = edge_tts.Communicate(text, self.voice_id)
                temp_path = tempfile.mktemp(suffix=".mp3")
                
                with open(temp_path, "wb") as f:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                
                return temp_path
            except Exception as e:
                self.emit("error", message=f"TTS generation error: {e}")
                return None
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(generate())
        finally:
            try:
                loop.close()
            except:
                pass
        
        return result
    
    def play_audio_file(self, audio_path):
        """Play an audio file and block until complete"""
        if not audio_path or not os.path.exists(audio_path):
            return
        
        try:
            self.current_tts_process = subprocess.Popen(
                ["mpv", "--no-terminal", "--no-video", audio_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            self.current_tts_process.wait()
            self.current_tts_process = None
        except FileNotFoundError:
            try:
                import pygame
                pygame.mixer.init(frequency=24000)
                pygame.mixer.music.load(audio_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    pygame.time.wait(50)
                pygame.mixer.quit()
            except ImportError:
                if sys.platform == "win32":
                    subprocess.run(["ffplay", "-nodisp", "-autoexit", audio_path],
                                  capture_output=True)
                else:
                    os.system(f'mpg123 -q "{audio_path}" 2>/dev/null || ffplay -nodisp -autoexit "{audio_path}" 2>/dev/null')
        
        # Cleanup
        try:
            os.unlink(audio_path)
        except:
            pass
    
    def stream_tts_to_player(self, text):
        """
        Stream TTS audio directly to player via stdin pipe.
        Eliminates intermediate file I/O for ~1-3s latency reduction.
        Returns True if successful, False if fallback to file-based needed.
        """
        if not text or not self.streaming_player or self.stop_tts_flag.is_set():
            return False
        
        import asyncio
        
        async def _stream():
            try:
                import edge_tts
                communicate = edge_tts.Communicate(text, self.voice_id)
                
                self.current_tts_process = subprocess.Popen(
                    self.streaming_player,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                
                async for chunk in communicate.stream():
                    if self.stop_tts_flag.is_set():
                        break
                    if chunk["type"] == "audio":
                        try:
                            self.current_tts_process.stdin.write(chunk["data"])
                        except (BrokenPipeError, OSError):
                            break
                
                if self.current_tts_process:
                    try:
                        self.current_tts_process.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
                    try:
                        self.current_tts_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.current_tts_process.terminate()
                    self.current_tts_process = None
                
                return True
            except Exception as e:
                self.emit("error", message=f"TTS streaming error: {e}")
                if self.current_tts_process:
                    try:
                        self.current_tts_process.terminate()
                    except:
                        pass
                    self.current_tts_process = None
                return False
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(_stream())
        finally:
            try:
                loop.close()
            except:
                pass
        
        return result

    def process_phases_async(self, text):
        """
        Hybrid streaming + pre-generation TTS pipeline:
        - Phase 1: Stream directly to player via stdin (~200ms to first audio)
        - Remaining phases: Pre-generate as files while phase 1 plays
        - Falls back to file-based approach if streaming not available
        """
        if self.stop_tts_flag.is_set():
            return
        
        phases = self.split_into_phases(text)
        
        if not phases:
            return
        
        has_streaming = bool(self.streaming_player)
        self.emit("debug", message=f"TTS: {len(phases)} phase(s), streaming={'yes' if has_streaming else 'no'}")
        
        # === Single phase: try streaming first ===
        if len(phases) == 1:
            if has_streaming:
                success = self.stream_tts_to_player(phases[0])
                if success:
                    return
            # Fallback to file-based
            audio_path = self.generate_tts_audio(phases[0])
            if audio_path and not self.stop_tts_flag.is_set():
                self.play_audio_file(audio_path)
            return
        
        # === Multi-phase: stream phase 1 + pre-generate remaining ===
        remaining_phases = phases[1:]
        future_audios = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Pre-generate remaining phases as files in background
            for phase_text in remaining_phases:
                future = executor.submit(self.generate_tts_audio, phase_text)
                future_audios.append(future)
            
            # Phase 1: stream directly for near-instant playback
            phase1_played = False
            if has_streaming:
                phase1_played = self.stream_tts_to_player(phases[0])
            
            if not phase1_played:
                # Fallback: generate file for phase 1
                audio_path = self.generate_tts_audio(phases[0])
                if audio_path and not self.stop_tts_flag.is_set():
                    self.play_audio_file(audio_path)
            
            # Play remaining pre-generated phases (should be ready by now)
            for future in future_audios:
                if self.stop_tts_flag.is_set():
                    # Cancel remaining and cleanup
                    for f in future_audios:
                        if not f.done():
                            f.cancel()
                        else:
                            try:
                                audio = f.result()
                                if audio:
                                    os.unlink(audio)
                            except:
                                pass
                    break
                
                try:
                    audio_path = future.result(timeout=30)
                    if audio_path and not self.stop_tts_flag.is_set():
                        self.play_audio_file(audio_path)
                except Exception as e:
                    self.emit("error", message=f"Phase TTS error: {e}")
    
    def _parse_gemini_chunk(self, chunk):
        """Parse a Gemini response chunk, extracting text and function calls.
        Uses explicit 'is not None' checks to avoid falsy Content/Part objects.
        Returns (text_parts: list[str], func_calls: list, finish_reason)"""
        text_parts = []
        func_calls = []
        finish_reason = None
        
        try:
            candidates = getattr(chunk, 'candidates', None)
            if not candidates:
                return text_parts, func_calls, finish_reason
            
            candidate = candidates[0]
            finish_reason = getattr(candidate, 'finish_reason', None)
            
            content = getattr(candidate, 'content', None)
            if content is None:
                return text_parts, func_calls, finish_reason
            
            parts = getattr(content, 'parts', None)
            if not parts:
                return text_parts, func_calls, finish_reason
            
            for part in parts:
                # Skip thinking/thought parts from gemini-2.5-flash
                if getattr(part, 'thought', False):
                    continue
                # Check function_call using getattr to avoid truthiness issues
                fc = getattr(part, 'function_call', None)
                if fc is not None and getattr(fc, 'name', None):
                    func_calls.append(fc)
                else:
                    t = getattr(part, 'text', None)
                    if t:
                        text_parts.append(t)
        except Exception as e:
            self.emit("debug", message=f"Chunk parse exception: {type(e).__name__}: {e}")
        
        return text_parts, func_calls, finish_reason

    def _dump_chunk_debug(self, chunk, label="chunk"):
        """Dump raw chunk data for debugging empty responses"""
        try:
            candidates = getattr(chunk, 'candidates', None)
            if not candidates:
                self.emit("debug", message=f"[{label}] No candidates. Raw: {str(chunk)[:300]}")
                return
            c = candidates[0]
            fr = getattr(c, 'finish_reason', 'N/A')
            content = getattr(c, 'content', None)
            if content is None:
                self.emit("debug", message=f"[{label}] content=None, finish_reason={fr}")
                return
            parts = getattr(content, 'parts', None)
            if not parts:
                self.emit("debug", message=f"[{label}] parts empty/None, role={getattr(content, 'role', 'N/A')}, finish_reason={fr}")
                return
            for i, part in enumerate(parts):
                fc = getattr(part, 'function_call', None)
                txt = getattr(part, 'text', None)
                self.emit("debug", message=f"[{label}] part[{i}]: text={repr(txt)[:100] if txt else 'None'}, fc={getattr(fc, 'name', None) if fc else 'None'}, type={type(part).__name__}")
        except Exception as e:
            self.emit("debug", message=f"[{label}] dump error: {e}, raw={str(chunk)[:200]}")

    def _try_direct_search_fallback(self, user_text, client, system_instruction, safety_settings, retry_contents, types):
        """
        Last-resort fallback: If Gemini returns empty responses, detect search intent 
        and call web_search directly, then feed results to Gemini WITHOUT tools
        to get a natural language answer.
        Returns response text or None.
        """
        try:
            self.emit("debug", message="Attempting direct web_search fallback...")
            
            # Execute web_search directly with user's text as query
            search_result = self.agent_tools.web_search(user_text)
            
            if not search_result.get("success") or not search_result.get("data", {}).get("results"):
                self.emit("debug", message="Direct search returned no results")
                return None
            
            # Format search results as context
            results = search_result["data"]["results"]
            search_context = f"Ket qua tim kiem cho '{user_text}':\n"
            for i, r in enumerate(results[:5], 1):
                search_context += f"\n{i}. {r.get('title', 'N/A')}\n   {r.get('snippet', 'N/A')}\n   URL: {r.get('url', '')}\n"
            
            # Ask Gemini to summarize WITHOUT tools (avoids the empty response issue)
            self.emit("debug", message=f"Feeding {len(results)} search results to Gemini (no tools)...")
            
            summary_prompt = f"""Nguoi dung hoi: "{user_text}"

Day la ket qua tim kiem tu internet:
{search_context}

Hay tom tat va tra loi cau hoi cua nguoi dung dua tren cac ket qua tren. Tra loi bang tieng Viet, ngan gon va tu nhien. KHONG dung markdown."""

            summary_response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=summary_prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=4096,
                    temperature=0.7,
                    thinking_config=types.ThinkingConfig(thinking_budget=1024)
                )
            )
            
            if summary_response.text:
                self.emit("debug", message=f"Direct search fallback succeeded: {len(summary_response.text)} chars")
                return summary_response.text
            
            # If Gemini still returns nothing, just return raw search snippets
            self.emit("debug", message="Gemini summary failed, returning raw snippets")
            raw_answer = f"Kết quả tìm kiếm cho '{user_text}':\n"
            for i, r in enumerate(results[:3], 1):
                raw_answer += f"{i}. {r.get('title', '')}: {r.get('snippet', '')}\n"
            return raw_answer
            
        except Exception as e:
            self.emit("debug", message=f"Direct search fallback error: {e}")
            return None

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
{self.agent_tools.memory.get_prompt_context()}
THONG TIN HIEN TAI: {now_str}
QUY TAC PHAN HOI:
- KHONG su dung dinh dang markdown (nhu *, _, `).
- Luon su dung cac cong cu (tools) duoc cung cap de tra cuu thoi tiet hoac cac ngay le neu can.
- Neu thong tin hien tai co ve khong chinh xac, hay chu dong kiem tra lai bang cong cu.
- BAT BUOC: Khi nguoi dung ke bat ky su kien/cau chuyen ca nhan nao, GOI memory_save NGAY TRUOC KHI tra loi. Dung ngay cu the (hom nay la {now_str.split(',')[0].strip()}) thay vi 'hom nay'.
- BAT BUOC: Khi nguoi dung hoi ve ban than ho (toi the nao, ban biet gi ve toi, toi da lam gi), GOI memory_list TRUOC roi tra loi dua tren ky uc."""

            # Build conversation history for the new SDK format
            history = []
            for msg in self.conversation.history[:-1]:
                role = "user" if msg["role"] == "user" else "model"
                history.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
            
            # Safety settings - prevent silent blocking of responses
            safety_settings = [
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            ]
            
            # Create chat session
            chat = client.chats.create(
                model='gemini-2.5-flash',
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=[get_gemini_tools()],
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    max_output_tokens=8192,
                    temperature=0.7,
                    safety_settings=safety_settings,
                    thinking_config=types.ThinkingConfig(thinking_budget=2048)
                ),
                history=history
            )
            
            full_text = ""
            function_calls = []
            music_tool_called = False
            chunk_count = 0
            last_finish_reason = None
            
            # Stream the response - collect all text and function calls
            last_chunk = None
            for chunk in chat.send_message_stream(text):
                chunk_count += 1
                last_chunk = chunk
                
                text_parts, func_calls, fr = self._parse_gemini_chunk(chunk)
                if fr:
                    last_finish_reason = fr
                if text_parts:
                    full_text += ''.join(text_parts)
                for fc in func_calls:
                    function_calls.append(fc)
                    self.emit("debug", message=f"Found function call: {fc.name}")
                
                # Also try chunk.text as fallback (wrapped in try-except for safety)
                if not full_text and not func_calls:
                    try:
                        if chunk.text:
                            full_text += chunk.text
                    except (ValueError, AttributeError):
                        pass  # chunk.text raises ValueError when response has function calls
            
            self.emit("debug", message=f"Stream finished: {chunk_count} chunks, {len(function_calls)} function calls, text len={len(full_text)}, finish_reason={last_finish_reason}")
            
            # Dump raw chunk data if response is empty (critical for diagnosing issues)
            if not full_text and not function_calls and chunk_count > 0 and last_chunk:
                self._dump_chunk_debug(last_chunk, "empty_stream")
                try:
                    candidate = last_chunk.candidates[0] if last_chunk.candidates else None
                    if candidate:
                        if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                            ratings = [(r.category, r.probability) for r in candidate.safety_ratings]
                            self.emit("debug", message=f"Safety ratings: {ratings}")
                    if hasattr(last_chunk, 'prompt_feedback') and last_chunk.prompt_feedback:
                        self.emit("debug", message=f"Prompt feedback: {last_chunk.prompt_feedback}")
                except Exception as diag_err:
                    self.emit("debug", message=f"Diagnostic error: {diag_err}")
            
            # If there were function calls, execute them and get the final answer
            if function_calls:
                self.emit("debug", message=f"Processing {len(function_calls)} function call(s)...")
                self.emit("tool_call", tool_name=function_calls[0].name)
                
                # Execute tools
                function_responses = []
                for fc in function_calls:
                    tool_name = fc.name
                    tool_args = dict(fc.args) if fc.args else {}
                    self.emit("debug", message=f"Calling {tool_name} with {tool_args}...")
                    result = self.agent_tools.execute_tool(tool_name, tool_args)
                    self.emit("debug", message=f"Tool result: {str(result)[:200]}...")
                    
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
                
                # Send tool results back to Gemini - may need multiple rounds
                max_rounds = 3
                for round_num in range(max_rounds):
                    self.emit("debug", message=f"Sending function responses to Gemini (round {round_num + 1})...")
                    
                    new_function_calls = []
                    for chunk in chat.send_message_stream(function_responses):
                        text_parts, func_calls, _ = self._parse_gemini_chunk(chunk)
                        if text_parts:
                            full_text += ''.join(text_parts)
                        new_function_calls.extend(func_calls)
                    
                    # If no more function calls, we're done
                    if not new_function_calls:
                        break
                    
                    # Execute new function calls
                    self.emit("debug", message=f"Gemini wants {len(new_function_calls)} more function call(s)...")
                    self.emit("tool_call", tool_name=new_function_calls[0].name)
                    function_responses = []
                    for fc in new_function_calls:
                        tool_name = fc.name
                        tool_args = dict(fc.args) if fc.args else {}
                        self.emit("debug", message=f"Calling {tool_name} with {tool_args}...")
                        result = self.agent_tools.execute_tool(tool_name, tool_args)
                        self.emit("debug", message=f"Tool result: {str(result)[:200]}...")
                        
                        if result.get("action") and result["action"].startswith("MUSIC_"):
                            self.emit("music_action", action=result["action"], data=result.get("data", {}))
                            music_tool_called = True
                        
                        function_responses.append(
                            types.Part.from_function_response(
                                name=tool_name,
                                response={"result": json.dumps(result, ensure_ascii=False)}
                            )
                        )
                
                self.emit("debug", message=f"Final text after tools: '{full_text[:100] if full_text else 'EMPTY'}'")
            
            # Clean and send to TTS once
            if full_text:
                clean_text = self.clean_text_for_tts(full_text)
                if clean_text:
                    self.emit("llm_response", text=clean_text)
                    self.tts_queue.put(clean_text)
            elif function_calls:
                # Fallback: If no text after function calls, try non-streaming request
                self.emit("debug", message="No text from streaming, trying non-streaming fallback...")
                try:
                    # Send a simple follow-up to get text response
                    fallback_response = chat.send_message("Vui long tra loi bang van ban dua tren ket qua cong cu.")
                    if fallback_response.text:
                        full_text = fallback_response.text
                        clean_text = self.clean_text_for_tts(full_text)
                        if clean_text:
                            self.emit("llm_response", text=clean_text)
                            self.tts_queue.put(clean_text)
                    else:
                        self.emit("debug", message="WARNING: Fallback also returned no text")
                except Exception as fb_error:
                    self.emit("debug", message=f"Fallback error: {fb_error}")
            else:
                self.emit("debug", message=f"WARNING: No text response from Gemini (finish_reason={last_finish_reason})")
                
                # Retry with a fresh direct API call (not the same chat session)
                # Using a direct generate_content call avoids chat session state issues
                self.emit("debug", message="Retrying with direct API call (non-streaming, fresh context)...")
                try:
                    # Build contents from conversation history for a fresh call
                    retry_contents = []
                    for msg in self.conversation.history:
                        role = "user" if msg["role"] == "user" else "model"
                        retry_contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg["content"])]))
                    
                    # Add a nudge to encourage response
                    if retry_contents and retry_contents[-1].role == "user":
                        # Replace last user message with a slightly modified version
                        retry_contents[-1] = types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=f"{text}\n(Hãy trả lời bằng tiếng Việt.)")]
                        )
                    
                    retry_response = client.models.generate_content(
                        model='gemini-2.5-flash',
                        contents=retry_contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            tools=[get_gemini_tools()],
                            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                            max_output_tokens=8192,
                            temperature=0.9,
                            safety_settings=safety_settings,
                            thinking_config=types.ThinkingConfig(thinking_budget=2048)
                        )
                    )
                    
                    # Check for function calls in retry using robust parser
                    retry_text_parts, retry_fc, retry_fr = self._parse_gemini_chunk(retry_response)
                    if retry_text_parts:
                        full_text += ''.join(retry_text_parts)
                    
                    # Dump debug if retry also empty
                    if not retry_text_parts and not retry_fc:
                        self._dump_chunk_debug(retry_response, "empty_retry")
                        self.emit("debug", message=f"Retry finish_reason={retry_fr}")
                    
                    if retry_fc:
                        self.emit("debug", message=f"Retry found {len(retry_fc)} function call(s)")
                        self.emit("tool_call", tool_name=retry_fc[0].name)
                        # Execute retry function calls
                        function_responses_parts = []
                        for fc in retry_fc:
                            tool_name = fc.name
                            tool_args = dict(fc.args) if fc.args else {}
                            self.emit("debug", message=f"Calling {tool_name} with {tool_args}...")
                            result = self.agent_tools.execute_tool(tool_name, tool_args)
                            self.emit("debug", message=f"Tool result: {str(result)[:200]}...")
                            if result.get("action") and result["action"].startswith("MUSIC_"):
                                self.emit("music_action", action=result["action"], data=result.get("data", {}))
                                music_tool_called = True
                            function_responses_parts.append(
                                types.Part.from_function_response(
                                    name=tool_name,
                                    response={"result": json.dumps(result, ensure_ascii=False)}
                                )
                            )
                        # Get final text from tool results via fresh call
                        # Build full context with tool call and response for the follow-up
                        tool_call_content = types.Content(
                            role="model",
                            parts=[types.Part.from_function_call(name=fc.name, args=dict(fc.args) if fc.args else {}) for fc in retry_fc]
                        )
                        tool_response_content = types.Content(
                            role="user",
                            parts=function_responses_parts
                        )
                        final_contents = retry_contents + [tool_call_content, tool_response_content]
                        final_resp = client.models.generate_content(
                            model='gemini-2.5-flash',
                            contents=final_contents,
                            config=types.GenerateContentConfig(
                                system_instruction=system_instruction,
                                max_output_tokens=8192,
                                temperature=0.9,
                                safety_settings=safety_settings,
                                thinking_config=types.ThinkingConfig(thinking_budget=2048)
                            )
                        )
                        if final_resp.text:
                            full_text = final_resp.text
                    
                    if full_text:
                        clean_text = self.clean_text_for_tts(full_text)
                        if clean_text:
                            self.emit("llm_response", text=clean_text)
                            self.tts_queue.put(clean_text)
                        self.emit("debug", message=f"Retry succeeded: text len={len(full_text)}")
                    else:
                        self.emit("debug", message="WARNING: Retry also returned no response")
                        
                        # === DIRECT TOOL FALLBACK ===
                        # If Gemini refuses to respond, detect search intent and call web_search directly
                        # Then feed results to Gemini without tools to get a natural language summary
                        search_result = self._try_direct_search_fallback(text, client, system_instruction, safety_settings, retry_contents, types)
                        if search_result:
                            full_text = search_result
                            clean_text = self.clean_text_for_tts(full_text)
                            self.emit("llm_response", text=clean_text)
                            self.tts_queue.put(clean_text)
                        else:
                            full_text = "Xin lỗi, tôi không nhận được phản hồi. Bạn thử lại nhé."
                            clean_text = self.clean_text_for_tts(full_text)
                            self.emit("llm_response", text=clean_text)
                            self.tts_queue.put(clean_text)
                except Exception as retry_err:
                    self.emit("debug", message=f"Retry error: {retry_err}")
                    
                    # Try direct search fallback even on retry exception
                    try:
                        from google import genai as genai_fb
                        from google.genai import types as types_fb
                        client_fb = genai_fb.Client(api_key=self.llm_api_key)
                        search_result = self._try_direct_search_fallback(text, client_fb, self.system_prompt, [], [], types_fb)
                        if search_result:
                            full_text = search_result
                            clean_text = self.clean_text_for_tts(full_text)
                            self.emit("llm_response", text=clean_text)
                            self.tts_queue.put(clean_text)
                        else:
                            raise Exception("Direct search fallback also failed")
                    except Exception:
                        full_text = "Xin lỗi, có lỗi xảy ra. Bạn thử lại nhé."
                        clean_text = self.clean_text_for_tts(full_text)
                        self.emit("llm_response", text=clean_text)
                        self.tts_queue.put(clean_text)
            
            return full_text, music_tool_called

        except Exception as e:
            self.emit("error", message=f"Gemini Streaming Error: {e}")
            fallback = "Xin lỗi, có lỗi xảy ra."
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
        """Text-to-speech - uses streaming if available, otherwise file-based"""
        # Try direct streaming first for lower latency
        if self.streaming_player:
            success = self.stream_tts_to_player(text)
            if success:
                return
        
        # Fallback to file-based TTS
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
