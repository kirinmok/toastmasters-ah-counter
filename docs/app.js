// ===== Filler 欄位定義 =====
const FILLERS = [
  {key: "uh_um",   label: "uh/um"},
  {key: "like",    label: "like"},
  {key: "so",      label: "so/well"},
  {key: "you_know", label: "you know"},
  {key: "actually", label: "actually"},
  {key: "ah_en",    label: "嗯/啊"},
  {key: "na_ge",    label: "那個"},
  {key: "jiu_shi",  label: "就是"},
  {key: "ran_hou",  label: "然後"},
  {key: "dui",      label: "對/所以"},
];

const STORE_KEY = "ah_counter_v1";

let speakers = [];

// ===== localStorage =====
function save() {
  localStorage.setItem(STORE_KEY, JSON.stringify(speakers));
}
function load() {
  try {
    const s = localStorage.getItem(STORE_KEY);
    if (s) speakers = JSON.parse(s);
  } catch {}
}

// ===== Tabs =====
document.querySelectorAll(".tab").forEach(t => {
  t.addEventListener("click", () => switchTab(t.dataset.tab));
});
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(x => x.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(x => x.classList.remove("active"));
  document.querySelector(`[data-tab="${name}"]`).classList.add("active");
  document.getElementById(`tab-${name}`).classList.add("active");
}

// ===== 載入講者 =====
document.getElementById("btn-load").addEventListener("click", () => {
  const text = document.getElementById("speakers-input").value.trim();
  if (!text) {
    alert("請至少輸入一位講者");
    return;
  }
  const lines = text.split("\n").map(l => l.trim()).filter(Boolean);
  speakers = lines.map((line, i) => {
    const parts = line.split(",").map(s => s.trim());
    const name = parts[0] || `Speaker ${i+1}`;
    const role = parts.slice(1).join(", ") || "Speaker";
    return {
      idx: i,
      name,
      role,
      fillers: Object.fromEntries(FILLERS.map(f => [f.key, 0])),
      done: false,
    };
  });
  save();
  renderCards();
  setStatus(`✅ 載入 ${speakers.length} 位講者`);
  switchTab("count");
});

document.getElementById("btn-clear-all").addEventListener("click", () => {
  if (!confirm("確定清空所有資料?")) return;
  speakers = [];
  save();
  document.getElementById("speakers-input").value = "";
  renderCards();
  setStatus("🗑️ 已清空");
});

// ===== 渲染講者卡片 =====
function renderCards() {
  const container = document.getElementById("speaker-cards");
  if (!speakers.length) {
    container.innerHTML = `
      <div class="section-card" style="text-align:center;color:#777;padding:30px">
        📋 還沒有講者<br><br>
        請到 <b>✏️ 設定</b> tab 輸入今晚講者
      </div>`;
    return;
  }
  container.innerHTML = speakers.map(sp => renderCard(sp)).join("");
  // 綁定按鈕事件
  speakers.forEach(sp => bindCard(sp));
}

function renderCard(sp) {
  const total = Object.values(sp.fillers).reduce((a, b) => a + b, 0);
  const cls = sp.done ? "done" : "";
  const fillerCells = FILLERS.map(f => {
    const n = sp.fillers[f.key];
    let badgeCls = "zero";
    if (n >= 5) badgeCls = "hot";
    else if (n >= 3) badgeCls = "warn";
    else if (n > 0) badgeCls = "";
    return `
      <div class="filler-btn ${badgeCls}" data-sp="${sp.idx}" data-fk="${f.key}">
        <span class="word">${f.label}</span>
        <span class="count">${n}</span>
      </div>`;
  }).join("");
  return `
    <div class="speaker-card ${cls}" id="card-${sp.idx}">
      <div class="speaker-header">
        <div class="speaker-name">
          <span class="name">${escapeHtml(sp.name)}</span>
          <span class="role">${escapeHtml(sp.role)}</span>
        </div>
        <div class="speaker-total">${total}</div>
      </div>
      <div class="filler-grid">${fillerCells}</div>
      <div class="filler-actions">
        <button data-action="reset" data-sp="${sp.idx}">↩️ 重置這位</button>
        <button data-action="done" data-sp="${sp.idx}">${sp.done ? "↻ 取消完成" : "✅ 標記完成"}</button>
      </div>
    </div>`;
}

