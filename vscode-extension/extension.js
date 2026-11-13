// Open LVGL Studio para VS Code.
// - Abrir el YAML en el diseñador (la app lo vincula y escribe en él).
// - Live Sync: la vista previa sigue el texto sin guardar; si el fichero está
//   abierto en el diseñador, VS Code lo guarda solo para que el diseñador lo recargue,
//   y los cambios del diseñador llegan al editor porque VS Code recarga el fichero.
// - Vista previa: dibujo idéntico al canvas (motor Python en segundo plano), clic en un
//   widget → salta a su línea; mover el cursor → resalta el widget.
// - Diagnósticos en «Problemas» y exportación a C.
"use strict";

const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const core = require("./lib/core");

let output;
let server;
let diagnostics;
let statusItem;
const previews = new Map();      // uri → PreviewPanel
const inDesigner = new Set();    // uris abiertos en el diseñador (para el guardado automático)
const saveTimers = new Map();

function cfg() {
  return vscode.workspace.getConfiguration("olvgl");
}

function log(msg) {
  if (output) output.appendLine(`[${new Date().toLocaleTimeString()}] ${msg}`);
}

// ------------------------------------------------------------------ localizar la aplicación
async function studioPath(ask = true) {
  const folders = (vscode.workspace.workspaceFolders || []).map((f) => f.uri.fsPath);
  const found = core.findStudio({
    setting: cfg().get("studioPath"),
    env: process.env.OLVGL_STUDIO,
    homeFile: path.join(os.homedir(), ".olvgl", "studio_path.txt"),
    workspaceFolders: folders,
    exists: fs.existsSync,
    read: (p) => fs.readFileSync(p, "utf8"),
  });
  if (found || !ask) return found;
  const pick = await vscode.window.showInformationMessage(
    "No encuentro Open LVGL Studio. Elige la carpeta donde está instalado (la que contiene main.py).",
    "Elegir carpeta…");
  if (pick) return selectStudio();
  return undefined;
}

async function selectStudio() {
  const uris = await vscode.window.showOpenDialog({ canSelectFolders: true, canSelectFiles: false,
    openLabel: "Usar esta carpeta" });
  if (!uris || !uris.length) return undefined;
  const dir = uris[0].fsPath;
  if (!fs.existsSync(path.join(dir, "main.py"))) {
    vscode.window.showErrorMessage("Esa carpeta no contiene main.py de Open LVGL Studio.");
    return undefined;
  }
  await cfg().update("studioPath", dir, vscode.ConfigurationTarget.Global);
  if (server) server.stop();
  return dir;
}

function pythonFor(studio, windowed = false) {
  return core.findPython({ setting: cfg().get("pythonPath"), studio, platform: process.platform,
    exists: fs.existsSync, windowed });
}

// ------------------------------------------------------------------ motor (python -m olvgl.cli serve)
class Server {
  constructor(studio) {
    this.studio = studio;
    this.proc = null;
    this.pending = new Map();
    this.nextId = 1;
    this.buffer = "";
  }

  start() {
    if (this.proc) return;
    const py = pythonFor(this.studio);
    log(`Motor: ${py} -m olvgl.cli serve (en ${this.studio})`);
    this.proc = cp.spawn(py, ["-m", "olvgl.cli", "serve"], {
      cwd: this.studio,
      env: Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8", PYTHONUTF8: "1" }),
      windowsHide: true,
    });
    this.proc.stdout.setEncoding("utf8");
    this.proc.stdout.on("data", (chunk) => this._data(chunk));
    this.proc.stderr.setEncoding("utf8");
    this.proc.stderr.on("data", (d) => log(d.trimEnd()));
    this.proc.on("error", (err) => this._fail(`No se pudo arrancar Python: ${err.message}`));
    this.proc.on("exit", (code) => this._fail(`El motor terminó (código ${code})`));
  }

