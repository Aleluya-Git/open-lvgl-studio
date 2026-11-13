// Protocolo real con `python -m olvgl.cli serve` (no necesita Qt: info y validate).
// Uso: node test/server.test.js [python]
"use strict";
const assert = require("assert");
const Module = require("module");
const path = require("path");

const root = path.resolve(__dirname, "..", "..");
const python = process.argv[2] || (process.platform === "win32"
  ? path.join(root, ".venv", "Scripts", "python.exe") : "python3");
const fakeVscode = {
  workspace: { getConfiguration: () => ({ get: (k) => (k === "pythonPath" ? python : undefined) }) },
};
const origLoad = Module._load;
Module._load = function (request, ...rest) {
  if (request === "vscode") return fakeVscode;
  return origLoad.call(this, request, ...rest);
};
const { Server } = require("../extension.js")._test;

(async () => {
  const srv = new Server(root);
  const demo = path.join(root, "examples", "importar", "panel_demo.yaml");
  const ping = await srv.request("ping");
  assert.ok(ping.version);
  const info = await srv.request("info", { path: demo });
  assert.deepStrictEqual(info.pages.map((p) => p.id), ["inicio", "ajustes"]);
  const val = await srv.request("validate", { path: demo, text: "lvgl:\n  pages: [\n" });
  assert.strictEqual(val.diagnostics[0].severity, "error");
  await assert.rejects(srv.request("nada"), /desconocida/);
  const again = await srv.request("ping");     // el servidor sigue vivo tras un error
  assert.strictEqual(again.version, ping.version);
  srv.stop();
  console.log(`server.test.js: OK (motor ${ping.version})`);
})().catch((e) => { console.error(e); process.exit(1); });
