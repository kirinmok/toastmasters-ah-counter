# Toastmasters Ah Counter Live (v1)

**邊講邊出字幕 + filler 即時跳數 + 自動生成英文報告話術** 的 Toastmasters Ah Counter 助手。
完全離線、免費、Mac 本機跑。

## 🎯 給誰用

第一次當 Ah Counter 卡關的人 — 你不用怕記不住、聽不清、現場手寫不及。

## 🚀 6/22 例會怎麼用

```bash
cd ~/projects/toastmasters_ah_counter
python3 app.py --agenda agenda_2026-06-22.json
```

### 開場前（7:00 前到場）
- 打開 Mac 跑上面那行
- 麥克風放講台前/桌上中央
- 螢幕會顯示第一位講者

### 會議中
| 按鍵 | 動作 |
|---|---|
| **Enter / N** | 切到下一位講者 |
| **P** | 上一位（按錯回去） |
| **O** | 顯示 7:01 你要念的**開場詞** |
| **R** | 顯示根據目前統計自動生成的**結尾報告話術** |
| **Q** | 結束會議、存錄音和報告、退出 |

### 8:47 報告
- 按 R → 螢幕顯示英文報告話術
- 直接念螢幕上的內容（或自己潤飾）

## 📁 檔案

```
toastmasters_ah_counter/
├── app.py                    # 主程式 (Textual TUI)
├── streaming.py              # faster-whisper streaming
├── counter.py                # 填充詞統計
├── script_gen.py             # 自動報告話術生成
├── fillers.json              # 中英填充詞字典
├── agenda_2026-06-22.json    # 下次會議議程（含開場詞）
├── recordings/               # 錄音檔（會議結束自動存）
└── reports/                  # Markdown 報告 + 報告話術
```

## ⚙️ 技術細節

- **錄音**：sounddevice 16kHz 單聲道
- **STT**：faster-whisper base 模型，int8 量化，CPU 跑（M 系列 < 1 秒處理 3 秒音檔）
- **滑動視窗**：5 秒視窗 / 3 秒 stride / 啟用 VAD 過濾沉默
- **語言**：auto detect（中英混合 OK）
- **檔案隱私**：完全本機，**不上雲、不打 API**

## 🐛 已知限制

1. **講者切換靠手動**：按 Enter 切下一位，沒有 speaker diarization
2. **滑動視窗會略重複算字**：邊界詞可能 +1，但長段下平均誤差 < 5%
3. **首次跑會下載 base 模型**（~140MB，存在 `~/.cache/huggingface/`），之後完全離線

## 📝 編輯下次的議程

複製 `agenda_2026-06-22.json` 改：
- `speakers[]` 每位講者的 `start / role / speaker / language`
- `counted: true/false` — 哪些講者要計入 filler（主持人 = false）
- `opening_speech` — 你的開場詞（可用內建版或自己改）

## 🔮 未來

- v2：每位講者實際時間記錄（不是寫死 5 分鐘）
- v3：speaker diarization（自動切換不用按 Enter）
- v4：Web GUI 版（如果嫌 terminal 不夠漂亮）
