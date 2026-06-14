#!/usr/bin/env python3
"""Toastmasters Ah Counter Live — Textual TUI

跑法:
    python3 app.py                              # 用預設 agenda
    python3 app.py --agenda agenda_2026-06-22.json

操作:
    Enter / N : 下一位講者
    P         : 上一位
    O         : 顯示開場詞 (你 7:01 念這段)
    R         : 顯示結尾報告話術 (你 8:47 念這段,從統計自動生成)
    Q         : 結束會議,存報告退出
"""
from __future__ import annotations
import argparse
import json
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.widgets import Header, Footer, Static, DataTable, Label
from textual.reactive import reactive

from streaming import StreamingTranscriber
from counter import count_chinese, count_english, load_fillers
from script_gen import build_report_script

HERE = Path(__file__).parent


def merge_counts(zh: Counter, en: Counter) -> Counter:
    combined = Counter()
    combined.update(zh)
    combined.update(en)
    return combined


class CurrentSpeakerBox(Static):
    """目前講者大字顯示。"""
    speaker_name = reactive("Not started")
    speaker_role = reactive("")
    elapsed = reactive(0)

    def render(self):
        mins, secs = divmod(int(self.elapsed), 60)
        return (
            f"[bold yellow]🎤 {self.speaker_name}[/bold yellow]\n"
            f"[dim]{self.speaker_role}[/dim]\n"
            f"[cyan]⏱  {mins:02d}:{secs:02d}[/cyan]"
        )


class TranscriptBox(Static):
    """最新字幕(滾動,只顯示最後 200 字)。"""
    text = reactive("")

    def render(self):
        snippet = self.text[-300:]
        return f"[italic]📝 {snippet or '(等待語音...)'}[/italic]"


class FillerTable(DataTable):
    """每位講者的 filler 即時表。"""

    def on_mount(self) -> None:
        self.add_columns("講者", "嗯/啊", "那個", "就是", "然後", "uh/um", "like", "so", "總計")
        self.cursor_type = "row"

    def upsert(self, label: str, counts: Counter):
        row = [
            label,
            str(counts.get("嗯", 0) + counts.get("啊", 0) + counts.get("欸", 0)),
            str(counts.get("那個", 0) + counts.get("這個", 0)),
            str(counts.get("就是", 0)),
            str(counts.get("然後", 0)),
            str(counts.get("uh", 0) + counts.get("um", 0) + counts.get("ah", 0)),
            str(counts.get("like", 0)),
            str(counts.get("so", 0) + counts.get("well", 0)),
            str(sum(counts.values())),
        ]
        # 找該 label 是否已存在
        for i, key in enumerate(self.rows):
            existing = self.get_row_at(i)
            if existing[0] == label:
                for col_idx, val in enumerate(row):
                    self.update_cell_at((i, col_idx), val)
                return
        self.add_row(*row)


