"""Vision OCR + 結構化議程 parser

策略 (KIRIN 6/14 親口指示):
  「議程表的欄位永遠是固定的, 右側欄就是人名欄。」

  → 用 bounding box 座標分欄, 鎖右側 = 人名欄, 不要的全濾掉。
"""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

HERE = Path(__file__).parent
OCR_BIN = HERE / "ocr_bin"
OCR_SWIFT = HERE / "ocr.swift"


# ===== Swift Vision OCR =====
def _ensure_binary():
    if OCR_BIN.exists():
        return
    if not OCR_SWIFT.exists():
        raise RuntimeError("ocr_bin and ocr.swift both missing")
    subprocess.run(["swiftc", str(OCR_SWIFT), "-o", str(OCR_BIN)],
                   check=True, capture_output=True)


def ocr_items(image_path: str) -> list[dict]:
    """跑 Swift Vision OCR, 回傳 [{text, x, y, w, h}]"""
    _ensure_binary()
    proc = subprocess.run([str(OCR_BIN), str(image_path)],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"OCR failed: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def ocr_image(image_path: str) -> str:
    """向後相容: 回傳純文字 raw OCR."""
    return "\n".join(it["text"] for it in ocr_items(image_path))


# ===== 結構化 parser =====
TIME_PATTERN = re.compile(r"\b(\d{1,2}):(\d{2})\b")
EN_CH_NAME = re.compile(r"([A-Z][a-z]{2,15})\s+([一-龥]{2,4})")

# 排除的「假人名」: 角色字、職稱
NON_NAME_EN = {
    "Toastmaster", "Toastmasters", "President", "Timer", "Grammarian",
    "Evaluator", "General", "Master", "Topicsmaster", "Topics", "Topic",
    "Speech", "Special", "Table", "English", "Talk", "Pitch", "Counter",
    "Elevator", "Zoom", "Receptionist", "Sergeant", "Officer", "Officers",
    "Manual", "Session", "Awesome", "Closing", "Opening", "Theme",
    "Variety", "Public", "Education", "Membership", "Relations", "Treasurer",
    "Secretary", "Arms", "Date", "Meeting", "Venue", "Welcome", "Guests",
    "Calls", "Order", "Roles", "Word", "Report", "Group", "Photo",
    "Intermission", "Coverage", "Number", "Club", "Area", "Division",
    "District", "Since", "ID", "Tonight", "Inspiring", "Power", "Audience",
    "Simple", "List", "Tour", "Vietnam", "Upcoming", "Events", "Stay",
    "Curious", "Teachable", "Equipment", "Checkout", "Social", "Chair",
}

# Ah Counter 不會統計這些角色 (即使有英中名)
SKIP_ROLES = {
    "Toastmaster", "President", "Timer", "Grammarian", "General Evaluator",
    "Ah Counter", "Ah counter", "SAA", "Zoom Master", "Receptionist",
    "Sergeant", "Variety Master", "Topicsmaster",
}

# 想計入的角色關鍵字 (用模糊匹配)
COUNT_ROLES = [
    ("Special Speech", "Special Speech"),
    ("ToastTalker", "Special Speech"),
    ("Manual speech", "Manual Speech"),
    ("Speech 1", "Speech 1"),
    ("Speech 2", "Speech 2"),
    ("English Talk", "English Talk"),
    ("Table Topics", "Table Topics"),
    ("Evaluator 1", "Evaluator 1"),
    ("Evaluator 2", "Evaluator 2"),
    ("Evaluator", "Evaluator"),
    ("Elevator Pitch", "Elevator Pitch"),
    ("Pitch", "Pitch"),
]


def _classify_role(context: str) -> tuple[Optional[str], bool]:
    """從上下文判斷角色 + 是否要 skip (不計入 Ah Counter 統計)"""
    context_lower = context.lower()
    for needle, label in COUNT_ROLES:
        if needle.lower() in context_lower:
            # 但若同時匹配 skip 角色, 還是要 skip
            for s in SKIP_ROLES:
                if s.lower() in context_lower and s.lower() != needle.lower():
                    pass  # 比如 "Toastmaster" 行裡有 "Toastmaster" 字, 走 skip
            return label, False
    for s in SKIP_ROLES:
        if s.lower() in context_lower:
            return s, True
    return None, False


def parse_agenda(raw_or_items) -> list[dict]:
    """從 OCR 結果抽出講者 (結構化版本)。

    raw_or_items 可以是:
      - list[dict] (來自 ocr_items, 帶座標)
      - str (raw text, 回退)
    """
    if isinstance(raw_or_items, str):
        # Fallback: 沒座標時退回純文字模式
        return _parse_text(raw_or_items)

    items = raw_or_items
    if not items:
        return []

    # === Step 1: 找「英文名 + 中文名」=== (這些是候選真人講者)
    name_candidates = []  # [{text:"Dirk 洪瑞臨", x, y, en, zh}]
    for it in items:
        text = it["text"]
        for m in EN_CH_NAME.finditer(text):
            en, zh = m.group(1), m.group(2)
            if en in NON_NAME_EN:
                continue
            name_candidates.append({
                "name": f"{en} {zh}",
                "en": en,
                "zh": zh,
                "x": it["x"],
                "y": it["y"],
            })

    if not name_candidates:
        return []

    # === Step 2: 鎖人名欄 (右側) ===
    # 把候選按 x 中位數判斷,主要人名欄通常 x > 中位數
    xs = sorted(c["x"] for c in name_candidates)
    median_x = xs[len(xs) // 2]
    # 寬鬆: 認可所有 x ≥ 0.5 × median 的候選 (避免漏)
    threshold = median_x * 0.5

    # === Step 3: 對每個候選, 找同 y 範圍的時間 + 角色 ===
    # 把所有時間項標記
    time_items = []  # [{time, x, y}]
    for it in items:
        for m in TIME_PATTERN.finditer(it["text"]):
            h, mm = int(m.group(1)), int(m.group(2))
            if 6 <= h <= 22:
                time_items.append({
                    "time": f"{h:02d}:{mm:02d}",
                    "x": it["x"],
                    "y": it["y"],
                })

    speakers = []
    seen = set()
    for cand in name_candidates:
        if cand["x"] < threshold:
            continue
        if cand["name"] in seen:
            continue
        seen.add(cand["name"])

        # 找最近的時間: 同 y ± 容差 (歸一化座標, 0.025 約一行)
        same_row = [t for t in time_items if abs(t["y"] - cand["y"]) < 0.025]
        time_str = same_row[0]["time"] if same_row else ""

        # 找角色: 同 y ± 容差的所有 text
        same_row_items = [it for it in items if abs(it["y"] - cand["y"]) < 0.025]
        context = " ".join(it["text"] for it in same_row_items)
        role, skip = _classify_role(context)

        # Ah Counter 預設規則:
        # - 真正演講角色 (Speech / Special / Table Topics / Evaluator / English Talk) → 勾選
        # - 主持/串場/Master/Pitch 角色 → 預設不勾 (KIRIN 想算可手動勾)
        # - 模糊 (待選) → 預設不勾, 避免雜訊
        counted_default = (not skip) and (role is not None) and (
            role not in ("Elevator Pitch", "Pitch")
        )

        speakers.append({
            "start": time_str,
            "role": role or "(待選)",
            "speaker": cand["name"],
            "language": "mixed",
            "counted": counted_default,
        })

    # 按時間排序
    speakers.sort(key=lambda s: (s["start"] or "99:99", s["speaker"]))
    return speakers


def _parse_text(raw_text: str) -> list[dict]:
    """純文字 fallback (無座標時)。"""
    speakers = []
    seen = set()
    current_time = ""
    for line in raw_text.splitlines():
        m = TIME_PATTERN.search(line)
        if m:
            h, mm = int(m.group(1)), int(m.group(2))
            if 6 <= h <= 22:
                current_time = f"{h:02d}:{mm:02d}"
        for m in EN_CH_NAME.finditer(line):
            en, zh = m.group(1), m.group(2)
            if en in NON_NAME_EN:
                continue
            full = f"{en} {zh}"
            if full in seen:
                continue
            seen.add(full)
            role, skip = _classify_role(line)
            speakers.append({
                "start": current_time,
                "role": role or "(待選)",
                "speaker": full,
                "language": "mixed",
                "counted": not skip,
            })
    speakers.sort(key=lambda s: (s["start"] or "99:99", s["speaker"]))
    return speakers


def parse_and_filter(image_or_text) -> list[dict]:
    """主入口: 接收 image_path 或 raw text, 回 parsed speakers。"""
    if isinstance(image_or_text, str) and Path(image_or_text).exists():
        items = ocr_items(image_or_text)
        return parse_agenda(items)
    return parse_agenda(image_or_text)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: ocr.py <image_path>")
        sys.exit(1)
    items = ocr_items(sys.argv[1])
    print(f"=== {len(items)} text blocks ===")
    speakers = parse_agenda(items)
    print(f"\n=== {len(speakers)} speakers ===")
    for s in speakers:
        flag = "✓" if s["counted"] else "✗"
        print(f"  {flag} {s['start']:6s} {s['role']:20s} {s['speaker']}")