  _data(chunk) {
    this.buffer += chunk;
    let i;
    while ((i = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, i).trim();
      this.buffer = this.buffer.slice(i + 1);
      if (!line) continue;
      let msg;
      try { msg = JSON.parse(line); } catch (e) { log(`Respuesta no JSON: ${line.slice(0, 200)}`); continue; }
      const p = this.pending.get(msg.id);
      if (!p) continue;
      this.pending.delete(msg.id);
      clearTimeout(p.timer);
      if (msg.ok) p.resolve(msg.result);
      else {
        log(msg.trace || msg.error);
        if (msg.license && !this.licenseWarned) {      // la extensión requiere la edición Pro
          this.licenseWarned = true;
          vscode.window.showWarningMessage(msg.error);
        }
        p.reject(new Error(msg.error));
      }
    }
  }

  _fail(reason) {
    log(reason);
    for (const p of this.pending.values()) { clearTimeout(p.timer); p.reject(new Error(reason)); }
    this.pending.clear();
    this.proc = null;
    this.buffer = "";
  }

  request(cmd, args = {}, timeoutMs = 90000) {
    this.start();
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Sin respuesta del motor (${cmd})`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      this.proc.stdin.write(JSON.stringify(Object.assign({ id, cmd }, args)) + "\n");
    });
  }

  stop() {
    if (this.proc) {
      try { this.proc.stdin.write(JSON.stringify({ cmd: "quit" }) + "\n"); } catch (e) { /* cerrado */ }
      try { this.proc.kill(); } catch (e) { /* ya terminó */ }
    }
    this._fail("Motor detenido");
  }
}

async function getServer() {
  const studio = await studioPath();
  if (!studio) throw new Error("Open LVGL Studio no está configurado");
  if (!server || server.studio !== studio) {
    if (server) server.stop();
    server = new Server(studio);
  }
  return server;
}

// ------------------------------------------------------------------ documentos
function isLvglDoc(doc) {
  return doc && doc.uri.scheme === "file" && doc.languageId === "yaml" && core.looksLikeLvgl(doc.getText());
}

function targetUri(arg) {
  if (arg instanceof vscode.Uri) return arg;
  const ed = vscode.window.activeTextEditor;
  return ed ? ed.document.uri : undefined;
}

async function openDesigner(arg) {
  const uri = targetUri(arg);
  if (!uri || uri.scheme !== "file") {
    vscode.window.showWarningMessage("Abre un YAML de ESPHome (o un .olvgl) para llevarlo al diseñador.");
    return;
  }
  const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
  if (doc && doc.isDirty) await doc.save();
  const studio = await studioPath();
  if (!studio) return;
  const py = pythonFor(studio, true);
  log(`Diseñador: ${py} main.py "${uri.fsPath}"`);
  const child = cp.spawn(py, [path.join(studio, "main.py"), uri.fsPath], {
    cwd: studio, detached: true, stdio: "ignore", windowsHide: false });
  child.on("error", (err) => vscode.window.showErrorMessage(`No se pudo abrir el diseñador: ${err.message}`));
  child.unref();
  inDesigner.add(uri.toString());
  updateStatus();
  vscode.window.setStatusBarMessage("$(sync) Live Sync con Open LVGL Studio: los cambios van y vienen por el fichero", 6000);
}

// Live Sync hacia el diseñador: guardar solo los ficheros abiertos en él
function scheduleSave(doc) {
  const key = doc.uri.toString();
  if (!cfg().get("liveSync") || !inDesigner.has(key) || !doc.isDirty) return;
  clearTimeout(saveTimers.get(key));
  saveTimers.set(key, setTimeout(() => {
    saveTimers.delete(key);
    if (doc.isDirty && !doc.isClosed) doc.save();
  }, Math.max(400, cfg().get("liveSyncDelay") + 300)));
}

// ------------------------------------------------------------------ diagnósticos
async function validate(doc, quiet = true) {
  if (!doc || !isLvglDoc(doc)) {
    if (!quiet) vscode.window.showInformationMessage("Este fichero no tiene sección lvgl:.");
    return;
  }
  try {
    const srv = await getServer();
    const res = await srv.request("validate", { path: doc.uri.fsPath, text: doc.getText() });
    const list = (res.diagnostics || []).map((d) => {
      const line = Math.min(Math.max(0, d.line || 0), doc.lineCount - 1);
      const range = doc.lineAt(line).range;
      const sev = d.severity === "error" ? vscode.DiagnosticSeverity.Error
        : d.severity === "warning" ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Information;
      const diag = new vscode.Diagnostic(range, d.message, sev);
      diag.source = "Open LVGL Studio";
      return diag;
    });
    diagnostics.set(doc.uri, list);
    if (!quiet) {
      vscode.window.showInformationMessage(list.length ? `${list.length} aviso(s) en «Problemas».`
        : "✓ El YAML de LVGL se importa sin avisos.");
    }
  } catch (err) {
    if (!quiet) vscode.window.showErrorMessage(err.message);
    log(`validate: ${err.message}`);
  }
}

// ------------------------------------------------------------------ exportar C
async function exportC(arg) {
  const uri = targetUri(arg);
  if (!uri) return;
  const dirs = await vscode.window.showOpenDialog({ canSelectFolders: true, canSelectFiles: false,
    openLabel: "Exportar ui.c / ui.h aquí", defaultUri: vscode.Uri.file(path.dirname(uri.fsPath)) });
  if (!dirs || !dirs.length) return;
  try {
    const srv = await getServer();
    const doc = vscode.workspace.textDocuments.find((d) => d.uri.toString() === uri.toString());
    const res = await srv.request("export-c", { path: uri.fsPath, out: dirs[0].fsPath,
      text: doc ? doc.getText() : undefined });
    const extra = res.warnings && res.warnings.length ? ` (${res.warnings.length} aviso(s), ver Salida)` : "";
    (res.warnings || []).forEach((w) => log(`C: ${w}`));
    const open = await vscode.window.showInformationMessage(`Generados ui.c y ui.h${extra}.`, "Abrir ui.c");
    if (open) vscode.window.showTextDocument(vscode.Uri.file(path.join(dirs[0].fsPath, "ui.c")));
  } catch (err) {
    vscode.window.showErrorMessage(`Exportación C: ${err.message}`);
  }
}

// ------------------------------------------------------------------ vista previa
class PreviewPanel {
  constructor(context, uri, column) {
    this.uri = uri;
    this.page = null;
    this.timer = null;
    this.busy = false;
    this.again = false;
    this.lines = [];
    this.panel = vscode.window.createWebviewPanel("olvglPreview", `LVGL · ${path.basename(uri.fsPath)}`,
      column, { enableScripts: true, retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.file(path.join(context.extensionPath, "media"))] });
    this.panel.iconPath = vscode.Uri.file(path.join(context.extensionPath, "media", "icon.png"));
    const script = this.panel.webview.asWebviewUri(vscode.Uri.file(path.join(context.extensionPath, "media", "preview.js")));
    this.panel.webview.html = core.previewHtml(this.panel.webview.cspSource, script.toString(), core.nonce());
    this.panel.webview.onDidReceiveMessage((m) => this.onMessage(m));
    this.panel.onDidDispose(() => {
      clearTimeout(this.timer);
      previews.delete(this.uri.toString());
    });
    this.refresh(0);
  }

  document() {
    return vscode.workspace.textDocuments.find((d) => d.uri.toString() === this.uri.toString());
  }

  refresh(delay) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.render(), delay === undefined ? cfg().get("liveSyncDelay") : delay);
  }

  async render() {
    if (this.busy) { this.again = true; return; }
    this.busy = true;
    this.post({ type: "busy" });
    try {
      const doc = this.document();
      const srv = await getServer();
      const t0 = Date.now();
      const res = await srv.request("render", { path: this.uri.fsPath,
        text: doc && cfg().get("liveSync") ? doc.getText() : undefined,
        page: this.page, scale: cfg().get("previewScale") });
      const page = res.rendered[0];
      this.page = page.id;
      this.lines = page.widgets.filter((w) => w.line !== null && w.line !== undefined);
      this.post({ type: "render", data: res, ms: Date.now() - t0 });
    } catch (err) {
      this.post({ type: "error", message: err.message });
    } finally {
      this.busy = false;
      if (this.again) { this.again = false; this.refresh(50); }
    }
  }

  post(msg) {
    this.panel.webview.postMessage(msg);
  }

  async onMessage(m) {
    if (m.type === "page") { this.page = m.id; this.refresh(0); }
    else if (m.type === "reveal" && typeof m.line === "number") {
      const doc = this.document() || await vscode.workspace.openTextDocument(this.uri);
      const col = vscode.window.visibleTextEditors.find((e) => e.document === doc);
      const ed = await vscode.window.showTextDocument(doc, { viewColumn: col ? col.viewColumn : vscode.ViewColumn.One,
        preserveFocus: false });
      const line = doc.lineAt(Math.min(m.line, doc.lineCount - 1));
      ed.selection = new vscode.Selection(line.range.start, line.range.end);
      ed.revealRange(line.range, vscode.TextEditorRevealType.InCenterIfOutsideViewport);
    } else if (m.type === "designer") openDesigner(this.uri);
    else if (m.type === "exportC") exportC(this.uri);
    else if (m.type === "refresh") this.refresh(0);
  }

  cursorAt(line) {
    const w = core.widgetAtLine(this.lines, line);
    this.post({ type: "highlight", id: w ? w.id : null });
  }
}

async function showPreview(context, arg, side) {
  const uri = targetUri(arg);
  if (!uri || uri.scheme !== "file") {
    vscode.window.showWarningMessage("Abre un YAML de ESPHome con sección lvgl: para ver la vista previa.");
    return;
  }
  const key = uri.toString();
  const existing = previews.get(key);
  if (existing) { existing.panel.reveal(); existing.refresh(0); return; }
  const column = side ? vscode.ViewColumn.Beside : vscode.ViewColumn.Active;
  previews.set(key, new PreviewPanel(context, uri, column));
}

// ------------------------------------------------------------------ barra de estado
function updateStatus() {
  const ed = vscode.window.activeTextEditor;
  if (ed && isLvglDoc(ed.document)) {
    const live = inDesigner.has(ed.document.uri.toString());
    statusItem.text = live ? "$(sync) LVGL Live Sync" : "$(device-desktop) LVGL";
    statusItem.tooltip = live ? "Abierto en Open LVGL Studio: los cambios se sincronizan por el fichero"
      : "Vista previa LVGL al lado";
    statusItem.show();
  } else {
    statusItem.hide();
  }
}

// ------------------------------------------------------------------ activación
function activate(context) {
  output = vscode.window.createOutputChannel("Open LVGL Studio");
  diagnostics = vscode.languages.createDiagnosticCollection("olvgl");
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusItem.command = "olvgl.showPreviewToSide";
  context.subscriptions.push(output, diagnostics, statusItem);

  const reg = (id, fn) => context.subscriptions.push(vscode.commands.registerCommand(id, fn));
  reg("olvgl.openDesigner", (uri) => openDesigner(uri));
  reg("olvgl.showPreview", (uri) => showPreview(context, uri, false));
  reg("olvgl.showPreviewToSide", (uri) => showPreview(context, uri, true));
  reg("olvgl.validate", () => validate(vscode.window.activeTextEditor && vscode.window.activeTextEditor.document, false));
  reg("olvgl.exportC", (uri) => exportC(uri));
  reg("olvgl.selectStudio", () => selectStudio());
  reg("olvgl.restartServer", () => { if (server) server.stop(); server = null;
    previews.forEach((p) => p.refresh(0)); });

  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((e) => {
      const p = previews.get(e.document.uri.toString());
      if (p && cfg().get("liveSync")) p.refresh();
      scheduleSave(e.document);
    }),
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const p = previews.get(doc.uri.toString());
      if (p) p.refresh(0);
      if (cfg().get("validateOnSave")) validate(doc);
    }),
    vscode.workspace.onDidOpenTextDocument((doc) => { if (cfg().get("validateOnSave")) validate(doc); }),
    vscode.workspace.onDidCloseTextDocument((doc) => diagnostics.delete(doc.uri)),
    vscode.window.onDidChangeActiveTextEditor(() => updateStatus()),
    vscode.window.onDidChangeTextEditorSelection((e) => {
      const p = previews.get(e.textEditor.document.uri.toString());
      if (p) p.cursorAt(e.selections[0].active.line);
    }),
  );
  updateStatus();
  log("Extensión activa");
}

function deactivate() {
  if (server) server.stop();
}

module.exports = { activate, deactivate, _test: { Server } };
