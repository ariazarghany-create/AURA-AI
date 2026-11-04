import { CreateMLCEngine } from "https://esm.run/@mlc-ai/web-llm";

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "aura-ai-chats-v1";
const MODEL_ID = "Qwen2.5-0.5B-Instruct-q4f16_1-MLC";

const state = {
  chats: [],
  activeId: null,
  busy: false,
  engine: null,
  modelLoading: false
};

function uid() {
  return globalThis.crypto?.randomUUID?.() ||
    `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function toast(message) {
  const el = $("toast");
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => el.classList.remove("show"), 3500);
}

function save() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.chats));
  } catch (e) {
    toast("فضای ذخیره‌سازی مرورگر پر شده است.");
  }
}

function load() {
  try {
    const data = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    state.chats = Array.isArray(data) ? data : [];
  } catch {
    state.chats = [];
  }

  if (!state.chats.length) {
    newChat();
  } else {
    state.activeId = state.chats[0].id;
    renderAll();
  }
}

function current() {
  return state.chats.find(c => c.id === state.activeId);
}

function newChat() {
  const c = {
    id: uid(),
    title: "گفت‌وگوی جدید",
    messages: [],
    updated: Date.now()
  };

  state.chats.unshift(c);
  state.activeId = c.id;
  save();
  renderAll();
  $("promptInput").focus();
  $("sidebar").classList.remove("open");
}

function renderHistory() {
  const box = $("history");
  box.replaceChildren();

  state.chats
    .sort((a, b) => b.updated - a.updated)
    .forEach(c => {
      const b = document.createElement("button");
      b.className = "history-item" +
        (c.id === state.activeId ? " active" : "");
      b.textContent = c.title;

      b.onclick = () => {
        state.activeId = c.id;
        renderAll();
        $("sidebar").classList.remove("open");
      };

      box.append(b);
    });
}

function addMessage(role, content) {
  const c = current();

  c.messages.push({ role, content });
  c.updated = Date.now();

  if (c.messages.filter(m => m.role === "user").length === 1) {
    c.title = content.slice(0, 30) || "گفت‌وگوی جدید";
  }

  save();
  renderAll();
}

function renderMessages() {
  const c = current();
  const box = $("messages");

  box.replaceChildren();
  $("welcome").hidden = !!(c && c.messages.length);

  if (!c) return;

  c.messages.forEach(m => {
    const row = document.createElement("div");
    row.className = `message ${m.role}`;

    const av = document.createElement("div");
    av.className = "avatar";
    av.textContent = m.role === "user" ? "شما" : "✦";

    const body = document.createElement("div");
    body.className = "message-content";
    body.textContent = m.content;

    row.append(av, body);
    box.append(row);
  });

  $("chatArea").scrollTop = $("chatArea").scrollHeight;
}

function renderAll() {
  renderHistory();
  renderMessages();
}

function online() {
  return navigator.onLine;
}

function updateStatus() {
  const isOnline = online();

  $("connectionDot").classList.toggle("online", isOnline);
  $("offlineNote").hidden = $("modeSelect").value !== "offline";
}

async function getOfflineEngine() {
  if (state.engine) return state.engine;

  if (!("gpu" in navigator)) {
    throw new Error(
      "این مرورگر از WebGPU پشتیبانی نمی‌کند؛ حالت آفلاین مدل در این دستگاه در دسترس نیست."
    );
  }

  if (state.modelLoading) {
    throw new Error("مدل در حال آماده‌سازی است؛ چند لحظه دیگر تلاش کن.");
  }

  state.modelLoading = true;

  toast("در حال آماده‌سازی مدل آفلاین؛ دانلود اولیه ممکن است حجیم باشد.");

  try {
    state.engine = await CreateMLCEngine(MODEL_ID, {
      initProgressCallback: (p) => {
        if (p.text) {
          $("offlineNote").textContent = p.text;
        }
      }
    });

    return state.engine;
  } finally {
    state.modelLoading = false;

    $("offlineNote").textContent =
      "حالت آفلاین: فقط چت فعال است و مدل روی این دستگاه نگهداری می‌شود.";
  }
}

async function askOffline(messages) {
  const engine = await getOfflineEngine();

  const result = await engine.chat.completions.create({
    messages: [
      {
        role: "system",
        content: "تو AURA، یک دستیار مفید و مودب هستی. در صورت امکان فارسی پاسخ بده."
      },
      ...messages.map(m => ({
        role: m.role,
        content: m.content
      }))
    ],
    temperature: 0.7,
    max_tokens: 700
  });

  return result.choices?.[0]?.message?.content?.trim() ||
    "پاسخی دریافت نشد.";
}

async function askOnline(messages) {
  const base = (window.AURA_CONFIG?.API_BASE || "").replace(/\/$/, "");

  if (!base) {
    throw new Error(
      "نشانی سرور آنلاین تنظیم نشده است. فایل config.js را طبق README تنظیم کن."
    );
  }

  const response = await fetch(`${base}/api/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ messages })
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || "ارتباط با سرور ناموفق بود.");
  }

  if (!data.reply) {
    throw new Error("پاسخ سرور معتبر نیست.");
  }

  return data.reply;
}

