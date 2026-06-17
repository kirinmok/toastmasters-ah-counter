#!/usr/bin/env python3
"""Toastmasters Ah Counter v2 — Web GUI

每位講者一個錄音按鍵,按下開始、再按結束、立刻顯示 filler 表。
"""
from __future__ import annotations
import os
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["OMP_NUM_THREADS"] = "1"

import sys
import json
import time
import asyncio
import threading
from pathlib import Path
from datetime import datetime
from collections import Counter
from typing import Optional

import numpy as np
import sounddevice as sd
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# 用 v1 既有模組
HERE = Path(__file__).parent
V1 = HERE.parent
sys.path.insert(0, str(V1))

from counter import load_fillers, count_chinese, count_english  # noqa: E402
from script_gen import build_report_script  # noqa: E402

# faster-whisper 共用單一 model instance (省記憶體)
MODEL_SIZE = os.environ.get("AH_MODEL", "base")  # 用 AH_MODEL=small 升級
print(f"Loading faster-whisper {MODEL_SIZE} model...", flush=True)
from faster_whisper import WhisperModel  # noqa: E402
MODEL = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
print("Model ready ✅", flush=True)

FILLERS_ZH, FILLERS_EN = load_fillers()
SAMPLE_RATE = 16000

# ===== 全域狀態 =====
class SpeakerSession:
    def __init__(self, idx: int, name: str, role: str, language: str = "auto"):
        self.idx = idx
        self.name = name
        self.role = role
        # faster-whisper 只認 ISO 語言代碼,把 auto/mixed/空字串全當 None (自動偵測)
        if language in (None, "", "auto", "mixed", "auto-detect"):
            self.language = None
        else:
            self.language = language
        self.audio_chunks: list[np.ndarray] = []
        self.transcript = ""
        self.fillers: Counter = Counter()
        self.is_recording = False
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, t, status):
        with self._lock:
            self.audio_chunks.append(indata[:, 0].copy())

    def start(self):
        if self.is_recording:
            return
        self.is_recording = True
        self.start_time = time.time()
        self.audio_chunks = []
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            callback=self._callback,
        )
        self.stream.start()

    def stop_and_analyze(self) -> dict:
        if not self.is_recording:
            return self.to_dict()
        self.is_recording = False
        self.end_time = time.time()
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        # 轉錄
        with self._lock:
            audio = np.concatenate(self.audio_chunks) if self.audio_chunks else np.array([], dtype=np.int16)
        if len(audio) < SAMPLE_RATE // 2:
            self.transcript = "(no audio)"
        else:
            try:
                audio_f32 = audio.astype(np.float32) / 32768.0
                # 為了抓 um/uh, 把 VAD 關掉 + 加 initial_prompt 告訴 Whisper 別過濾 filler
                segments, _ = MODEL.transcribe(
                    audio_f32,
                    language=self.language,
                    beam_size=5,  # 提高精度
                    vad_filter=False,  # 關掉 VAD, 避免 um/uh 被當無聲過濾
                    condition_on_previous_text=False,
                    initial_prompt="Um, uh, like, so, you know, actually, basically.",
                )
                self.transcript = " ".join(s.text.strip() for s in segments).strip()
            except Exception as e:
                self.transcript = f"[error: {e}]"
        # 統計
        zh = count_chinese(self.transcript, FILLERS_ZH)
        en = count_english(self.transcript, FILLERS_EN)
        self.fillers = Counter()
        self.fillers.update(zh)
        self.fillers.update(en)
        return self.to_dict()

    def duration(self) -> float:
        if not self.start_time:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time

    def to_dict(self) -> dict:
        return {
            "idx": self.idx,
            "name": self.name,
            "role": self.role,
            "is_recording": self.is_recording,
            "duration_sec": self.duration(),
            "transcript": self.transcript,
            "fillers": dict(self.fillers),
            "total_fillers": sum(self.fillers.values()),
            "started": self.start_time is not None,
            "ended": self.end_time is not None,
        }


# 全域 session 容器
SPEAKERS: list[SpeakerSession] = []
AGENDA: dict = {}


def load_meta_only(path: Path):
    """載入會議 metadata + 開場詞。若 JSON 已含 speakers 直接預填(免 OCR);沒有就空等 OCR。"""
    global SPEAKERS, AGENDA
    AGENDA = json.loads(path.read_text(encoding="utf-8"))
    SPEAKERS = []
    # 若 agenda 已含實際講者(KIRIN 手寫或從 OCR 預先解析過),直接吃進去
    for i, sp in enumerate(AGENDA.get("speakers", [])):
        SPEAKERS.append(SpeakerSession(
            idx=i,
            name=sp.get("speaker", f"Speaker {i+1}"),
            role=sp.get("role", ""),
            language=sp.get("language", "auto"),
        ))


