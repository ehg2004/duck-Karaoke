#!/usr/bin/env python3
"""Real-time mic capture + VAD + optional RNNoise + transcription (ROS removed)."""

from time import time_ns, sleep
from datetime import datetime
from queue import Queue, Empty
from threading import Lock

import numpy as np
import torch
import torchaudio
from scipy.signal import decimate
import pyaudio
from rnnoise_wrapper import RNNoise
from openai import OpenAI


class AudioTranscriber:
    def __init__(
        self,
        sample_rate=48000,
        channels=1,
        vad_timeout_ms=3000,
        vad_threshold=0.65,
        verbose=False,
        disable_denoiser=True,
        device="cpu",
        save_audio=True,
        audio_save_dir="debug_audio",
    ):
        self.device = device
        self.verbose = verbose
        self.disable_denoiser = disable_denoiser
        self.save_audio = save_audio
        self.audio_save_dir = audio_save_dir
        self.segment_counter = 0

        self.SAMPLE_RATE = sample_rate
        self.CHANNELS = channels
        self.FORMAT = pyaudio.paInt16
        self.CHUNK_SIZE = int(self.SAMPLE_RATE / 10)

        self.vad_timeout_ns = int(vad_timeout_ms * 1_000_000)
        self.vad_threshold = float(vad_threshold)

        self.audio = pyaudio.PyAudio()
        self.audio_queue = Queue(maxsize=1000)
        self.queue_lock = Lock()
        self.transcription_output_queue = Queue(maxsize=1000)  # Output queue for transcriptions

        self.data = np.array([], dtype=np.int16)
        self.is_speaking = False
        self.t_last = time_ns()
        self.t0 = self.t_last

        # Create debug audio directory if saving is enabled
        if self.save_audio:
            import os
            os.makedirs(self.audio_save_dir, exist_ok=True)
            print(f"[{datetime.now()}] Audio persistence enabled: {self.audio_save_dir}")

        self.denoiser = None
        if not self.disable_denoiser:
            self.denoiser = RNNoise('librnnoise_default.so.0.4.1')

        self.vad_model, self.vad_utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad',
            force_reload=False,
            verbose=False)
        self.vad_utils = None
        # (
        #     self.get_speech_timestamps,
        #     self.save_audio,
        #     self.read_audio,
        #     self.VADIterator,
        #     self.collect_chunks,
        # ) = self.vad_utils

        self.asr_backend = None
        self._load_asr_model()

        self.stream = self.audio.open(
            format=self.FORMAT,
            channels=self.CHANNELS,
            rate=self.SAMPLE_RATE,
            input=True,
            frames_per_buffer=self.CHUNK_SIZE,
            stream_callback=self.audio_callback,
        )
        self.stream.start_stream()

        print(f"[{datetime.now()}] Audio stream started @ {self.SAMPLE_RATE} Hz")

    def _load_asr_model(self):
        try:
            self.openai_client = OpenAI(
                base_url="http://127.0.0.1:52625/v1",
                api_key="flm"
            )
            self.asr_backend = 'openai_local_whisper'
            print("ASR backend: OpenAI API (Local FastFlowLM Whisper)")
            return
        except Exception as e:
            print(f"OpenAI local Whisper API initialization failed: {e}")

        raise RuntimeError('OpenAI local Whisper API not available. Ensure FastFlowLM is running on http://127.0.0.1:52625')

    def stop(self):
        """Gracefully stop the audio stream and clean up resources."""
        try:
            if hasattr(self, 'stream') and self.stream:
                try:
                    if self.stream.is_active():
                        self.stream.stop_stream()
                    self.stream.close()
                except Exception as e:
                    print(f"[{datetime.now()}] Error closing stream: {e}")
            
            if hasattr(self, 'audio') and self.audio:
                try:
                    self.audio.terminate()
                except Exception as e:
                    print(f"[{datetime.now()}] Error terminating PyAudio: {e}")
            
            print(f"[{datetime.now()}] Audio stream stopped")
        except Exception as e:
            print(f"[{datetime.now()}] Error during stop: {e}")

    def audio_callback(self, in_data, frame_count, time_info, status):
        audio_int16 = np.frombuffer(in_data, dtype=np.int16)
        with self.queue_lock:
            if not self.audio_queue.full():
                self.audio_queue.put((time_ns(), audio_int16))
        return (None, pyaudio.paContinue)

    def process_audio_from_queue(self):
        if self.audio_queue.empty():
            return

        try:
            timestamp, audio_data = self.audio_queue.get(timeout=0.1)
        except Empty:
            return

        speech_presence = self.evaluate_speech_presence(audio_data)
        now_ns = timestamp

        if speech_presence:
            self.data = np.concatenate([self.data, audio_data])
            self.t_last = now_ns
            if not self.is_speaking:
                self.is_speaking = True
                self.t0 = now_ns
                if self.verbose:
                    print(f"[{datetime.now()}] Speaker detected")
            else:
                if self.verbose:
                    print(
                        f"[{datetime.now()}] Speaker present, elapsed {(now_ns - self.t0) / 1_000_000:.0f} ms"
                    )
            return

        if self.is_speaking and not speech_presence:
            self.data = np.concatenate([self.data, audio_data])
            if self.verbose:
                print(f"[{datetime.now()}] Possible silence")

            if now_ns - self.t_last >= self.vad_timeout_ns:
                self.is_speaking = False
                segment = self.data.copy()
                self.data = np.array([], dtype=np.int16)

                if len(segment) == 0:
                    return

                if not self.disable_denoiser and self.denoiser is not None:
                    segment = self.remove_noise(segment)

                segment16k = self.decimate_cast(segment, passthrough=False)
                
                # Save audio segments if persistence is enabled
                if self.save_audio:
                    self._save_audio_segment(segment, segment16k)
                
                text = self.transcribe_audio(segment16k)

                # Push transcription result to output queue with timestamp
                timestamp_seconds = (now_ns - self.t0) / 1_000_000_000
                transcription_result = {
                    "timestamp": timestamp_seconds,
                    "text": text,
                    "score": 0.0  # Placeholder for ASR confidence
                }
                
                try:
                    self.transcription_output_queue.put(transcription_result, block=False)
                except:
                    pass  # Drop if queue is full

                print(
                    f"[{datetime.now()}] Finalized segment {(now_ns - self.t0) / 1_000_000:.0f} ms, transcription: {text}"
                )

    def evaluate_speech_presence(self, audio_int16):
        if len(audio_int16) < 512 * 3:
            return False

        audio_float = self.int2float(audio_int16)
        decimated = decimate(x=audio_float, q=3, zero_phase=True)
        sample = decimated[:512].copy()

        confidence = self.vad_evaluate(sample)
        if self.verbose:
            print(f"VAD confidence: {confidence:.3f}")

        return bool(confidence > self.vad_threshold)

    def vad_evaluate(self, audio_float32):
        with torch.no_grad():
            return self.vad_model(torch.from_numpy(np.ascontiguousarray(audio_float32)), 16000).item()

    def decimate_cast(self, audio_int16_48khz, passthrough=False):
        if passthrough:
            return audio_int16_48khz

        audio_float = self.int2float(audio_int16_48khz)
        decimated = decimate(x=audio_float, q=3, zero_phase=True)
        return self.float2int(decimated)

    @staticmethod
    def int2float(sound):
        """Convert int16 audio array to float32 (-1.0 to 1.0 range)."""
        abs_max = np.abs(sound).max() if sound.size > 0 else 0.0
        sound = sound.astype('float32')
        if abs_max > 0:
            sound = sound / 32768.0
        sound = sound.squeeze()  # Remove extra dimensions if present
        return sound

    @staticmethod
    def float2int(sound):
        """Convert float32 audio array to int16.
        
        NOTE: Clipping is intentionally disabled. Audio values > 1.0 or < -1.0 
        are allowed to overflow naturally to preserve dynamic range.
        """
        if not ((sound.dtype == np.float32) or (sound.dtype == np.float64)):
            sound = np.asarray(sound, dtype=np.float32)
        
        # DO NOT CLIP - allows natural overflow for better audio quality
        sound = np.round(sound * 32768.0)  # Use 32768 for full int16 range
        return sound.astype(np.int16, copy=False).squeeze()

    def remove_noise(self, audio_np):
        if len(audio_np) == 0:
            return audio_np

        if audio_np.dtype != np.int16:
            audio_np = self.float2int(audio_np)

        audio_bytes = audio_np.tobytes()
        frame_size = 960
        processed_frames = []

        for i in range(0, len(audio_bytes), frame_size):
            frame = audio_bytes[i : i + frame_size]
            if len(frame) < frame_size:
                frame += b"\x00" * (frame_size - len(frame))

            _, processed_frame = self.filter_frames(frame)
            if processed_frame.size > 0:
                processed_frames.append(processed_frame)

        if not processed_frames:
            return np.array([], dtype=np.int16)

        return np.concatenate(processed_frames)

    def filter_frames(self, frame_bytes):
        #should test if self.denoiser is None here, but in practice this should never be called if disable_denoiser is True
        vad_prob, processed_bytes = self.denoiser.filter_frame(frame_bytes) # type: ignore
        return vad_prob, np.frombuffer(processed_bytes, dtype=np.int16)

    def audio_padding(self, audio):
        """Pad audio to ensure minimum 30 seconds for better Whisper performance."""
        min_duration_sec = 30
        sample_rate_16k = 16000
        min_samples = sample_rate_16k * min_duration_sec
        
        if audio.shape[-1] < min_samples:
            pad_length = min_samples - audio.shape[-1]
            if self.verbose:
                print(f"[{datetime.now()}] Audio padded from {audio.shape[-1]} to {min_samples} samples")
            return np.pad(audio, (0, pad_length), mode="constant")
        return audio

    def _save_audio_segment(self, audio_48k, audio_16k):
        """Save audio segment to disk for debugging (both 48k and 16k versions)."""
        try:
            import soundfile as sf
            
            self.segment_counter += 1
            
            # Save 48kHz version (original)
            filename_48k = f"{self.audio_save_dir}/segment_{self.segment_counter:04d}_48k.wav"
            audio_float_48k = self.int2float(audio_48k)
            sf.write(filename_48k, audio_float_48k, 48000, format='WAV')
            
            # Save 16kHz version (decimated for ASR)
            filename_16k = f"{self.audio_save_dir}/segment_{self.segment_counter:04d}_16k.wav"
            audio_float_16k = self.int2float(audio_16k)
            sf.write(filename_16k, audio_float_16k, 16000, format='WAV')
            
            print(f"[{datetime.now()}] Saved audio segment {self.segment_counter} (48k: {len(audio_48k)} samples, 16k: {len(audio_16k)} samples)")
        except Exception as e:
            print(f"[{datetime.now()}] Error saving audio segment: {e}")

    def transcribe_audio(self, audio_int16_16khz):
        if self.asr_backend == 'openai_local_whisper':
            return self._transcribe_with_openai_local_whisper(audio_int16_16khz)
        
        return ''

    def _transcribe_with_openai_local_whisper(self, audio_int16_16khz):
        try:
            import soundfile as sf
            import os
            
            # Apply padding to ensure min 30s of audio
            audio_int16_16khz = self.audio_padding(audio_int16_16khz)
            
            # Convert int16 to float32
            audio_float = self.int2float(audio_int16_16khz)
            
            # Save to debug directory instead of /tmp if audio persistence is enabled
            if self.save_audio:
                temp_path = f"{self.audio_save_dir}/transcribe_input_{self.segment_counter:04d}.wav"
                sf.write(temp_path, audio_float, 16000, format='WAV')
                print(f"[{datetime.now()}] Transcription input saved: {temp_path}")
                should_clean_up = False
            else:
                # Use system temp if not saving
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                    sf.write(f.name, audio_float, 16000, format='WAV')
                    temp_path = f.name
                should_clean_up = True
            
            # Call local OpenAI API (FastFlowLM)
            with open(temp_path, 'rb') as f:
                resp = self.openai_client.audio.transcriptions.create(
                    model="whisper-v3",
                    file=f,
                )
            
            # Clean up temp file only if using system temp directory
            if should_clean_up:
                os.unlink(temp_path)
            
            return resp.text.strip()
        except Exception as e:
            print(f"OpenAI local Whisper transcription failed: {e}")
            import traceback
            traceback.print_exc()
            return ''



def main():
    print(f"CUDA available: {torch.cuda.is_available()}")
    transcriber = AudioTranscriber(verbose=True, vad_timeout_ms=3000, vad_threshold=0.5, disable_denoiser=True,device="cuda" if torch.cuda.is_available() else "cpu")

    try:
        while True:
            transcriber.process_audio_from_queue()
            sleep(0.01)
    except KeyboardInterrupt:
        print('Interrupted by user')
    finally:
        transcriber.stop()


if __name__ == '__main__':
    main()
