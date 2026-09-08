// Asistente de flora -- frontend. No build step, no external dependencies,
// just fetch() against the Starlette API in web.py.

const messagesEl = document.getElementById("messages");
const formEl = document.getElementById("chat-form");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send-btn");
const serverGroupsEl = document.getElementById("server-groups");
const toolTotalEl = document.getElementById("tool-total");
const photoGridEl = document.getElementById("photo-grid");
const photoCountEl = document.getElementById("photo-count");
const uploadZoneEl = document.getElementById("upload-zone");
const fileInputEl = document.getElementById("file-input");
const uploadStatusEl = document.getElementById("upload-status");
const placeInputEl = document.getElementById("place-input");

// ---------- Minimal markdown-lite renderer ----------
// Handles just what Claude's replies typically use: headers, bold, inline
// code, and bullet/numbered lists. Escapes HTML first so nothing in a
// tool's output can inject markup.
function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderMarkdownLite(text) {
  const escaped = escapeHtml(text);
  const lines = escaped.split("\n");
  let html = "";
  let inList = null; // "ul" | "ol" | null

  const closeList = () => {
    if (inList) {
      html += `</${inList}>`;
      inList = null;
    }
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = Math.min(heading[1].length + 2, 6);
      html += `<h${level}>${inlineFormat(heading[2])}</h${level}>`;
      continue;
    }

    const bullet = line.match(/^[-*]\s+(.*)$/);
    if (bullet) {
      if (inList !== "ul") {
        closeList();
        html += "<ul>";
        inList = "ul";
      }
      html += `<li>${inlineFormat(bullet[1])}</li>`;
      continue;
    }

    const numbered = line.match(/^\d+\.\s+(.*)$/);
    if (numbered) {
      if (inList !== "ol") {
        closeList();
        html += "<ol>";
        inList = "ol";
      }
      html += `<li>${inlineFormat(numbered[1])}</li>`;
      continue;
    }

    closeList();
    if (line === "") {
      continue;
    }
    html += `<p>${inlineFormat(line)}</p>`;
  }
  closeList();
  return html;
}