class AhCounterApp(App):
    CSS = """
    Screen { background: #1a1a2e; }
    #current { height: 5; border: solid cyan; padding: 1; }
    #transcript { height: 6; border: solid magenta; padding: 1; }
    #stats { height: 1fr; border: solid green; }
    #hint { height: 3; padding: 1; color: white; background: #16213e; }
    .panel-title { color: cyan; text-style: bold; }
    """

    BINDINGS = [
        Binding("enter", "next_speaker", "下一位"),
        Binding("n", "next_speaker", "下一位"),
        Binding("p", "prev_speaker", "上一位"),
        Binding("o", "show_opening", "開場詞"),
        Binding("r", "show_report", "報告話術"),
        Binding("q", "quit_save", "結束存檔"),
    ]

    def __init__(self, agenda_path: Path):
        super().__init__()
        self.agenda = json.loads(agenda_path.read_text(encoding="utf-8"))
        self.speakers = [s for s in self.agenda["speakers"] if s.get("counted", True)]
        self.current_idx = 0
        self.start_time: float | None = None
        self.speaker_start_time: float | None = None
        self.fillers_zh, self.fillers_en = load_fillers()
        # per-speaker accumulated transcripts and counters
        self.transcripts: dict[str, str] = {sp["speaker"]: "" for sp in self.speakers}
        self.transcriber: StreamingTranscriber | None = None
        self.recordings_dir = HERE / "recordings"
        self.recordings_dir.mkdir(exist_ok=True)

    def compose(self) -> ComposeResult:
        yield Header(name=f"🎤 Ah Counter Live — {self.agenda.get('club', 'Toastmasters')}")
        yield CurrentSpeakerBox(id="current")
        yield TranscriptBox(id="transcript")
        yield FillerTable(id="stats")
        yield Static(
            "[bold]鍵盤:[/bold]  [Enter] 下一位  |  [P] 上一位  |  [O] 開場詞  |  [R] 報告話術  |  [Q] 結束",
            id="hint",
        )
        yield Footer()

    def on_mount(self) -> None:
        # 啟動 streaming
        self.start_time = time.time()
        self.speaker_start_time = self.start_time
        self.transcriber = StreamingTranscriber(
            on_text=self._on_new_text,
            model_size="base",
            language=None,  # auto detect
        )
        self.transcriber.start()
        self._refresh_speaker_box()
        self.set_interval(0.5, self._tick)

    def _on_new_text(self, text: str):
        """faster-whisper 吐新字串時,在主 thread 更新 UI 和統計。"""
        # textual 的 call_from_thread 確保 thread-safe
        self.call_from_thread(self._apply_new_text, text)

    def _apply_new_text(self, text: str):
        if self.current_idx >= len(self.speakers):
            return
        sp = self.speakers[self.current_idx]
        name = sp["speaker"]
        # streaming 會吐出重疊字串,我們 append 完整新句
        prev = self.transcripts[name]
        # 簡化策略: 把新字串接在後面 (允許小重複,filler 統計用 substring 多算 1-2 次可接受)
        # 真正生產應做 diff/dedup, 這裡先求可用
        if text not in prev[-200:]:
            self.transcripts[name] = prev + " " + text
        # 更新 UI
        self.query_one("#transcript", TranscriptBox).text = self.transcripts[name]
        self._update_stats(name)

    def _update_stats(self, name: str):
        transcript = self.transcripts[name]
        zh = count_chinese(transcript, self.fillers_zh)
        en = count_english(transcript, self.fillers_en)
        merged = merge_counts(zh, en)
        self.query_one("#stats", FillerTable).upsert(name, merged)

    def _tick(self):
        if self.speaker_start_time is None:
            return
        box = self.query_one("#current", CurrentSpeakerBox)
        box.elapsed = time.time() - self.speaker_start_time

    def _refresh_speaker_box(self):
        box = self.query_one("#current", CurrentSpeakerBox)
        if self.current_idx >= len(self.speakers):
            box.speaker_name = "✅ 全部結束"
            box.speaker_role = "按 R 看報告話術,按 Q 存檔退出"
            return
        sp = self.speakers[self.current_idx]
        box.speaker_name = sp["speaker"]
        box.speaker_role = sp["role"]
        box.elapsed = 0
        self.speaker_start_time = time.time()

    def action_next_speaker(self):
        if self.current_idx < len(self.speakers):
            self.current_idx += 1
            self._refresh_speaker_box()

    def action_prev_speaker(self):
        if self.current_idx > 0:
            self.current_idx -= 1
            self._refresh_speaker_box()

    def action_show_opening(self):
        opening = self.agenda.get("opening_speech", "(opening_speech not in agenda)")
        self.push_screen_wait = None  # placeholder
        # 用 transcript box 顯示
        self.query_one("#transcript", TranscriptBox).text = "[OPENING] " + opening

    def action_show_report(self):
        # 從統計組裝報告
        stats = []
        for sp in self.speakers[: self.current_idx + 1]:
            name = sp["speaker"]
            transcript = self.transcripts.get(name, "")
            zh = count_chinese(transcript, self.fillers_zh)
            en = count_english(transcript, self.fillers_en)
            merged = merge_counts(zh, en)
            stats.append({
                "name": name,
                "role": sp["role"],
                "duration_sec": 300,  # TODO: 改記錄每位實際時間
                "fillers": merged,
                "transcript": transcript,
            })
        script = build_report_script(stats)
        # 寫到檔 + 在 transcript 顯示前 500 字
        out = HERE / "reports" / f"script_{datetime.now():%Y%m%d_%H%M}.md"
        out.parent.mkdir(exist_ok=True)
        out.write_text(script, encoding="utf-8")
        self.query_one("#transcript", TranscriptBox).text = (
            f"[REPORT 已存到 {out.name}]\n\n" + script[:500] + "..."
        )

    def action_quit_save(self):
        # 停 streaming, 存錄音, 寫最終報告, 退出
        if self.transcriber:
            wav_path = self.recordings_dir / f"meeting_{int(time.time())}.wav"
            try:
                self.transcriber.save_full(wav_path)
            except Exception:
                pass
        # 寫最終報告
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        report_path = HERE / "reports" / f"final_{ts}.md"
        report_path.parent.mkdir(exist_ok=True)
        lines = [f"# Ah Counter Final Report — {ts}", ""]
        for sp in self.speakers:
            name = sp["speaker"]
            transcript = self.transcripts.get(name, "")
            zh = count_chinese(transcript, self.fillers_zh)
            en = count_english(transcript, self.fillers_en)
            merged = merge_counts(zh, en)
            total = sum(merged.values())
            lines.append(f"## {name} ({sp['role']})")
            lines.append(f"- 總 filler: **{total}**")
            for w, n in merged.most_common(5):
                lines.append(f"  - {w}: {n}")
            lines.append(f"- 逐字稿 (前 300 字): {transcript[:300]}...")
            lines.append("")
        # 加上自動報告話術
        stats = [{
            "name": sp["speaker"],
            "role": sp["role"],
            "duration_sec": 300,
            "fillers": merge_counts(
                count_chinese(self.transcripts.get(sp["speaker"], ""), self.fillers_zh),
                count_english(self.transcripts.get(sp["speaker"], ""), self.fillers_en),
            ),
        } for sp in self.speakers]
        lines.append("---")
        lines.append("## 📣 報告話術 (8:47 念這段)")
        lines.append("")
        lines.append(build_report_script(stats))
        report_path.write_text("\n".join(lines), encoding="utf-8")
        self.exit(message=f"報告存到 {report_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--agenda",
        type=str,
        default=str(HERE / "agenda_2026-06-22.json"),
    )
    args = parser.parse_args()
    AhCounterApp(Path(args.agenda)).run()


if __name__ == "__main__":
    main()
