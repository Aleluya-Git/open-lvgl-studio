// Vista previa LVGL dentro de VS Code.
(function () {
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);
  const img = $("img"), screen = $("screen"), pages = $("pages"), status = $("status");
  const errorBox = $("error"), warn = $("warn"), tip = $("tip");
  let state = vscode.getState() || { zoom: "fit" };
  let current = null;          // última respuesta
  let selected = null;

  function display() { return current ? current.display : { width: 1, height: 1 }; }

  function zoomFactor() {
    if (state.zoom !== "fit") return state.zoom;
    const d = display();
    const avail = Math.max(100, window.innerWidth - 26);
    const availH = Math.max(100, window.innerHeight - 90);
    return Math.min(1.5, avail / d.width, availH / d.height);
  }

  function layout() {
    if (!current) return;
    const z = zoomFactor();
    const d = display();
    img.style.width = `${d.width * z}px`;
    img.style.height = `${d.height * z}px`;
    for (const el of screen.querySelectorAll(".hit")) {
      const w = el._w;
      el.style.left = `${w.x * z}px`; el.style.top = `${w.y * z}px`;
      el.style.width = `${Math.max(4, w.w * z)}px`; el.style.height = `${Math.max(4, w.h * z)}px`;
    }
  }

  function render(data, ms) {
    current = data;
    errorBox.style.display = "none";
    const page = data.rendered[0];
    pages.innerHTML = "";
    for (const p of data.pages) {
      const o = document.createElement("option");
      o.value = p.id; o.textContent = p.name === p.id ? p.id : `${p.name} (${p.id})`;
      if (p.id === page.id) o.selected = true;
      pages.appendChild(o);
    }
    img.src = `data:image/png;base64,${page.png}`;
    for (const el of screen.querySelectorAll(".hit")) el.remove();
    // de abajo arriba: los contenedores primero para que los hijos queden encima
    const list = page.widgets.slice().sort((a, b) => (b.w * b.h) - (a.w * a.h));
    for (const w of list) {
      if (w.w <= 0 || w.h <= 0) continue;
      const el = document.createElement("div");
      el.className = "hit"; el._w = w; el.dataset.id = w.id;
      el.addEventListener("mousemove", (e) => {
        tip.style.display = "block";
        tip.textContent = `${w.type} · ${w.auto ? "(sin id)" : w.id}${w.line === null ? "" : "  — clic: ir al código"}`;
        tip.style.left = `${e.clientX + 12}px`; tip.style.top = `${e.clientY + 12}px`;
        e.stopPropagation();
      });
      el.addEventListener("mouseleave", () => { tip.style.display = "none"; });
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        select(w.id);
        if (typeof w.line === "number") vscode.postMessage({ type: "reveal", line: w.line });
      });
      screen.appendChild(el);
    }
    if (selected) select(selected);
    const nw = page.widgets.length;
    status.textContent = `${data.display.width}×${data.display.height} · ${nw} widgets · ${ms} ms`;
    warn.textContent = (data.warnings || []).length ? `⚠ ${data.warnings.join("  ·  ")}` : "";
    layout();
  }

  function select(id) {
    selected = id;
    for (const el of screen.querySelectorAll(".hit")) el.classList.toggle("sel", el.dataset.id === id);
  }

  window.addEventListener("message", (ev) => {
    const m = ev.data;
    if (m.type === "render") render(m.data, m.ms);
    else if (m.type === "busy") status.textContent = "Dibujando…";
    else if (m.type === "error") {
      errorBox.style.display = "block";
      errorBox.textContent = `No se pudo dibujar: ${m.message}\n\nEl último dibujo correcto sigue debajo. Revisa el YAML o «Salida › Open LVGL Studio».`;
      status.textContent = "Error";
    } else if (m.type === "highlight") select(m.id);
  });

  pages.addEventListener("change", () => vscode.postMessage({ type: "page", id: pages.value }));
  $("fit").addEventListener("click", () => { state.zoom = "fit"; vscode.setState(state); layout(); });
  $("z100").addEventListener("click", () => { state.zoom = 1; vscode.setState(state); layout(); });
  $("refresh").addEventListener("click", () => vscode.postMessage({ type: "refresh" }));
  $("designer").addEventListener("click", () => vscode.postMessage({ type: "designer" }));
  $("exportC").addEventListener("click", () => vscode.postMessage({ type: "exportC" }));
  window.addEventListener("resize", layout);
})();
