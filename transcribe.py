"""用 whisper.cpp 把音檔轉逐字稿。"""
from __future__ import annotations
import subprocess
import shutil
from pathlib import Path

# Whisper.cpp 模型路徑 (brew 裝在 /opt/homebrew/share/whisper.cpp/models/)
MODEL_CANDIDATES = [
    "/opt/homebrew/share/whisper.cpp/models/ggml-base.bin",
    "/opt/homebrew/share/whisper.cpp/models/ggml-small.bin",
    Path.home() / ".cache/whisper.cpp/ggml-base.bin",
]


def find_whisper_binary() -> str:
    """找到 whisper.cpp 可執行檔。brew 裝後通常叫 whisper-cli。"""
    for name in ("whisper-cli", "whisper-cpp", "main"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("whisper.cpp 沒裝。請跑: brew install whisper-cpp")


def find_model() -> Path:
    """找已下載的 ggml model。"""
    for cand in MODEL_CANDIDATES:
        if Path(cand).exists():
            return Path(cand)
    raise RuntimeError(
        "找不到 whisper 模型。請下載 base 或 small:\n"
        "  bash /opt/homebrew/share/whisper.cpp/models/download-ggml-model.sh base"
    )


def transcribe(audio_path: Path, language: str = "auto") -> str:
    """跑 whisper.cpp 回傳純文字逐字稿。"""
    binary = find_whisper_binary()
    model = find_model()
    cmd = [
        binary,
        "-m", str(model),
        "-f", str(audio_path),
        "-l", language,
        "-otxt",  # 輸出 .txt
        "-np",    # no prints (簡潔)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    txt_path = audio_path.with_suffix(audio_path.suffix + ".txt")
    if not txt_path.exists():
        # whisper.cpp 有時用 <name>.txt 不接副檔名
        txt_path = audio_path.with_suffix(".txt")
    return txt_path.read_text(encoding="utf-8").strip()
