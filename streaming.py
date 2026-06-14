"""即時 streaming Whisper — 用 faster-whisper 跑滑動視窗,每 3 秒吐一次字幕。

設計:
- 背景 thread 1: sounddevice 持續錄音到 ring buffer
- 背景 thread 2: 每 3 秒從 buffer 取最後 5 秒音檔丟 whisper, 1 秒回字串
- callback 把新字串送到 main thread (textual app) 更新 UI
"""
from __future__ import annotations
import threading
import queue
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
WINDOW_SEC = 5.0      # 每次給 whisper 看的音檔長度
STRIDE_SEC = 3.0      # 每隔幾秒吐一次結果
DTYPE = "int16"


class StreamingTranscriber:
    """背景錄音 + 滑動視窗轉錄 + callback。"""

    def __init__(
        self,
        on_text: Callable[[str], None],
        model_size: str = "base",
        compute_type: str = "int8",  # M 系列 CPU 友好,也可 float16/int8_float16
        language: Optional[str] = None,  # None = auto detect; 設 "en" / "zh" 加速
    ):
        from faster_whisper import WhisperModel
        self.model = WhisperModel(model_size, device="cpu", compute_type=compute_type)
        self.on_text = on_text
        self.language = language

        # ring buffer for audio
        self.buffer = np.zeros(int(SAMPLE_RATE * 60), dtype=np.int16)  # 60 秒滾動
        self.write_pos = 0
        self.total_samples = 0
        self._lock = threading.Lock()

        self._running = False
        self._stream: Optional[sd.InputStream] = None
        self._worker: Optional[threading.Thread] = None

        # full-meeting recording
        self.full_recording: list[np.ndarray] = []

    def _audio_callback(self, indata, frames, time_info, status):
        with self._lock:
            samples = indata[:, 0].copy()
            self.full_recording.append(samples.copy())
            n = len(samples)
            end = self.write_pos + n
            if end <= len(self.buffer):
                self.buffer[self.write_pos:end] = samples
            else:
                first = len(self.buffer) - self.write_pos
                self.buffer[self.write_pos:] = samples[:first]
                self.buffer[:n - first] = samples[first:]
            self.write_pos = end % len(self.buffer)
            self.total_samples += n

    def _get_window(self, seconds: float) -> np.ndarray:
        """從 ring buffer 取最後 N 秒。"""
        with self._lock:
            n = int(seconds * SAMPLE_RATE)
            n = min(n, self.total_samples)
            if n == 0:
                return np.array([], dtype=np.int16)
            # 從 write_pos 往回取 n 個 sample
            if self.write_pos >= n:
                return self.buffer[self.write_pos - n:self.write_pos].copy()
            else:
                tail = self.buffer[-(n - self.write_pos):].copy()
                head = self.buffer[:self.write_pos].copy()
                return np.concatenate([tail, head])

    def _transcribe_worker(self):
        last_text = ""
        while self._running:
            time.sleep(STRIDE_SEC)
            window = self._get_window(WINDOW_SEC)
            if len(window) < SAMPLE_RATE * 1.0:  # 至少 1 秒才跑
                continue
            audio_float = window.astype(np.float32) / 32768.0
            try:
                segments, _info = self.model.transcribe(
                    audio_float,
                    language=self.language,
                    beam_size=1,         # 快,可選 5 更準
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 300},
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                if text and text != last_text:
                    self.on_text(text)
                    last_text = text
            except Exception as e:
                self.on_text(f"[轉錄錯誤: {e}]")

    def start(self):
        self._running = True
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            callback=self._audio_callback,
        )
        self._stream.start()
        self._worker = threading.Thread(target=self._transcribe_worker, daemon=True)
        self._worker.start()

    def stop(self) -> np.ndarray:
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
        if self._worker:
            self._worker.join(timeout=5)
        with self._lock:
            if self.full_recording:
                return np.concatenate(self.full_recording, axis=0)
            return np.array([], dtype=np.int16)

    def save_full(self, path: Path):
        from scipy.io import wavfile
        audio = self.stop() if self._running else np.concatenate(self.full_recording, axis=0)
        wavfile.write(str(path), SAMPLE_RATE, audio)
