const {test} = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function page() {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, {value: "", textContent: "", hidden: false, handlers: {},
      classList: {add(){}, remove(){}, toggle(){}}, replaceChildren(){}, append(){},
      addEventListener(name, handler) { this.handlers[name] = handler; }, showModal(){}, close(){}, focus(){}});
    return elements.get(id);
  }
  const responses = {
    "/v1/workspace": {notes: [], goals: [], topics: []},
    "/v1/capabilities": {demo: true},
    "/health": {index_ready: true, vault_name: "test"},
    "/v1/ai/connection": {available: true, configured: true, model: "deepseek-flash"},
  };
  const context = vm.createContext({
    document: {querySelector: element, querySelectorAll: () => [], createElement: () => element(Symbol())},
    fetch: async url => ({ok: true, json: async () => responses[url]}),
    Option: function(text, value) { this.text = text; this.value = value; },
    localStorage: {getItem: () => null}, AbortSignal,
    setTimeout: () => 1, clearTimeout(){}, structuredClone,
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../app/static/app.js"), "utf8"), context);
  return {element, run: code => vm.runInContext(code, context)};
}

test("refresh preserves the user's paused AI mode", async () => {
  const ui = page();
  await ui.run("loadWorkspace()");
  ui.element("#analysis-mode").value = "rules";
  ui.element("#analysis-mode").handlers.change();
  assert.equal(ui.run("useAI"), false);
  await ui.run("loadWorkspace()");
  assert.equal(ui.run("useAI"), false);
});

test("leaving AI mode clears the single-note scope", async () => {
  const ui = page();
  await ui.run("loadWorkspace()");
  ui.run('selectNote({note_id: "only-note", title: "Selected note"})');
  ui.element("#analysis-mode").value = "rules";
  ui.element("#analysis-mode").handlers.change();
  assert.equal(ui.run("selectedNote"), null);
  assert.equal(ui.element("#note-scope").hidden, true);
});


test("paused AI also blocks a saved AI recheck", async () => {
  const ui = page();
  await ui.run("loadWorkspace()");
  ui.run("useAI = false");
  await assert.rejects(ui.run('execute({kind: "chat", engine: "deepseek", question: "test"})'), /请先切换/);
});