function inlineFormat(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

// ---------- Tools checklist ----------

async function loadTools() {
  try {
    const res = await fetch("/api/tools");
    const data = await res.json();
    renderServerGroups(data.servers);
  } catch (err) {
    serverGroupsEl.innerHTML = `<p class="panel-loading">No se pudo cargar la lista de herramientas.</p>`;
  }
}

function renderServerGroups(servers) {
  serverGroupsEl.innerHTML = "";
  let total = 0;

  servers.forEach((server, idx) => {
    total += server.tools.length;

    const group = document.createElement("div");
    group.className = "server-group" + (idx === 0 ? " expanded" : "");

    const header = document.createElement("div");
    header.className = "server-header";
    header.innerHTML = `
      <span class="status-dot${server.error ? " down" : ""}"></span>
      <span class="server-name">${escapeHtml(server.name)}</span>
      <span class="server-tool-count">${server.error ? "caido" : server.tools.length}</span>
      <span class="chevron">&#9656;</span>
    `;
    header.addEventListener("click", () => group.classList.toggle("expanded"));

    const list = document.createElement("ul");
    list.className = "tool-list";
    if (server.error) {
      // A server that failed to start is shown as down rather than omitted, so
      // a missing tool has a visible explanation.
      list.innerHTML = `<li class="tool-error">${escapeHtml(server.error)}</li>`;
      group.append(header, list);
      serverGroupsEl.appendChild(group);
      return;
    }
    list.innerHTML = server.tools
      .map(
        (tool) => `
        <li>
          <span class="tool-check">&#10003;</span>
          <span>
            <span class="tool-name">${escapeHtml(tool.name)}</span>
            <span class="tool-desc">${escapeHtml(tool.description || "")}</span>
          </span>
        </li>`
      )
      .join("");

    group.append(header, list);
    serverGroupsEl.appendChild(group);
  });

  toolTotalEl.textContent = `${total} tools / ${servers.length} servidores`;
}

// ---------- Photos ----------
// The workspace folder is the one place both the Filesystem MCP server and
// flora-mcp can see, so uploading here is all it takes for the assistant to be
// able to identify a photo by name.

const PLACE_KEY = "flora.place";

function formatSize(bytes) {
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} KB`
    : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function currentPlace() {
  return placeInputEl.value.trim();
}

function identifyPrompt(name) {
  const place = currentPlace();
  // Without a place the assistant asks for it (the system prompt tells it to),
  // so an empty field degrades into a question rather than a wrong answer.
  return place
    ? `Identifica la foto ${name}. Estoy en ${place}.`
    : `Identifica la foto ${name}.`;
}

function showUploadStatus(text, isError = false) {
  uploadStatusEl.textContent = text;
  uploadStatusEl.classList.toggle("error", isError);
  uploadStatusEl.hidden = false;
}

function clearUploadStatus() {
  uploadStatusEl.hidden = true;
}

async function loadPhotos() {
  try {
    const res = await fetch("/api/photos");
    const data = await res.json();
    renderPhotos(data.photos);
  } catch (err) {
    photoGridEl.innerHTML = `<p class="panel-loading">No se pudieron cargar las fotos.</p>`;
  }
}

function renderPhotos(photos) {
  photoCountEl.textContent = `${photos.length} foto${photos.length === 1 ? "" : "s"}`;

  if (photos.length === 0) {
    photoGridEl.innerHTML = `<p class="panel-loading">No hay fotos en el workspace todavia.</p>`;
    return;
  }

  photoGridEl.innerHTML = "";
  photos.forEach((photo) => {
    const tile = document.createElement("button");
    tile.className = "photo-tile";
    tile.type = "button";
    tile.title = `Identificar ${photo.name}`;
    tile.innerHTML = `
      <img src="${escapeHtml(photo.url)}" alt="${escapeHtml(photo.name)}" loading="lazy" />
      <span class="photo-meta">
        <span class="photo-name">${escapeHtml(photo.name)}</span>
        <span class="photo-size">${formatSize(photo.size)}</span>
      </span>
      <span class="photo-action">Identificar</span>
    `;
    tile.addEventListener("click", () => sendMessage(identifyPrompt(photo.name)));
    photoGridEl.appendChild(tile);
  });
}

async function uploadFiles(files) {
  const list = Array.from(files);
  if (list.length === 0) return;

  const uploaded = [];
  for (const [index, file] of list.entries()) {
    showUploadStatus(`Subiendo ${file.name} (${index + 1}/${list.length})...`);
    const body = new FormData();
    body.append("file", file);
    try {
      const res = await fetch("/api/upload", { method: "POST", body });
      const data = await res.json();
      if (!res.ok) {
        showUploadStatus(`${file.name}: ${data.error || "no se pudo subir"}`, true);
        continue;
      }
      uploaded.push(data.name);
    } catch (err) {
      showUploadStatus(`${file.name}: no se pudo contactar al servidor.`, true);
    }
  }

  await loadPhotos();

  if (uploaded.length === 1) {
    // One photo is unambiguous -- identify it right away, which is the whole
    // point of uploading it. Several at once would fire several API calls, so
    // those just land in the grid and wait to be clicked.
    clearUploadStatus();
    sendMessage(identifyPrompt(uploaded[0]));
  } else if (uploaded.length > 1) {
    showUploadStatus(`${uploaded.length} fotos subidas. Hace clic en una para identificarla.`);
  }
}

uploadZoneEl.addEventListener("click", () => fileInputEl.click());

fileInputEl.addEventListener("change", () => {
  uploadFiles(fileInputEl.files);
  fileInputEl.value = "";
});

["dragenter", "dragover"].forEach((event) =>
  uploadZoneEl.addEventListener(event, (e) => {
    e.preventDefault();
    uploadZoneEl.classList.add("dragging");
  })
);

["dragleave", "drop"].forEach((event) =>
  uploadZoneEl.addEventListener(event, (e) => {
    e.preventDefault();
    uploadZoneEl.classList.remove("dragging");
  })
);

uploadZoneEl.addEventListener("drop", (e) => {
  if (e.dataTransfer?.files?.length) uploadFiles(e.dataTransfer.files);
});

// The country rarely changes between photos, so remember it for next time.
try {
  placeInputEl.value = localStorage.getItem(PLACE_KEY) || "";
} catch (err) {
  /* private browsing or blocked storage -- the field just starts empty */
}
placeInputEl.addEventListener("change", () => {
  try {
    localStorage.setItem(PLACE_KEY, currentPlace());
  } catch (err) {
    /* not worth bothering the user about */
  }
});

// ---------- Chat ----------

function addMessage(role, { text = "", pending = false, error = false } = {}) {
  const el = document.createElement("div");
  el.className = `message ${role}` + (pending ? " pending" : "") + (error ? " error" : "");

  if (role === "user") {
    el.textContent = text;
  } else if (pending) {
    el.innerHTML = `<span class="typing-dots"><span></span><span></span><span></span></span>`;
  } else {
    el.innerHTML = renderMarkdownLite(text);
  }

  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function addToolTrace(el, toolCalls) {
  if (!toolCalls || toolCalls.length === 0) return;

  const details = document.createElement("details");
  details.className = "tool-trace";
  const count = toolCalls.length;
  details.innerHTML = `
    <summary>${count} herramienta${count === 1 ? "" : "s"} usada${count === 1 ? "" : "s"}</summary>
    <ul>
      ${toolCalls
        .map(
          (call) =>
            `<li><span class="trace-server">${escapeHtml(call.server)}</span>.${escapeHtml(call.tool)}</li>`
        )
        .join("")}
    </ul>
  `;
  el.appendChild(details);
}

async function sendMessage(text) {
  const welcome = document.querySelector(".welcome");
  if (welcome) welcome.remove();

  addMessage("user", { text });
  const pendingEl = addMessage("assistant", { pending: true });

  sendBtn.disabled = true;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();

    pendingEl.classList.remove("pending");
    if (!res.ok || data.error) {
      pendingEl.classList.add("error");
      pendingEl.textContent = `Error: ${data.error || "algo salio mal"}`;
    } else {
      pendingEl.innerHTML = renderMarkdownLite(data.reply);
      addToolTrace(pendingEl, data.tool_calls);
    }
  } catch (err) {
    pendingEl.classList.remove("pending");
    pendingEl.classList.add("error");
    pendingEl.textContent = "Error: no se pudo contactar al asistente.";
  } finally {
    sendBtn.disabled = false;
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  inputEl.style.height = "auto";
  sendMessage(text);
});

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    formEl.requestSubmit();
  }
});

inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 160)}px`;
});

document.querySelectorAll(".example-chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    inputEl.value = chip.dataset.prompt;
    inputEl.focus();
  });
});

loadTools();
loadPhotos();