# ===== FastAPI =====
app = FastAPI(title="Ah Counter v2")
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (HERE / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/agenda")
def api_agenda():
    return JSONResponse({
        "meeting": AGENDA.get("meeting_no"),
        "date": AGENDA.get("date"),
        "club": AGENDA.get("club"),
        "opening_speech": AGENDA.get("opening_speech", ""),
        "speakers": [s.to_dict() for s in SPEAKERS],
    })


@app.post("/api/speaker/{idx}/start")
def api_start(idx: int):
    sp = _get_speaker(idx)
    # 確保只有一個在錄(避免麥克風衝突)
    for other in SPEAKERS:
        if other.idx != idx and other.is_recording:
            return JSONResponse(
                {"error": f"另一位 {other.name} 正在錄音,請先停止"},
                status_code=400,
            )
    sp.start()
    return sp.to_dict()


@app.post("/api/speaker/{idx}/stop")
def api_stop(idx: int):
    sp = _get_speaker(idx)
    return sp.stop_and_analyze()


@app.get("/api/speaker/{idx}")
def api_get(idx: int):
    return _get_speaker(idx).to_dict()


@app.get("/api/report")
def api_report():
    """所有講者完成後產出英文報告話術。"""
    stats = []
    for sp in SPEAKERS:
        if sp.ended:
            stats.append({
                "name": sp.name,
                "role": sp.role,
                "duration_sec": sp.duration(),
                "fillers": sp.fillers,
                "transcript": sp.transcript,
            })
    if not stats:
        return JSONResponse({"script": "(尚未有任何講者完成錄音)"})
    script = build_report_script(stats)
    # 存檔
    out = HERE / "reports" / f"report_{datetime.now():%Y%m%d_%H%M}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(script, encoding="utf-8")
    return JSONResponse({"script": script, "saved_to": str(out)})


def _get_speaker(idx: int) -> SpeakerSession:
    for sp in SPEAKERS:
        if sp.idx == idx:
            return sp
    raise HTTPException(404, f"speaker idx {idx} not found")


# ===== OCR 上傳議程 =====
UPLOADS = HERE / "uploads"
UPLOADS.mkdir(exist_ok=True)


@app.post("/api/upload-agenda")
async def api_upload_agenda(file: UploadFile = File(...)):
    """收議程照片,跑 OCR,回傳 parsed speakers (前端確認後再 commit)."""
    try:
        import ocr as ocr_module  # 延遲 import,避免啟動失敗
    except Exception as e:
        return JSONResponse({"error": f"OCR 模組不可用: {e}"}, status_code=500)

    suffix = Path(file.filename or "upload").suffix or ".jpg"
    out_path = UPLOADS / f"agenda_{int(time.time())}{suffix}"
    out_path.write_bytes(await file.read())

    try:
        items = ocr_module.ocr_items(str(out_path))
        raw_text = "\n".join(it["text"] for it in items)
        speakers = ocr_module.parse_agenda(items)  # 用座標版,鎖右側人名欄
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    return JSONResponse({
        "raw_text": raw_text,
        "speakers": speakers,
        "image_path": str(out_path),
    })


class CommitSpeakers(BaseModel):
    speakers: list[dict]


@app.post("/api/upload-agenda-json")
async def api_upload_agenda_json(file: UploadFile = File(...)):
    """直接吃 KIRIN 從外部 AI (Claude.ai / ChatGPT / Gemini) 拿回的 JSON 議程。"""
    global SPEAKERS, AGENDA
    try:
        content = (await file.read()).decode("utf-8")
        # 容錯: 若是 markdown 包 JSON, 抽出來
        if "```json" in content:
            content = content.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in content:
            content = content.split("```", 1)[1].split("```", 1)[0]
        data = json.loads(content.strip())
    except Exception as e:
        return JSONResponse({"error": f"JSON 格式錯: {e}"}, status_code=400)

    AGENDA = data
    SPEAKERS = []
    for i, sp in enumerate(data.get("speakers", [])):
        SPEAKERS.append(SpeakerSession(
            idx=i,
            name=sp.get("speaker", f"Speaker {i+1}"),
            role=sp.get("role", ""),
            language=sp.get("language", "auto"),
        ))
    return {"loaded": len(SPEAKERS), "meeting": data.get("meeting_no")}


@app.post("/api/commit-speakers")
def api_commit_speakers(payload: CommitSpeakers):
    """收到 KIRIN 確認後的講者名單,重置 SPEAKERS。"""
    global SPEAKERS
    SPEAKERS = []
    for i, sp in enumerate(payload.speakers):
        if not sp.get("counted", True):
            continue
        SPEAKERS.append(SpeakerSession(
            idx=i,
            name=sp.get("speaker", f"Speaker {i+1}"),
            role=sp.get("role", ""),
            language=sp.get("language", "auto"),
        ))
    return {"loaded": len(SPEAKERS)}


if __name__ == "__main__":
    import uvicorn
    agenda_path = V1 / "agenda_2026-06-22.json"
    if len(sys.argv) > 1:
        agenda_path = Path(sys.argv[1])
    load_meta_only(agenda_path)
    print(f"📋 Loaded agenda: {agenda_path.name}", flush=True)
    print(f"🎤 Speakers: {len(SPEAKERS)}", flush=True)
    port = int(os.environ.get("AH_PORT", "8766"))
    print(f"\n🌐 Open browser: http://localhost:{port}\n", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
