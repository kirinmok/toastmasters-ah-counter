#!/usr/bin/env python3
"""Toastmasters Ah Counter Live CLI

用法:
    python3 tm.py                    # 用預設議程 agenda_2026-06-08.json
    python3 tm.py --agenda foo.json  # 指定議程

互動:
    [Enter] = 講者結束,切段並即時轉錄
    [q]     = 結束會議,產出完整報告
    [s]     = 跳過當前講者(不切段,直接到下一位)
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from datetime import datetime

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel

from recorder import BackgroundRecorder
from transcribe import transcribe
from counter import report_segment, overall_summary

console = Console()
HERE = Path(__file__).parent
DEFAULT_AGENDA = HERE / "agenda_2026-06-08.json"


def load_agenda(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["speakers"]


def render_status(rec: BackgroundRecorder, current_idx: int, speakers: list[dict]) -> Panel:
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", width=3)
    table.add_column("講者", width=30)
    table.add_column("狀態", width=10)
    for i, sp in enumerate(speakers):
        mark = "✅" if i < current_idx else ("🎤" if i == current_idx else "  ")
        status = "完成" if i < current_idx else ("進行中" if i == current_idx else "等待")
        style = "green" if i < current_idx else ("bold yellow" if i == current_idx else "dim")
        table.add_row(f"{mark}{i+1}", sp["speaker"], status, style=style)

    elapsed = int(rec.elapsed())
    mins, secs = divmod(elapsed, 60)
    title = f"⏱️  錄音 {mins:02d}:{secs:02d}  |  講者 {current_idx+1}/{len(speakers)}"
    return Panel(table, title=title, border_style="cyan")


@click.command()
@click.option("--agenda", type=click.Path(exists=True), default=str(DEFAULT_AGENDA))
@click.option("--output-dir", type=click.Path(), default=str(HERE / "recordings"))
def main(agenda, output_dir):
    speakers = load_agenda(Path(agenda))
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        f"[bold cyan]🎤 Toastmasters Ah Counter Live[/bold cyan]\n"
        f"議程: {agenda}\n"
        f"講者數: {len(speakers)}\n\n"
        f"[bold]控制鍵:[/bold]\n"
        f"  [Enter] = 講者結束,切段並轉錄\n"
        f"  [q]     = 結束會議,產出完整報告\n"
        f"  [s]     = 跳過當前講者",
        title="開始前",
    ))
    input("按 Enter 開始錄音...")

    rec = BackgroundRecorder(output)
    rec.start()
    console.print("[bold green]🔴 錄音中...[/bold green]")

    segments_with_text: list[dict] = []
    current_idx = 0

    while current_idx < len(speakers):
        with Live(render_status(rec, current_idx, speakers), refresh_per_second=2) as live:
            # 等使用者輸入
            line = input()
        cmd = line.strip().lower()

        if cmd == "q":
            break
        elif cmd == "s":
            console.print(f"[yellow]跳過 {speakers[current_idx]['speaker']}[/yellow]")
            current_idx += 1
            continue
        else:
            # 預設 Enter = 切段
            sp = speakers[current_idx]
            label = f"{sp['speaker']}_{sp['role']}"
            seg = rec.mark_segment(label)
            console.print(f"[cyan]📝 切段 {label} ({seg['end_sec']-seg['start_sec']:.0f}秒),轉錄中...[/cyan]")
            # 即時切音檔 + 轉錄
            try:
                # 先存當前所有錄音
                wav_path = output / f"_temp_{int(time.time())}.wav"
                # 因為 rec 還在錄,我們用 snapshot 方式取出當前 buffer 切片
                # 簡化: 直接把所有 frames concat 存,再從整檔切
                # (真正 production 要 streaming, 但小型會議 90 分鐘 wav < 200MB, OK)
                # 這裡先 stop+restart 取得 snapshot
                # 或更簡單: 結束才轉錄,現場只切段時間戳
                console.print(f"[dim](即時轉錄延後到結束,先記時間戳)[/dim]")
            except Exception as e:
                console.print(f"[red]轉錄失敗: {e}[/red]")
            current_idx += 1

    # 結束: 停止錄音 + 全部轉錄
    console.print("[bold yellow]⏹️  結束錄音,開始全段轉錄...[/bold yellow]")
    wav_path = rec.stop()
    console.print(f"[green]錄音存檔: {wav_path}[/green]")

    # 逐段切音檔 + 跑 whisper
    for seg in rec.segments:
        console.print(f"[cyan]🎯 處理 {seg['label']}...[/cyan]")
        clip = rec.extract_segment(wav_path, seg)
        try:
            text = transcribe(clip)
        except Exception as e:
            text = f"[轉錄失敗: {e}]"
        segments_with_text.append({
            "label": seg["label"],
            "transcript": text,
            "duration_sec": seg["end_sec"] - seg["start_sec"],
        })

    # 產出報告
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    report_path = HERE / "reports" / f"report_{ts}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"# 🎤 Ah Counter Report — {ts}", ""]
    lines.append("## 📊 各講者統計\n")
    for seg in segments_with_text:
        lines.append(report_segment(seg["label"], seg["transcript"], seg["duration_sec"]))
    lines.append(overall_summary(segments_with_text))
    report_path.write_text("\n".join(lines), encoding="utf-8")

    console.print(Panel.fit(
        f"[bold green]✅ 完成[/bold green]\n"
        f"報告: {report_path}\n"
        f"錄音: {wav_path}",
        title="會議結束",
    ))


if __name__ == "__main__":
    main()
