// ===== Filler 顯示欄位 =====
const FILLER_COLUMNS = [
  {label: "嗯/啊", alts: ["嗯", "啊", "欸"]},
  {label: "那個",  alts: ["那個", "這個"]},
  {label: "就是",  alts: ["就是"]},
  {label: "然後",  alts: ["然後"]},
  {label: "對/所以", alts: ["所以", "對"]},
  {label: "uh/um", alts: ["uh", "um", "ah"]},
  {label: "like",  alts: ["like"]},
  {label: "so/well", alts: ["so", "well"]},
  {label: "you know", alts: ["you know"]},
  {label: "actually", alts: ["actually", "basically"]},
];

let timers = {};

// ===== Tabs =====
document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
    t.classList.add("active");
    document.getElementById("tab-" + t.dataset.tab).classList.add("active");
  });
});

// ===== Load Agenda =====
async function loadAgenda() {
  const res = await fetch("/api/agenda");
  const data = await res.json();
  document.getElementById("meeting-info").textContent =
    `${data.club || "Toastmasters"} #${data.meeting || "-"} · ${data.date || ""}`;
  document.getElementById("opening-text").textContent = data.opening_speech || "(no opening script)";
  renderSpeakers(data.speakers);
}

function renderSpeakers(speakers) {
  const list = document.getElementById("speaker-list");
  list.innerHTML = "";
  if (!speakers || speakers.length === 0) {
    list.innerHTML = `
      <div class="hint" style="text-align:center; padding:24px; border:1px dashed #333; border-radius:8px;">
        📷 還沒有講者<br>
        請到 <b>Script tab → 拍照載入今晚講者</b>
      </div>`;
    return;
  }
  speakers.forEach(sp => list.appendChild(speakerRow(sp)));
}

function speakerRow(sp) {
  const div = document.createElement("div");
  div.className = "speaker";
  div.id = `sp-${sp.idx}`;
  if (sp.is_recording) div.classList.add("active");
  if (sp.ended) div.classList.add("done");

  div.innerHTML = `
    <div class="speaker-row">
      <div class="speaker-name">
        <span class="name" contenteditable="true" data-idx="${sp.idx}" data-field="name">${sp.name}</span>
        <span class="role" contenteditable="true" data-idx="${sp.idx}" data-field="role">${sp.role}</span>
      </div>
      <div class="timer-display" id="tm-${sp.idx}">00:00</div>
      <button class="btn-rec" id="btn-${sp.idx}" data-idx="${sp.idx}">
        ${recBtnLabel(sp)}
      </button>
      <button class="btn-del" data-del="${sp.idx}" title="刪除">✕</button>
    </div>
    <div class="filler-grid" id="fg-${sp.idx}"></div>
    <div class="transcript-mini" id="tr-${sp.idx}" style="display:none"></div>
  `;
  renderFiller(sp);
  const btn = div.querySelector(".btn-rec");
  if (sp.is_recording) btn.classList.add("recording");
  if (sp.ended) btn.classList.add("done");
  btn.addEventListener("click", () => toggleRecording(sp.idx));

  // ===== Inline 編輯姓名 / 角色 =====
  div.querySelectorAll('[contenteditable="true"]').forEach(el => {
    el.addEventListener("blur", async () => {
      const idx = el.dataset.idx;
      const field = el.dataset.field;
      const val = el.textContent.trim();
      await fetch(`/api/speaker/${idx}/rename`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({[field]: val}),
      });
      setStatus(`✏️ 更新 ${field}: ${val}`);
    });
    el.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); el.blur(); }
    });
  });

  // ===== 刪除講者 =====
  const delBtn = div.querySelector(".btn-del");
  if (delBtn) {
    delBtn.addEventListener("click", async () => {
      if (!confirm(`刪除 ${sp.name}?`)) return;
      await fetch(`/api/speaker/${sp.idx}`, {method: "DELETE"});
      loadAgenda();
    });
  }
  return div;
}

function recBtnLabel(sp) {
  if (sp.is_recording) return "⏹ 停止";
  if (sp.ended) return "✅ 已完成";
  return "● 開始錄音";
}

