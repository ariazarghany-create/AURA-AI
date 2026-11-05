const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "aura-ai-chats-v1";
const state = { chats: [], activeId: null, busy: false };
function uid() { return globalThis.crypto?.randomUUID?.() || ${Date.now()}-${Math.random().toString(16).slice(2)}; }
function toast(message) { const el = $("toast"); if (!el) return;
el.textContent = message; el.classList.add("show");
clearTimeout(toast.timer);
toast.timer = setTimeout(() => { el.classList.remove("show"); }, 3500); }
function save() { try { localStorage.setItem( STORAGE_KEY, JSON.stringify(state.chats) ); } catch { toast("فضای ذخیره‌سازی مرورگر پر شده است."); } }
function load() { try { const data = JSON.parse( localStorage.getItem(STORAGE_KEY) || "[]" );
state.chats = Array.isArray(data) ? data : [];
} catch { state.chats = []; }
if (!state.chats.length) { newChat(); } else { state.activeId = state.chats[0].id; renderAll(); } }
function current() { return state.chats.find( c => c.id === state.activeId ); }
function newChat() { const c = { id: uid(), title: "گفت‌وگوی جدید", messages: [], updated: Date.now() };
state.chats.unshift(c); state.activeId = c.id;
save(); renderAll();
$("promptInput")?.focus(); $("sidebar")?.classList.remove("open"); }
function renderHistory() { const box = $("history"); if (!box) return;
box.replaceChildren();
state.chats .sort((a, b) => b.updated - a.updated) .forEach(c => { const b = document.createElement("button");
b.className =
    "history-item" +
    (c.id === state.activeId ? " active" : "");

  b.textContent = c.title;

  b.onclick = () => {
    state.activeId = c.id;
    renderAll();
    $("sidebar")?.classList.remove("open");
  };

  box.append(b);
});
}
function addMessage(role, content) { const c = current(); if (!c) return;
c.messages.push({ role, content }); c.updated = Date.now();
if ( c.messages.filter(m => m.role === "user").length === 1 ) { c.title = content.slice(0, 30) || "گفت‌وگوی جدید"; }
save(); renderAll(); }
function renderMessages() { const c = current(); const box = $("messages");
if (!box) return;
box.replaceChildren();
const welcome = $("welcome");
if (welcome) { welcome.hidden = !!(c && c.messages.length); }
if (!c) return;
const row = document.createElement("div");
row.className = `message ${m.role}`;
const av = document.createElement("div");
av.className = "avatar";
av.textContent =
  m.role === "user" ? "شما" : "✦";

const body = document.createElement("div");
body.className = "message-content";
body.textContent = m.content;

row.append(av, body);
box.append(row);
});
const chatArea = $("chatArea");
if (chatArea) { chatArea.scrollTop = chatArea.scrollHeight; } }
function renderAll() { renderHistory(); renderMessages(); }
function updateStatus() { const isOnline = navigator.onLine;
$("connectionDot")?.classList.toggle( "online", isOnline );
const note = $("offlineNote");
if (note) { note.hidden = isOnline;
if (!isOnline) {
  note.textContent =
    "اتصال اینترنت برقرار نیست. برای استفاده از AURA اینترنت لازم است.";
}
} }
async function askOnline(messages, webSearch = false) {
  const base = (
    window.AURA_CONFIG?.API_BASE || ""
  ).replace(/\/$/, "");

  if (!base) {
    throw new Error("نشانی سرور آنلاین تنظیم نشده است.");
  }

  const response = await fetch(`${base}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      messages,
      web_search: webSearch
    })
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.detail || "ارتباط با سرور ناموفق بود."
    );
  }

  if (!data.reply) {
    throw new Error("پاسخ سرور معتبر نیست.");
  }

  return data.reply;
}
async function submit(text) { if (state.busy || !text.trim()) return;
state.busy = true;
const sendBtn = $("sendBtn"); if (sendBtn) sendBtn.disabled = true;
addMessage("user", text.trim());
try { if (!navigator.onLine) { throw new Error( "اینترنت قطع است. لطفاً اتصال اینترنت را بررسی کن." ); }
const webSearch =
  text.trim().startsWith("جستجو:")
const reply = await askOnline(
  current().messages,
  webSearch
);

addMessage("assistant", reply);
} catch (e) { addMessage( "assistant", متأسفم، مشکلی پیش آمد: ${ e.message || "خطای ناشناخته" } );
} finally { state.busy = false;
if (sendBtn) sendBtn.disabled = false;

$("promptInput")?.focus();
} }
$("chatForm")?.addEventListener("submit", e => { e.preventDefault();
const input = $("promptInput"); if (!input) return;
const value = input.value;
input.value = ""; input.style.height = "auto";
submit(value); });
$("promptInput")?.addEventListener("input", e => { e.target.style.height = "auto";
e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px"; });
$("newChat")?.addEventListener("click", newChat);
$("menuBtn")?.addEventListener("click", () => { $("sidebar")?.classList.toggle("open"); });
$("themeToggle")?.addEventListener("click", () => { document.body.classList.toggle("light");
localStorage.setItem( "aura-theme", document.body.classList.contains("light") ? "light" : "dark" ); });
document.querySelectorAll(".suggestion").forEach(b => { b.addEventListener("click", () => { const input = $("promptInput"); if (!input) return;
input.value = b.dataset.prompt || "";
input.focus();
}); });
window.addEventListener("online", updateStatus); window.addEventListener("offline", updateStatus);
if (localStorage.getItem("aura-theme") === "light") { document.body.classList.add("light"); }
if ( "serviceWorker" in navigator && location.protocol !== "file:" ) { navigator.serviceWorker .register("./service-worker.js") .catch(() => { toast("ثبت حالت نصب‌پذیر انجام نشد."); }); }
load(); updateStatus();
