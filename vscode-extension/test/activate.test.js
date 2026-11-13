// Activa la extensión con un «vscode» simulado: comandos registrados y vista previa sin errores.
"use strict";
const assert = require("assert");
const Module = require("module");
const path = require("path");

const registered = {};
const ev = () => ({ dispose() {} });
const fakeVscode = {
  Uri: class { constructor(p) { this.fsPath = p; this.scheme = "file"; } static file(p) { return new fakeVscode.Uri(p); } toString() { return "file://" + this.fsPath; } },
  ViewColumn: { One: 1, Beside: -2, Active: -1 },
  StatusBarAlignment: { Right: 2 },
  DiagnosticSeverity: { Error: 0, Warning: 1, Information: 2 },
  ConfigurationTarget: { Global: 1 },
  workspace: {
    workspaceFolders: [], textDocuments: [],
    getConfiguration: () => ({ get: (k) => ({ liveSync: true, liveSyncDelay: 600, validateOnSave: true, previewScale: 1 })[k], update: async () => {} }),
    onDidChangeTextDocument: ev, onDidSaveTextDocument: ev, onDidOpenTextDocument: ev, onDidCloseTextDocument: ev,
  },
  window: {
    activeTextEditor: undefined, visibleTextEditors: [],
    createOutputChannel: () => ({ appendLine() {}, dispose() {} }),
    createStatusBarItem: () => ({ show() {}, hide() {}, dispose() {} }),
    onDidChangeActiveTextEditor: ev, onDidChangeTextEditorSelection: ev,
    showWarningMessage: async () => undefined, showInformationMessage: async () => undefined,
    showErrorMessage: async () => undefined, setStatusBarMessage() {},
  },
  languages: { createDiagnosticCollection: () => ({ set() {}, delete() {}, dispose() {} }) },
  commands: { registerCommand: (id, fn) => { registered[id] = fn; return { dispose() {} }; } },
};
const origLoad = Module._load;
Module._load = function (request, ...rest) {
  if (request === "vscode") return fakeVscode;
  return origLoad.call(this, request, ...rest);
};
const ext = require(path.join(__dirname, "..", "extension.js"));
const ctx = { subscriptions: [], extensionPath: path.join(__dirname, "..") };
ext.activate(ctx);
const pkg = require("../package.json");
for (const c of pkg.contributes.commands) assert.ok(registered[c.command], `sin registrar: ${c.command}`);
// sin editor activo, los comandos avisan y no fallan
Promise.all([registered["olvgl.showPreviewToSide"](), registered["olvgl.openDesigner"]()]).then(() => {
  ext.deactivate();
  console.log(`activate.test.js: OK (${Object.keys(registered).length} comandos)`);
});