function renderFiller(sp) {
  const wrap = document.getElementById(`fg-${sp.idx}`);
  if (!wrap) return;
  const fillers = sp.fillers || {};
  wrap.innerHTML = FILLER_COLUMNS.map(col => {
    const n = col.alts.reduce((a, w) => a + (fillers[w] || 0), 0);
    let cls = "zero";
    if (n >= 5) cls = "hot";
    else if (n >= 3) cls = "warn";
    else if (n > 0) cls = "";
    return `<div class="filler-cell ${cls}">
      <div class="word">${col.label}</div>
      <div class="count">${n}</div>
    </div>`;
  }).join("");
  if (sp.transcript && sp.transcript !== "(no audio)") {
    const t = document.getElementById(`tr-${sp.idx}`);
    t.textContent = "📝 " + sp.transcript;
    t.style.display = "block";
  }
}

// ===== Recording control =====
async function toggleRecording(idx) {
  const btn = document.getElementById(`btn-${idx}`);
  const card = document.getElementById(`sp-${idx}`);
  const isRec = btn.textContent.includes("停止");

  if (!isRec) {
    setStatus(`啟動 ${idx} 錄音…`);
    const res = await fetch(`/api/speaker/${idx}/start`, {method: "POST"});
    const data = await res.json();
    if (data.error) {
      setStatus(`❌ ${data.error}`);
      alert(data.error);
      return;
    }
    btn.textContent = "⏹ 停止";
    btn.classList.add("recording");
    card.classList.add("active");
    card.classList.remove("done");
    timers[`start-${idx}`] = Date.now();
    timers[idx] = setInterval(() => updateTimer(idx), 500);
    setStatus(`🔴 錄音中: ${data.name}`);
  } else {
    setStatus(`⏳ 轉錄分析中…`);
    btn.disabled = true;
    btn.textContent = "⏳ 分析…";
    clearInterval(timers[idx]);
    const res = await fetch(`/api/speaker/${idx}/stop`, {method: "POST"});
    const data = await res.json();
    btn.disabled = false;
    btn.textContent = "✅ 已完成";
    btn.classList.remove("recording");
    btn.classList.add("done");
    card.classList.remove("active");
    card.classList.add("done");
    renderFiller(data);
    setStatus(`✅ ${data.name}: ${data.total_fillers} fillers`);
    await maybeAutoReport();
  }
}

function updateTimer(idx) {
  const start = timers[`start-${idx}`];
  if (!start) return;
  const sec = Math.floor((Date.now() - start) / 1000);
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  const el = document.getElementById(`tm-${idx}`);
  if (el) el.textContent = `${m}:${s}`;
}

async function maybeAutoReport() {
  const res = await fetch("/api/agenda");
  const data = await res.json();
  if (data.speakers.every(s => s.ended)) {
    setStatus("🎉 全部完成,自動生成報告…");
    await generateReport();
    // 切到 Report tab
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
    document.querySelector('[data-tab="report"]').classList.add("active");
    document.getElementById("tab-report").classList.add("active");
  }
}

async function generateReport() {
  const res = await fetch("/api/report");
  const data = await res.json();
  document.getElementById("report-text").textContent = data.script || "(no data)";
  setStatus("📣 報告已生成");
}

function setStatus(msg) {
  document.getElementById("status-bar").textContent = msg;
}

// ===== Copy buttons =====
document.getElementById("copy-report").addEventListener("click", () => {
  const t = document.getElementById("report-text").textContent;
  navigator.clipboard.writeText(t).then(() => setStatus("📋 報告已複製"));
});
document.getElementById("generate-report").addEventListener("click", generateReport);

// ===== 共用: 提交 JSON 文字到 server =====
async function submitAgendaJsonText(text) {
  if (!text || !text.trim()) {
    alert("沒內容可提交");
    return;
  }
  setStatus("⏳ 解析中...");
  const blob = new Blob([text], {type: "application/json"});
  const fd = new FormData();
  fd.append("file", blob, "pasted.json");
  try {
    const res = await fetch("/api/upload-agenda-json", {method: "POST", body: fd});
    const data = await res.json();
    if (data.error) {
      setStatus("❌ " + data.error);
      alert("JSON 格式錯: " + data.error + "\n\n檢查是不是純 JSON, 不要包額外文字");
      return;
    }
    setStatus(`✅ 載入 ${data.loaded} 位講者 (Meeting #${data.meeting || "?"})`);
    await loadAgenda();
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
    document.querySelector('[data-tab="counter"]').classList.add("active");
    document.getElementById("tab-counter").classList.add("active");
  } catch (err) {
    setStatus("❌ " + err.message);
  }
}

