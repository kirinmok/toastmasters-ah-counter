#!/usr/bin/env python3
"""極簡測試 — 不用 textual,純驗證:麥克風能錄、faster-whisper 能轉、counter 能算。

跑法:
    cd ~/projects/toastmasters_ah_counter
    python3 minimal_test.py

操作: 按 Ctrl+C 結束,會印出最後的逐字稿 + filler 統計。
"""
import os
# 避免 macOS Python 3.12 multiprocessing fd 衝突
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

import multiprocessing
try:
    multiprocessing.set_start_method("spawn", force=True)
except RuntimeError:
    pass

import time
import threading
import numpy as np
import sounddevice as sd

print("✅ 載入 faster-whisper (首次可能要等 5 秒)...")
from faster_whisper import WhisperModel
model = WhisperModel("base", device="cpu", compute_type="int8")
print("✅ 模型載入完成")

from counter import load_fillers, count_chinese, count_english
fillers_zh, fillers_en = load_fillers()

SAMPLE_RATE = 16000
buffer = []
lock = threading.Lock()
running = True

def audio_cb(indata, frames, t, status):
    with lock:
        buffer.append(indata[:, 0].copy())

print("🎤 開始錄音 (按 Ctrl+C 結束)...")
print("   對麥克風念:")
print('   "Um you know like so today is going to be great. 那個, 然後, 就是, 嗯."')
print()

stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", callback=audio_cb)
stream.start()

full_transcript = ""
try:
    last_text = ""
    while running:
        time.sleep(3)
        with lock:
            if not buffer:
                continue
            window = np.concatenate(buffer[-50:]) if buffer else np.array([])
        if len(window) < SAMPLE_RATE:
            continue
        audio_f32 = window.astype(np.float32) / 32768.0
        segments, _ = model.transcribe(
            audio_f32, beam_size=1, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        if text and text != last_text:
            print(f"📝 {text}")
            full_transcript += " " + text
            last_text = text
            # 即時 filler 統計
            zh = count_chinese(full_transcript, fillers_zh)
            en = count_english(full_transcript, fillers_en)
            total = sum(zh.values()) + sum(en.values())
            print(f"   📊 filler 總計={total}  ZH={dict(zh)}  EN={dict(en)}")
except KeyboardInterrupt:
    print("\n⏹️  結束錄音")
finally:
    stream.stop()
    stream.close()

print("\n" + "=" * 50)
print("最終逐字稿:")
print(full_transcript.strip())
print()
zh = count_chinese(full_transcript, fillers_zh)
en = count_english(full_transcript, fillers_en)
print(f"中文 filler: {dict(zh)}")
print(f"英文 filler: {dict(en)}")
print(f"總計: {sum(zh.values()) + sum(en.values())}")
