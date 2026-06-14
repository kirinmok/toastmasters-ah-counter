"""根據統計結果自動生成英文報告話術 (8:47 念這段)。"""
from __future__ import annotations
from collections import Counter
from typing import Iterable


def _format_top_fillers(c: Counter, n: int = 3) -> str:
    items = c.most_common(n)
    if not items:
        return "no significant fillers"
    return ", ".join(f'"{w}" {n_}x' for w, n_ in items)


def build_report_script(speaker_stats: list[dict]) -> str:
    """
    speaker_stats = [
        {"name": "Darren", "role": "Manual Speech 1", "duration_sec": 420,
         "fillers": Counter({"就是": 8, "uh": 5, ...}), "transcript": "..."},
        ...
    ]
    """
    lines = []
    lines.append("Thank you, Madam Toastmaster. Good evening everyone.")
    lines.append("")
    lines.append("Tonight my role was to listen for filler words and unnecessary repetitions. "
                 "Here are my observations:")
    lines.append("")

    # 各講者一句話
    for sp in speaker_stats:
        if not sp.get("fillers"):
            lines.append(
                f'- **{sp["name"]}** ({sp["role"]}) — '
                f'no significant fillers detected. Excellent flow!'
            )
            continue
        total = sum(sp["fillers"].values())
        top = _format_top_fillers(sp["fillers"], n=2)
        duration_min = sp["duration_sec"] / 60
        density = sp["duration_sec"] / total if total else 0
        line = (
            f'- **{sp["name"]}** ({sp["role"]}) — about {total} fillers '
            f'in {duration_min:.1f} minutes, mainly {top}.'
        )
        if density > 20:
            line += " Very smooth pacing — well done."
        elif density > 10:
            line += " Solid control."
        elif density > 0:
            line += " A few habit words to be aware of next time."
        lines.append(line)
    lines.append("")

    # 找今晚之最
    if speaker_stats:
        # smoothest
        candidates = [s for s in speaker_stats if s.get("fillers") and s.get("duration_sec")]
        if candidates:
            smoothest = max(
                candidates,
                key=lambda s: s["duration_sec"] / max(sum(s["fillers"].values()), 1)
            )
            lines.append(f'The smoothest speaker tonight goes to **{smoothest["name"]}**. '
                         f'Well-paced and confident.')
            lines.append("")

        # 全場最常用 filler
        grand = Counter()
        for s in speaker_stats:
            grand.update(s.get("fillers", {}))
        if grand:
            top_word, top_n = grand.most_common(1)[0]
            lines.append(f'The most common filler tonight across all speakers was "{top_word}", '
                         f'showing up {top_n} times in total.')
            lines.append("")

    # 收尾金句
    lines.append("One reminder for all of us:")
    lines.append('**Filler is not a mistake — it\'s our brain catching up. '
                 'The cure is not to speak faster, but to pause longer.**')
    lines.append("")
    lines.append("Thank you. Back to you, Madam Toastmaster.")

    return "\n".join(lines)
