"""背景錄音模組 — 全程錄成 .wav，講者切段時把對應時間範圍切出來給 Whisper。"""
from __future__ import annotations
import sounddevice as sd
import numpy as np
from scipy.io import wavfile
import threading
import time
from pathlib import Path


class BackgroundRecorder:
    """全程錄音 + 記錄切段時間戳。"""

    SAMPLE_RATE = 16000  # Whisper 偏好 16kHz
    CHANNELS = 1

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frames: list[np.ndarray] = []
        self.start_time: float | None = None
        self.segments: list[dict] = []  # [{label, start_sec, end_sec}]
        self._stream = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        with self._lock:
            self.frames.append(indata.copy())

    def start(self):
        self.start_time = time.time()
        self._stream = sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=self.CHANNELS,
            dtype="int16",
            callback=self._callback,
        )
        self._stream.start()

    def elapsed(self) -> float:
        return time.time() - self.start_time if self.start_time else 0.0

    def mark_segment(self, label: str) -> dict:
        """講者結束時呼叫,記下切段時間。回傳該段 dict。"""
        now = self.elapsed()
        prev_end = self.segments[-1]["end_sec"] if self.segments else 0.0
        seg = {"label": label, "start_sec": prev_end, "end_sec": now}
        self.segments.append(seg)
        return seg

    def stop(self) -> Path:
        if self._stream:
            self._stream.stop()
            self._stream.close()
        with self._lock:
            audio = np.concatenate(self.frames, axis=0) if self.frames else np.array([])
        out_path = self.output_dir / f"meeting_{int(self.start_time)}.wav"
        wavfile.write(out_path, self.SAMPLE_RATE, audio)
        return out_path

    def extract_segment(self, audio_path: Path, seg: dict) -> Path:
        """從整檔錄音切出指定段落為新 wav。"""
        sr, audio = wavfile.read(audio_path)
        start_sample = int(seg["start_sec"] * sr)
        end_sample = int(seg["end_sec"] * sr)
        clip = audio[start_sample:end_sample]
        slug = seg["label"].replace(" ", "_").replace("/", "_")
        out = self.output_dir / f"seg_{slug}.wav"
        wavfile.write(out, sr, clip)
        return out
