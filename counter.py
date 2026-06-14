"""填充詞統計引擎 — 吃逐字稿,吐統計報告。"""
from __future__ import annotations
import json
import re
from pathlib import Path
from collections import Counter

FILLERS_PATH = Path(__file__).parent / "fillers.json"


def load_fillers() -> tuple[dict, dict]:
    data = json.loads(FILLERS_PATH.read_text(encoding="utf-8"))
    return data["chinese_fillers"], data["english_fillers"]


def count_chinese(transcript: str, fillers_zh: dict) -> Counter:
    """中文填充詞用 substring 計算 (中文沒有 word boundary)。"""
    counts = Counter()
    for canonical, variants in fillers_zh.items():
        total = 0
        for v in variants:
            # 排除標點符號內 — 簡化版直接 count
            total += transcript.count(v)
        if total > 0:
            counts[canonical] = total
    return counts


def count_english(transcript: str, fillers_en: dict) -> Counter:
    """英文用 word boundary regex。"""
    counts = Counter()
    text_lower = transcript.lower()
    for canonical, variants in fillers_en.items():
        total = 0
        for v in variants:
            # \b 邊界,避免 like 命中 likely
            pattern = r"\b" + re.escape(v) + r"\b"
            total += len(re.findall(pattern, text_lower))
        if total > 0:
            counts[canonical] = total
    return counts


def report_segment(label: str, transcript: str, duration_sec: float) -> str:
    """產出單一講者段落的 Markdown 報告。"""
    fillers_zh, fillers_en = load_fillers()
    zh = count_chinese(transcript, fillers_zh)
    en = count_english(transcript, fillers_en)
    total = sum(zh.values()) + sum(en.values())
    density = duration_sec / total if total else 0

    lines = [f"### {label} (時長 {int(duration_sec//60)}:{int(duration_sec%60):02d})", ""]
    lines.append("| 填充詞 | 次數 |")
    lines.append("|---|---|")
    for word, n in sorted(zh.items(), key=lambda x: -x[1]):
        lines.append(f"| {word} | {n} |")
    for word, n in sorted(en.items(), key=lambda x: -x[1]):
        lines.append(f"| {word} | {n} |")
    lines.append(f"| **小計** | **{total}** |")
    lines.append("")
    if density:
        lines.append(f"**密度**: 約每 {density:.1f} 秒一次 filler")
    lines.append(f"**逐字稿節錄** (前 200 字): {transcript[:200]}...")
    lines.append("")
    return "\n".join(lines)


def overall_summary(all_segments: list[dict]) -> str:
    """all_segments = [{label, transcript, duration_sec}]"""
    lines = ["## 🏆 今晚之最", ""]
    grand = Counter()
    densities = []
    for seg in all_segments:
        fillers_zh, fillers_en = load_fillers()
        zh = count_chinese(seg["transcript"], fillers_zh)
        en = count_english(seg["transcript"], fillers_en)
        seg_total = sum(zh.values()) + sum(en.values())
        grand.update(zh)
        grand.update(en)
        if seg_total:
            densities.append((seg["label"], seg["duration_sec"] / seg_total))

    if densities:
        smoothest = max(densities, key=lambda x: x[1])
        lines.append(f"- 最流暢: **{smoothest[0]}** (每 {smoothest[1]:.1f} 秒一次 filler)")
    if grand:
        top = grand.most_common(1)[0]
        lines.append(f"- 全場最常用: **{top[0]}** — 累積 {top[1]} 次")
    return "\n".join(lines)
