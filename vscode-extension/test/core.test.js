// node test/core.test.js
"use strict";
const assert = require("assert");
const path = require("path");
const core = require("../lib/core");

const files = new Set([
  path.join("C:/studio", "main.py"), path.join("C:/studio", "olvgl", "cli.py"),
  path.join("C:/studio", ".venv", "Scripts", "pythonw.exe"), path.join("C:/studio", ".venv", "Scripts", "python.exe"),
  "home.txt",
]);
const exists = (p) => files.has(p);

assert.strictEqual(core.findStudio({ setting: "C:/studio", exists, read: () => "" }), "C:/studio");
assert.strictEqual(core.findStudio({ homeFile: "home.txt", exists, read: () => "C:/studio\n" }), "C:/studio");
// carpeta abierta en VS Code que contiene open-lvgl-studio/
const ws = path.join("C:/", "workspace");
const nested = new Set([path.join(ws, "open-lvgl-studio", "main.py"), path.join(ws, "open-lvgl-studio", "olvgl", "cli.py")]);
assert.strictEqual(core.findStudio({ workspaceFolders: [ws], exists: (p) => nested.has(p), read: () => "" }),
  path.join(ws, "open-lvgl-studio"));
assert.strictEqual(core.findStudio({ setting: "C:/nada", exists, read: () => "" }), undefined);

assert.strictEqual(core.findPython({ studio: "C:/studio", platform: "win32", exists, windowed: true }),
  path.join("C:/studio", ".venv", "Scripts", "pythonw.exe"));
assert.strictEqual(core.findPython({ studio: "C:/studio", platform: "win32", exists }),
  path.join("C:/studio", ".venv", "Scripts", "python.exe"));
assert.strictEqual(core.findPython({ setting: "py", studio: "C:/studio", platform: "win32", exists }), "py");
assert.strictEqual(core.findPython({ studio: "/x", platform: "linux", exists: () => false }), "python3");

assert.ok(core.looksLikeLvgl("esphome:\n  name: x\nlvgl:\n  pages: []\n"));
assert.ok(core.looksLikeLvgl("lvgl:   # comentario\r\n  pages: []"));
assert.ok(!core.looksLikeLvgl("esphome:\n  lvgl: no\n"));

const wl = [{ id: "a", line: 10 }, { id: "b", line: 20 }, { id: "c", line: null }];
assert.strictEqual(core.widgetAtLine(wl, 15).id, "a");
assert.strictEqual(core.widgetAtLine(wl, 25).id, "b");
assert.strictEqual(core.widgetAtLine(wl, 5), null);
assert.strictEqual(core.widgetAtLine(wl, 200), null);

const html = core.previewHtml("vscode-resource:", "x.js", "abc");
assert.ok(html.includes("nonce-abc") && html.includes('src="x.js"'));
console.log("core.test.js: OK");