// ارسال پیام با انتقال خودکار بین آنلاین و آفلاین
async function submit(text) {
  if (state.busy || !text.trim()) return;

  const mode = $("modeSelect").value;

  state.busy = true;
  $("sendBtn").disabled = true;

  addMessage("user", text.trim());

  try {
    let reply;

    if (mode === "offline") {
      // حالت آفلاین دستی
      reply = await askOffline(current().messages);

    } else {
      // ابتدا تلاش برای پاسخ آنلاین
      try {
        reply = await askOnline(current().messages);

      } catch (onlineError) {
        // اگر آنلاین ناموفق بود، تلاش برای آفلاین
        toast("اتصال آنلاین در دسترس نیست؛ در حال انتقال به حالت آفلاین...");

        try {
          reply = await askOffline(current().messages);

        } catch (offlineError) {
          throw new Error(
            "اتصال آنلاین و آماده‌سازی مدل آفلاین ناموفق بود. " +
            offlineError.message
          );
        }
      }
    }

    addMessage("assistant", reply);

  } catch (e) {
    addMessage(
      "assistant",
      `متأسفم، مشکلی پیش آمد: ${e.message || "خطای ناشناخته"}`
    );

  } finally {
    state.busy = false;
    $("sendBtn").disabled = false;
    $("promptInput").focus();
  }
}

$("chatForm").addEventListener("submit", e => {
  e.preventDefault();

  const input = $("promptInput");
  const value = input.value;

  input.value = "";
  input.style.height = "auto";

  submit(value);
});

$("promptInput").addEventListener("input", e => {
  e.target.style.height = "auto";
  e.target.style.height =
    Math.min(e.target.scrollHeight, 160) + "px";
});

$("newChat").onclick = newChat;

$("menuBtn").onclick = () =>
  $("sidebar").classList.toggle("open");

$("themeToggle").onclick = () => {
  document.body.classList.toggle("light");

  localStorage.setItem(
    "aura-theme",
    document.body.classList.contains("light") ? "light" : "dark"
  );
};

$("modeSelect").addEventListener("change", updateStatus);

$("modeSelect").addEventListener("change", () => {
  if ($("modeSelect").value === "offline") {
    toast("برای اولین استفاده، مدل آفلاین باید با اینترنت دانلود شود.");
  }
});

document.querySelectorAll(".suggestion").forEach(b => {
  b.onclick = () => {
    $("promptInput").value = b.dataset.prompt;
    $("promptInput").focus();
  };
});

window.addEventListener("online", updateStatus);
window.addEventListener("offline", updateStatus);

if (localStorage.getItem("aura-theme") === "light") {
  document.body.classList.add("light");
}

if ("serviceWorker" in navigator && location.protocol !== "file:") {
  navigator.serviceWorker
    .register("./service-worker.js")
    .catch(() => toast("ثبت حالت نصب‌پذیر انجام نشد."));
}

load();
updateStatus();