function bindCard(sp) {
  const card = document.getElementById(`card-${sp.idx}`);
  if (!card) return;
  card.querySelectorAll(".filler-btn").forEach(b => {
    b.addEventListener("click", () => {
      const fk = b.dataset.fk;
      sp.fillers[fk] = (sp.fillers[fk] || 0) + 1;
      save();
      renderCards();
    });
    // 長按減一
    let pressTimer;
    b.addEventListener("touchstart", () => {
      pressTimer = setTimeout(() => {
        const fk = b.dataset.fk;
        if (sp.fillers[fk] > 0) {
          sp.fillers[fk]--;
          save();
          renderCards();
        }
      }, 500);
    });
    b.addEventListener("touchend", () => clearTimeout(pressTimer));
    // 右鍵減一 (桌面)
    b.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const fk = b.dataset.fk;
      if (sp.fillers[fk] > 0) {
        sp.fillers[fk]--;
        save();
        renderCards();
      }
    });
  });
  card.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("click", () => {
      const action = btn.dataset.action;
      if (action === "reset") {
        if (!confirm(`重置 ${sp.name} 所有 filler?`)) return;
        Object.keys(sp.fillers).forEach(k => sp.fillers[k] = 0);
      } else if (action === "done") {
        sp.done = !sp.done;
      }
      save();
      renderCards();
    });
  });
}

// ===== 生成英文報告 =====
function generateReport() {
  if (!speakers.length) return "(尚未載入講者)";
  const lines = [];
  lines.push("Thank you, Toastmaster. Good evening everyone.");
  lines.push("");
  lines.push("Tonight my role was to listen for filler words and unnecessary repetitions. Here are my observations:");
  lines.push("");

  speakers.forEach(sp => {
    const total = Object.values(sp.fillers).reduce((a, b) => a + b, 0);
    if (total === 0) {
      lines.push(`- **${sp.name}** (${sp.role}) — excellent flow, no significant fillers detected. Well done!`);
      return;
    }
    const top = Object.entries(sp.fillers)
      .filter(([, n]) => n > 0)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 2)
      .map(([k, n]) => {
        const label = FILLERS.find(f => f.key === k).label;
        return `"${label}" ${n} time${n > 1 ? "s" : ""}`;
      }).join(", ");
    let advice = "";
    if (total <= 3) advice = " Very smooth pacing — well done.";
    else if (total <= 8) advice = " Solid control.";
    else advice = " A few habit words to be aware of next time.";
    lines.push(`- **${sp.name}** (${sp.role}) — about ${total} filler${total > 1 ? "s" : ""}, mainly ${top}.${advice}`);
  });

  lines.push("");
  // 找最流暢
  const withFillers = speakers.filter(sp =>
    Object.values(sp.fillers).reduce((a, b) => a + b, 0) > 0
  );
  if (withFillers.length > 0) {
    const smoothest = withFillers.reduce((min, sp) => {
      const t = Object.values(sp.fillers).reduce((a, b) => a + b, 0);
      const mt = Object.values(min.fillers).reduce((a, b) => a + b, 0);
      return t < mt ? sp : min;
    });
    lines.push(`The smoothest speaker tonight goes to **${smoothest.name}**. Well-paced and confident.`);
    lines.push("");
  }

  lines.push("One reminder for all of us:");
  lines.push("**Filler is not a mistake — it's our brain catching up. The cure is not to speak faster, but to pause longer.**");
  lines.push("");
  lines.push("Thank you. Back to you, Toastmaster.");
  return lines.join("\n");
}

document.getElementById("btn-generate").addEventListener("click", () => {
  document.getElementById("report-text").textContent = generateReport();
  setStatus("📣 報告已生成");
});
document.getElementById("btn-copy-report").addEventListener("click", () => {
  const t = document.getElementById("report-text").textContent;
  navigator.clipboard.writeText(t).then(() => setStatus("📋 已複製"));
});
document.getElementById("copy-opening").addEventListener("click", () => {
  const t = document.getElementById("opening-text").textContent;
  navigator.clipboard.writeText(t).then(() => setStatus("📋 開場詞已複製"));
});

function setStatus(msg) {
  document.getElementById("status-bar").textContent = msg;
}

function escapeHtml(s) {
  return String(s || "").replace(/[<>&"']/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;","'":"&#39;"}[c]));
}

// ===== 現場新增講者 (Table Topics 用) =====
document.getElementById("btn-add-speaker").addEventListener("click", () => {
  const name = document.getElementById("add-name").value.trim();
  const role = document.getElementById("add-role").value.trim() || "Table Topics";
  if (!name) { alert("姓名必填"); return; }
  const idx = speakers.length;
  speakers.push({
    idx, name, role,
    fillers: Object.fromEntries(FILLERS.map(f => [f.key, 0])),
    done: false,
  });
  save();
  renderCards();
  document.getElementById("add-name").value = "";
  document.getElementById("add-role").value = "";
  setStatus(`✅ 新增 ${name}`);
});

// ===== Init =====
load();
renderCards();
setStatus(`Ready — ${speakers.length ? speakers.length + ' 位講者已存' : '請設定講者'}`);
