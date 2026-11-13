// Lógica sin dependencias de VS Code (se prueba con `node test/core.test.js`).
"use strict";

const path = require("path");
const crypto = require("crypto");

function isStudio(dir, exists) {
  return !!dir && exists(path.join(dir, "main.py")) && exists(path.join(dir, "olvgl", "cli.py"));
}

/** Carpeta de Open LVGL Studio: ajuste, variable OLVGL_STUDIO, fichero de instalación o espacio de trabajo. */
function findStudio({ setting, env, homeFile, workspaceFolders = [], exists, read }) {
  const candidates = [];
  if (setting) candidates.push(setting);
  if (env) candidates.push(env);
  if (homeFile && exists(homeFile)) {
    try { candidates.push(read(homeFile).trim()); } catch (e) { /* ilegible */ }
  }
  for (const f of workspaceFolders) {
    candidates.push(f, path.join(f, "open-lvgl-studio"));
  }
  return candidates.find((c) => isStudio(c, exists));
}

/** Python con PySide6: ajuste o el .venv de la aplicación (pythonw en Windows para no abrir consola). */
function findPython({ setting, studio, platform, exists, windowed = false }) {
  if (setting) return setting;
  const win = platform === "win32";
  const names = win ? (windowed ? ["pythonw.exe", "python.exe"] : ["python.exe"]) : ["python3", "python"];
  for (const n of names) {
    const p = win ? path.join(studio, ".venv", "Scripts", n) : path.join(studio, ".venv", "bin", n);
    if (exists(p)) return p;
  }
  return win ? "python" : "python3";
}

/** ¿El YAML tiene una sección lvgl: de primer nivel? */
function looksLikeLvgl(text) {
  return /(^|\n)lvgl:\s*(#.*)?(\r?\n|$)/.test(text || "");
}

/** Widget cuyo bloque contiene la línea del cursor: el último `id:` que empieza antes. */
function widgetAtLine(widgets, line) {
  let best = null;
  for (const w of widgets || []) {
    if (typeof w.line !== "number" || w.line > line) continue;
    if (!best || w.line > best.line) best = w;
  }
  // un `id:` está como mucho una línea por debajo del tipo (- button:\n    id: x)
  if (best && line - best.line > 60) return null;
  return best;
}

function nonce() {
  return crypto.randomBytes(16).toString("hex");
}

function previewHtml(cspSource, scriptUri, n) {
  return `<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: ${cspSource}; style-src 'unsafe-inline' ${cspSource}; script-src 'nonce-${n}';">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font: 12px var(--vscode-font-family); color: var(--vscode-foreground);
         background: var(--vscode-editor-background); }
  header { position: sticky; top: 0; z-index: 3; display: flex; gap: 6px; align-items: center; flex-wrap: wrap;
           padding: 6px 8px; background: var(--vscode-sideBar-background, var(--vscode-editor-background));
           border-bottom: 1px solid var(--vscode-panel-border, #444); }
  button, select { font: inherit; color: var(--vscode-button-secondaryForeground, var(--vscode-foreground));
           background: var(--vscode-button-secondaryBackground, #3a3d41); border: 1px solid transparent;
           border-radius: 3px; padding: 3px 8px; cursor: pointer; }
  button.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
  button:hover { filter: brightness(1.15); }
  #status { margin-left: auto; opacity: .75; white-space: nowrap; }
  #stage { padding: 12px; overflow: auto; }
  #screen { position: relative; display: inline-block; box-shadow: 0 0 0 1px #555, 0 4px 18px rgba(0,0,0,.35); }
  #screen img { display: block; image-rendering: auto; }
  .hit { position: absolute; box-sizing: border-box; border: 1px solid transparent; cursor: pointer; }
  .hit:hover { border: 1px dashed #7C4DFF; background: rgba(124,77,255,.10); }
  .hit.sel { border: 2px solid #7C4DFF; background: rgba(124,77,255,.14); }
  #tip { position: fixed; z-index: 5; pointer-events: none; padding: 2px 6px; border-radius: 3px;
         background: var(--vscode-editorHoverWidget-background, #252526); border: 1px solid var(--vscode-editorHoverWidget-border, #454545);
         display: none; white-space: nowrap; }
  #error { display: none; margin: 12px; padding: 10px; border-radius: 4px; white-space: pre-wrap;
           background: var(--vscode-inputValidation-errorBackground, #5a1d1d); border: 1px solid var(--vscode-inputValidation-errorBorder, #be1100); }
  #warn { margin: 0 12px; opacity: .8; }
</style></head>
<body>
<header>
  <select id="pages" title="Página"></select>
  <button id="fit" title="Ajustar a la ventana">Ajustar</button>
  <button id="z100" title="Tamaño real">100 %</button>
  <button id="refresh" title="Volver a dibujar">⟳</button>
  <button id="designer" class="primary" title="Abrir en Open LVGL Studio">Abrir en el diseñador</button>
  <button id="exportC" title="Exportar ui.c / ui.h">Exportar C</button>
  <span id="status">Cargando…</span>
</header>
<div id="error"></div>
<div id="stage"><div id="screen"><img id="img" alt=""></div></div>
<div id="warn"></div>
<div id="tip"></div>
<script nonce="${n}" src="${scriptUri}"></script>
</body></html>`;
}

module.exports = { findStudio, findPython, looksLikeLvgl, widgetAtLine, previewHtml, nonce, isStudio };