// 方式 A: 貼上提交
document.getElementById("btn-paste-submit").addEventListener("click", () => {
  const text = document.getElementById("agenda-paste").value;
  submitAgendaJsonText(text);
});

// 方式 B: 檔案上傳
document.getElementById("btn-pick-json").addEventListener("click", () => {
  document.getElementById("agenda-json").click();
});

document.getElementById("agenda-json").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  setStatus("📂 上傳議程 JSON...");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/upload-agenda-json", {method: "POST", body: fd});
    const data = await res.json();
    if (data.error) {
      setStatus("❌ " + data.error);
      alert("解析失敗: " + data.error);
      return;
    }
    setStatus(`✅ 載入 ${data.loaded} 位講者 (Meeting #${data.meeting || "?"})`);
    await loadAgenda();
    // 自動切到 Counter tab
    document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
    document.querySelector('[data-tab="counter"]').classList.add("active");
    document.getElementById("tab-counter").classList.add("active");
  } catch (err) {
    setStatus("❌ " + err.message);
  }
});

// ===== OCR 拍照上傳 (備用) =====
document.getElementById("btn-pick-photo").addEventListener("click", () => {
  document.getElementById("agenda-photo").click();
});

document.getElementById("agenda-photo").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  setStatus("📷 OCR 辨識中…");
  const fd = new FormData();
  fd.append("file", file);
  try {
    const res = await fetch("/api/upload-agenda", {method: "POST", body: fd});
    const data = await res.json();
    if (data.error) {
      setStatus("❌ " + data.error);
      alert("OCR 失敗: " + data.error);
      return;
    }
    showOcrResult(data);
    setStatus(`📷 辨識到 ${data.speakers.length} 位講者,請確認`);
  } catch (err) {
    setStatus("❌ " + err.message);
  }
});

function showOcrResult(data) {
  const wrap = document.getElementById("ocr-result");
  wrap.style.display = "block";
  document.getElementById("ocr-count").textContent = data.speakers.length;
  document.getElementById("ocr-raw").textContent = data.raw_text;

  const list = document.getElementById("ocr-speaker-list");
  list.innerHTML = data.speakers.map((sp, i) => `
    <div class="ocr-row">
      <input type="checkbox" id="ocr-${i}" ${sp.counted ? "checked" : ""}>
      <input type="text" id="ocr-name-${i}" value="${sp.speaker || ""}" placeholder="姓名">
      <input type="text" id="ocr-role-${i}" value="${sp.role || ""}" placeholder="角色">
      <span class="ocr-time">${sp.start || ""}</span>
    </div>
  `).join("");
}

document.getElementById("btn-show-raw").addEventListener("click", () => {
  const el = document.getElementById("ocr-raw");
  el.style.display = el.style.display === "none" ? "block" : "none";
});

document.getElementById("btn-commit").addEventListener("click", async () => {
  const rows = document.querySelectorAll("#ocr-speaker-list .ocr-row");
  const speakers = Array.from(rows).map((row, i) => ({
    speaker: document.getElementById(`ocr-name-${i}`).value.trim(),
    role: document.getElementById(`ocr-role-${i}`).value.trim() || "Speaker",
    counted: document.getElementById(`ocr-${i}`).checked,
    language: "mixed",
  })).filter(s => s.speaker);
  if (speakers.length === 0) {
    alert("沒勾選任何講者");
    return;
  }
  setStatus("⏳ 載入講者…");
  const res = await fetch("/api/commit-speakers", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({speakers}),
  });
  const data = await res.json();
  setStatus(`✅ 已載入 ${data.loaded} 位講者`);
  await loadAgenda();
  // 切到 Counter tab
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
  document.querySelector('[data-tab="counter"]').classList.add("active");
  document.getElementById("tab-counter").classList.add("active");
});

// ===== Init =====
loadAgenda();
setStatus("Ready");
