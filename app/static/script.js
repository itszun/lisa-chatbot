// static/script.js

let sessionId = null;
let working = false;
let cfg = {
  title: "Pokémon Assistant",
  subtitle: "Tanyakan apa saja tentang Pokémon",
  welcome: "Hai! Saya siap membantu info Pokémon. Contoh: 'Info Pikachu' atau 'Ability Charizard'.",
};

const $ = (sel) => document.querySelector(sel);
const chatEl = $("#chat");
const inputEl = $("#input");
const sendBtn = $("#sendBtn");
const resetBtn = $("#resetBtn");
const appTitle = $("#app-title");
const appSubtitle = $("#app-subtitle");

init();

async function init() {
  // Muat config.json (opsional)
  try {
    const res = await fetch("/static/config.json", { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      cfg = { ...cfg, ...data };
    }
  } catch (_) {}
  appTitle.textContent = cfg.title || appTitle.textContent;
  appSubtitle.textContent = cfg.subtitle || appSubtitle.textContent;

  appendAssistant(cfg.welcome);
  await newSession();

  // Auto focus input
  inputEl.focus();

  // Resize textarea otomatis
  inputEl.addEventListener("input", autoResize);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  });

  $("#composer").addEventListener("submit", (e) => {
    e.preventDefault();
    onSend();
  });

  resetBtn.addEventListener("click", async () => {
    await newSession(true);
  });
}

function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 180) + "px";
}

async function newSession(showNotice = false) {
  try {
    const res = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    const data = await res.json();
    sessionId = data.session_id;
    if (showNotice) {
      appendAssistant("Sesi baru dimulai. Silakan ketik pertanyaan.");
    }
  } catch (err) {
    appendError("Gagal membuat sesi baru. Pastikan server Flask berjalan.");
  }
}

async function onSend() {
  if (working) return;
  const text = (inputEl.value || "").trim();
  if (!text) return;
  if (!sessionId) {
    await newSession();
    if (!sessionId) return;
  }

  // Tampilkan pesan user
  appendUser(text);
  inputEl.value = "";
  autoResize();

  // Indikator bot mengetik
  const typingId = appendTyping();

  working = true;
  toggleComposer(false);
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    });

    removeTyping(typingId);

    const data = await res.json();
    if (!res.ok) {
      appendError(data?.error || "Terjadi kesalahan.");
    } else {
      appendAssistant(data.answer || "(kosong)");

      // Tampilkan jejak eksekusi tool (jika ada)
      if (Array.isArray(data.tool_runs) && data.tool_runs.length) {
        for (const run of data.tool_runs) {
          const pretty = JSON.stringify(run.result, null, 2);
          appendToolRun(`🔧 ${run.name}(${JSON.stringify(run.args)})\n${pretty}`);
        }
      }
    }
  } catch (err) {
    removeTyping(typingId);
    appendError("Tidak dapat terhubung ke server. Pastikan app.py berjalan.");
  } finally {
    working = false;
    toggleComposer(true);
  }
}

function toggleComposer(enabled) {
  inputEl.disabled = !enabled;
  sendBtn.disabled = !enabled;
}

function appendUser(text) {
  appendMsg("user", "🧑", text);
}

function appendAssistant(text) {
  appendMsg("assistant", "🤖", text);
}

function appendMsg(kind, icon, text) {
  const wrap = document.createElement("div");
  wrap.className = `message ${kind}`;
  wrap.innerHTML = `
    <div class="avatar">${icon}</div>
    <div class="bubble">${escapeHtml(text)}</div>
  `;
  chatEl.appendChild(wrap);
  scrollToBottom();
}

function appendToolRun(text) {
  const last = chatEl.lastElementChild;
  const note = document.createElement("div");
  note.className = "toolrun";
  note.textContent = text;
  if (last && last.classList.contains("assistant")) {
    last.querySelector(".bubble").appendChild(note);
  } else {
    // fallback
    appendAssistant(text);
  }
  scrollToBottom();
}

function appendTyping() {
  const id = `t_${Date.now()}`;
  const wrap = document.createElement("div");
  wrap.className = "message assistant";
  wrap.id = id;
  wrap.innerHTML = `
    <div class="avatar">🤖</div>
    <div class="bubble">
      <span class="typing"><span></span><span></span><span></span></span>
    </div>
  `;
  chatEl.appendChild(wrap);
  scrollToBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function appendError(text) {
  const wrap = document.createElement("div");
  wrap.className = "message assistant";
  wrap.innerHTML = `
    <div class="avatar">⚠️</div>
    <div class="bubble" style="border-color:#5a2430;background:#2a0f1a;color:#ffdce1">
      ${escapeHtml(text)}
    </div>
  `;
  chatEl.appendChild(wrap);
  scrollToBottom();
}

function scrollToBottom() {
  chatEl.scrollTop = chatEl.scrollHeight;
}

function escapeHtml(str) {
  return (str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
