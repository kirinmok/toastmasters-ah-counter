# 議程解析 Prompt（丟給任何 AI 都能用）

## 📋 使用方法

1. 拍照議程表
2. 打開 **Claude.ai / ChatGPT / Gemini** 任何一個（網頁版免費）
3. 上傳議程照片 + 貼下面 prompt
4. AI 會回一段 JSON
5. 存成 `agenda_YYYY-MM-DD.json` → 上傳到網頁

---

## 🤖 Prompt（複製貼上）

```
你是 Toastmasters 議程解析專家。我會給你一張 Toastmasters 會議議程表的圖片。

請按以下規則解析,輸出 JSON 格式:

【Ah Counter 國際標準計入規則】
✅ counted: true (要算 filler)
  - Manual Speech / Special Speech 講者
  - Table Topics 即興回答者
  - English Talk / Evaluator (各位 Evaluator)
  - Variety Session Master (即興引導,通常算)

❌ counted: false (不算 filler)
  - President / Chair / Toastmaster of the Evening (主持)
  - Timer / Grammarian / Ah Counter / SAA / Zoom Master / Receptionist
  - General Evaluator (照稿 report)
  - Word of the Day Master / Variety Master (純介紹)
  - Table Topicsmaster (出題後不算他)
  - VP / Secretary / Treasurer / Sergeant 等 club officer

【人名規則】
- 同一個人多角色 → 只列「最重要演講角色」一次
  (例: Terence Ai 同時是 Zoom Master + Evaluator → 列 Evaluator)
- 純英文名 (像 "Luca") 直接收
- 英文+中文姓 (像 "Doreen Huang") 直接收
- 排除欄位標題 / 講題 / 友會資訊

【JSON 輸出格式】(嚴格遵守,別加說明文字,只給純 JSON)
{
  "meeting_no": <會議編號>,
  "date": "YYYY-MM-DD",
  "club": "<club 名稱>",
  "theme": "<主題>",
  "ah_counter": "<Ah Counter 名字>",
  "report_time": "<HH:MM>",
  "opening_speech": "Thank you, Toastmaster. Good evening fellow Toastmasters and welcomed guests. I'm <Ah Counter 名字>, your Ah Counter for tonight. My role is to listen for filler words — uh, um, ah, like, so, you know — and unnecessary repetitions that sneak in when our brain races ahead of our mouth. But fillers are not mistakes — they are simply our brain catching up with our tongue. I'm not here as a judge. I'm here as a mirror, helping each of you notice the habits you may not hear yourself. Wishing everyone a night of powerful pauses and minimal fillers. Thank you. Back to you, Toastmaster.",
  "speakers": [
    {
      "start": "HH:MM",
      "role": "<角色>",
      "speaker": "<人名>",
      "language": "mixed | en | zh",
      "counted": true | false
    }
  ]
}

請現在解析我給你的議程圖片。
```

---

## 💡 範例輸出

(KIRIN 看這個範例就知道格式對不對)

```json
{
  "meeting_no": 583,
  "date": "2026-06-17",
  "club": "CHIA-YI Toastmasters Club 4439",
  "theme": "SDGs",
  "ah_counter": "Kirin Mok",
  "report_time": "20:27",
  "opening_speech": "...",
  "speakers": [
    {"start": "19:34", "role": "Speaker 1 (Manual Speech)", "speaker": "Luca", "language": "en", "counted": true},
    {"start": "19:34", "role": "Speaker 2 (Manual Speech)", "speaker": "Bain Chou", "language": "en", "counted": true},
    {"start": "20:27", "role": "Evaluator (Ice breaker)", "speaker": "Terence Ai", "language": "en", "counted": true}
  ]
}
```
