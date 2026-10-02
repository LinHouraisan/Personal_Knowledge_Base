"use strict";
const $ = selector => document.querySelector(selector);
const labels = {search: "查资料", review: "做复盘", plan: "定下一步"};
let view = "search", workspace = null, demo = true, lastRun = null, runNumber = 0;
let storageKey = "", toastTimer;
let aiConnection = {available: false, configured: false}, useAI = false, openedNote = null, selectedNote = null;

function el(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function notify(text) {
  $("#toast").textContent = text;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => $("#toast").hidden = true, 6000);
}
async function api(path, body) {
  const response = await fetch(path, {method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? {} : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(75000)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "请检查日期、目标或输入内容。");
  return data;
}
function clearResult() {
  runNumber++;
  lastRun = null;
  $("#results").replaceChildren();
  $("#feedback").hidden = true;
  $("#feedback-form").hidden = true;
  $("#status").textContent = "";
  $("#status").classList.remove("error");
  $("#initial-hint").hidden = false;
}
function activate(next) {
  view = next;
  selectNote(null);
  clearResult();
  document.querySelectorAll("[data-view]").forEach(button => {
    const selected = button.dataset.view === next;
    button.classList.toggle("active", selected);
    if (selected) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
  });
  $("#view-name").textContent = labels[next];
  $("#search-panel").hidden = next !== "search";
  $("#reflection-panel").hidden = next === "search";
  $("#goal-field").hidden = next !== "plan";
  $("#review-scope").hidden = next === "plan";
  $("#focus-field").hidden = next === "plan";
  $("#reflection-heading").textContent = next === "plan" ? "把目标，变成可完成的一步" : "选一段值得回看的时间";
  $("#reflect").textContent = next === "plan" ? "整理下一步行动 ↗" : "整理这段时间 ↗";
  $("#view-title").textContent = {search: "让记下来的，慢慢变成你的。", review: "回看走过的路，也看清卡住的地方。", plan: "不必做很多，先走好下一步。"}[next];
  $("#view-description").textContent = {search: "从笔记里找线索，让每个答案都有一页可回看的依据。", review: "把已完成、正在做和没解决的事分开，计划不会被当成成果。", plan: "从你明确记录的目标和待办出发，留下最多三件具体的事。"}[next];
}
async function openNote(id) {
  try {
    const note = await api("/v1/notes/" + encodeURIComponent(id));
    openedNote = note;
    $("#read-with-ai").hidden = !aiConnection.available;
    $("#note-title").textContent = note.title;
    $("#note-path").textContent = note.relative_path;
    $("#note-content").textContent = note.content;
    const link = $("#open-obsidian");
    link.hidden = demo || !String(note.obsidian_uri).startsWith("obsidian://open?");
    if (!link.hidden) link.href = note.obsidian_uri;
    if (!$("#note-dialog").open) $("#note-dialog").showModal();
  } catch (error) { notify("原文暂时无法打开：" + error.message); }
}
function sourceButton(source) {
  const button = el("button", "查看原文 · " + source.title, "source-link");
  button.type = "button";
  button.addEventListener("click", () => openNote(source.note_id));
  return button;
}
function heading(text, badge) {
  const block = el("div", undefined, "result-heading");
  block.append(el("h2", text));
  if (badge) block.append(el("span", badge, "badge"));
  return block;
}
function renderSearch(data) {
  const target = $("#results");
  if (data.answer) {
    const answer = el("article", undefined, "card result-card");
    answer.append(el("h3", data.method === "deepseek" ? "DeepSeek 依据笔记的回答" : demo ? "从笔记里找到的内容" : "根据资料的回答"), el("p", data.answer));
    target.append(answer);
    if (data.method === "deepseek") target.append(el("p", "由 " + data.model + " 整理；请结合下方原文核对结论。", "field-hint"));
    (data.warnings || []).forEach(text => target.append(el("p", text, "field-hint")));
  }
  target.append(heading("可以回看的出处", (data.sources || []).length + " 条"));
  if (!data.sources?.length) target.append(el("p", "这份资料里还没有找到相关记录。可以换个关键词，或浏览已有笔记。", "result-subtitle"));
  for (const source of data.sources || []) {
    const card = el("article", undefined, "card result-card");
    card.append(el("h3", source.title), el("p", source.excerpt), el("div", source.relative_path, "source-meta"), sourceButton(source));
    target.append(card);
  }
}
function renderReflection(data) {
  const target = $("#results");
  target.append(heading(data.title, "依据 " + data.notes_count + " 篇记录"));
  if (data.status === "no_evidence") target.append(el("p", "所选范围没有足够的明确记录。请调整日期或资料范围；这里不会补写不存在的成果。", "result-subtitle"));
  if (data.goal) {
    const goal = el("article", undefined, "card result-card");
    goal.append(el("h3", "这次的目标：" + data.goal.title), el("p", "只采用与这个目标主题一致的笔记。"), sourceButton(data.goal.source));
    target.append(goal);
  }
  if (data.mode === "review") for (const section of data.sections) {
    const card = el("section", undefined, "card result-card");
    card.append(heading(section.label, String(section.items.length)));
    for (const item of section.items) {
      const row = el("article", undefined, "item-row");
      row.append(el("h3", item.subject), el("p", item.detail), el("div", item.date + (item.occurrences > 1 ? " · 在 " + item.occurrences + " 篇记录里有后续经过" : ""), "source-meta"), sourceButton(item.source));
      if (data.method === "deepseek") row.append(el("p", "原文依据：" + item.source.excerpt, "source-meta"));
      card.append(row);
    }
    target.append(card);
  }
  if (data.actions.length) {
    const card = el("section", undefined, "card result-card");
    card.append(heading(data.method === "deepseek" ? "AI 建议的下一步 · 待你确认" : data.mode === "plan" ? "先做这几件事" : "笔记里留下的下一步", "最多 3 项"));
    data.actions.forEach((item, index) => {
      const row = el("article", undefined, "item-row action-card");
      row.append(el("span", String(index + 1).padStart(2, "0"), "action-number"), el("h3", item.text), el("p", item.reason), el("p", "做到这里算完成：" + item.done_when, "criteria"), sourceButton(item.source));
      card.append(row);
    });
    target.append(card);
  } else if (data.mode === "plan" && data.status !== "no_evidence") target.append(el("p", "这些记录里没有尚未完成的明确行动。先补充一条具体待办，再整理下一步。", "result-subtitle"));
  const warnings = el("div", undefined, "warnings");
  data.warnings.forEach(text => warnings.append(el("div", text)));
  target.append(warnings);
}
function reportText(context, data) {
  if (context.kind === "search" || context.kind === "chat") return "整理来源：" + (data.method === "deepseek" ? "DeepSeek / " + data.model : "离线资料") + "\n问题：" + context.question + "\n\n" + (data.answer || "资料搜索结果") + "\n\n" + (data.sources || []).map(s => s.title + "\n" + s.excerpt + "\n来源：" + s.relative_path).join("\n\n");
  const lines = [data.title, "整理来源：" + (data.method === "deepseek" ? "DeepSeek / " + data.model : "明确记录规则"), "依据记录：" + data.notes_count + " 篇", "范围：" + (context.payload.start_date || "不限") + " 至 " + (context.payload.end_date || "不限"), "整理方式：" + (context.payload.focus === "open" ? "聚焦未完成" : "完整复盘")];
  if (data.goal) lines.push("目标：" + data.goal.title);
  if (data.mode === "review") data.sections.forEach(section => {
    lines.push("\n" + section.label);
    section.items.forEach(item => lines.push("- " + item.text + "\n  来源：" + item.source.relative_path));
  });
  data.actions.forEach((item, index) => lines.push("\n行动 " + (index + 1) + "：" + item.text, "原因：" + item.reason, "完成标准：" + item.done_when, "来源：" + item.source.relative_path));
  lines.push("\n说明", ...data.warnings);
  return lines.join("\n");
}
function currentContext(kind) {
  if (kind === "search" || kind === "chat") {
    const question = $("#query").value.trim();
    if (!question) throw new Error("先写一个问题，或点一下示例问题。");
    return {kind, question, note_id: selectedNote?.note_id || null, engine: useAI ? "deepseek" : "rules"};
  }
  const start = $("#start-date").value, end = $("#end-date").value;
  if (start && end && start > end) throw new Error("开始日期不能晚于结束日期。");
  const payload = {mode: view, scope: view === "plan" ? "all" : $("#scope").value, topic: view === "plan" ? "" : $("#topic").value,
    start_date: start || null, end_date: end || null, focus: view === "plan" ? "all" : $("#focus").value,
    goal_id: view === "plan" ? $("#goal").value : null};
  if (view === "plan" && !payload.goal_id) throw new Error("资料中还没有可选择的明确目标。");
  return {kind: view, payload, engine: useAI ? "deepseek" : "rules"};
}
async function execute(context) {
  if (context.kind !== "search" && context.engine === "deepseek" && !useAI) throw new Error("这条记录需要 DeepSeek，请先切换到 DeepSeek AI 再复查。");
  if (context.kind === "search") return api("/v1/search?q=" + encodeURIComponent(context.question) + "&top_k=5");
  if (context.kind === "chat") return api(context.engine === "deepseek" ? "/v1/ai/chat" : "/v1/chat", {question: context.question, note_id: context.note_id});
  return api(context.engine === "deepseek" ? "/v1/ai/reflection" : "/v1/reflection", context.payload);
}
async function run(kind) {
  if (kind === "search" || !useAI) selectNote(null);
  clearResult();
  const ticket = runNumber;
  const buttons = [$("#search"), $("#ask"), $("#reflect")];
  buttons.forEach(button => button.disabled = true);
  try {
    const context = currentContext(kind);
    $("#status").textContent = context.engine === "deepseek" && kind !== "search" ? "DeepSeek 正在阅读选中的笔记，请稍候…" : "正在阅读笔记，整理依据…";
    const data = await execute(context);
    if (ticket !== runNumber) return;
    if (context.kind === "search" || context.kind === "chat") renderSearch(data); else renderReflection(data);
    lastRun = {context, text: reportText(context, data)};
    $("#status").textContent = "整理完成。你可以打开原文核对，也可以留下反馈。";
    $("#feedback").hidden = false;
    $("#initial-hint").hidden = true;
  } catch (error) {
    if (ticket === runNumber) {
      $("#status").textContent = "这次没有完成：" + error.message;
      $("#status").classList.add("error");
    }
  } finally { buttons.forEach(button => button.disabled = false); }
}
function records() {
  // ponytail: browser-local demo records; use a server store if multi-device sync is needed.
  if (!storageKey) throw new Error("资料尚未加载，暂时不能保存记录。");
  const value = JSON.parse(localStorage.getItem(storageKey) || "[]");
  if (!Array.isArray(value)) throw new Error("本地记录格式有误，未覆盖已有内容。");
  return value;
}
function persist(items) {
  localStorage.setItem(storageKey, JSON.stringify(items));
  $("#history-count").textContent = String(items.length);
}
function saveFeedback(reason) {
  if (!lastRun) return;
  try {
    const items = records();
    items.unshift({id: crypto.randomUUID(), created: new Date().toISOString(), reason, comment: reason === "有帮助" ? "" : $("#comment").value.trim(),
      context: structuredClone(lastRun.context), before: lastRun.text, after: null, resolved: false});
    persist(items);
    $("#feedback-form").hidden = true;
    $("#comment").value = "";
    notify("已保存在改进记录中。原笔记没有改变。");
  } catch (error) { notify("没有保存成功：" + error.message + " 你仍可以导出本次结果。"); }
}
function download(name, text) {
  const url = URL.createObjectURL(new Blob([text], {type: "text/markdown;charset=utf-8"}));
  const link = el("a");
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function details(label, text) {
  const block = el("details");
  block.append(el("summary", label), el("pre", text));
  return block;
}
function showHistory() {
  const list = $("#history-list");
  list.replaceChildren();
  try {
    const items = records();
    $("#history-count").textContent = String(items.length);
    if (!items.length) list.append(el("p", "还没有反馈。先试一次查询或复盘，再标记有帮助或需要改进。", "field-hint"));
    for (const record of items) {
      const card = el("article", undefined, "history-card");
      card.append(el("div", new Date(record.created).toLocaleString("zh-CN", {hour12: false}), "source-meta"), el("h3", record.reason + (record.resolved ? " · 已由你确认解决" : "")));
      if (record.comment) card.append(el("p", record.comment));
      card.append(details("查看保存时的结果", record.before));
      if (record.after !== null) {
        card.append(el("p", record.before === record.after ? "复查结果与之前相同。" : "复查结果有变化，请核对是否解决了问题。"), details("查看复查结果", record.after));
      }
      const actions = el("div", undefined, "actions");
      const recheck = el("button", "重新核对这条记录", "secondary");
      recheck.addEventListener("click", async () => {
        recheck.disabled = true;
        try {
          const context = structuredClone(record.context);
          if (context.payload) context.payload.focus = $("#recheck-focus").value;
          await api("/v1/index/rebuild", {});
          const data = await execute(context);
          const fresh = records();
          const entry = fresh.find(item => item.id === record.id);
          if (!entry) throw new Error("这条记录已不在当前浏览器中。");
          entry.after = reportText(context, data);
          entry.rechecked = new Date().toISOString();
          entry.resolved = false;
          persist(fresh); showHistory(); notify("已保留原结果和复查结果，请对照检查。");
        } catch (error) { notify("复查没有完成：" + error.message); }
        finally { recheck.disabled = false; }
      });
      actions.append(recheck);
      if (record.after !== null && !record.resolved && record.reason !== "有帮助") {
        const resolve = el("button", "我已核对，问题已解决", "plain");
        resolve.addEventListener("click", () => {
          try { const fresh = records(); fresh.find(item => item.id === record.id).resolved = true; persist(fresh); showHistory(); }
          catch (error) { notify("状态没有保存：" + error.message); }
        });
        actions.append(resolve);
      }
      card.append(actions); list.append(card);
    }
  } catch (error) { list.append(el("p", "无法读取改进记录：" + error.message, "field-hint")); }
  if (!$("#history-dialog").open) $("#history-dialog").showModal();
}
async function loadWorkspace() {
  const [data, capabilities, health, connection] = await Promise.all([api("/v1/workspace"), api("/v1/capabilities"), api("/health"), api("/v1/ai/connection")]);
  aiConnection = connection;
  useAI = workspace === null ? connection.configured : useAI && connection.configured;
  workspace = data; demo = capabilities.demo;
  storageKey = "personal-kb:feedback:v1:" + (demo ? "demo" : "configured") + ":" + health.vault_name;
  $("#note-count").textContent = String(data.notes.length);
  $("#goal-count").textContent = String(data.goals.length);
  $("#period-label").textContent = data.start_date && data.end_date ? data.start_date.slice(5).replace("-", ".") + " — " + data.end_date.slice(5).replace("-", ".") : "暂无日期";
  $("#mode-label").textContent = demo ? "公开虚构笔记 · 按记录整理 · 不调用 AI 模型" : "当前配置的知识库 · 问答使用配置模型 · 复盘按明确记录整理";
  $("#side-mode").textContent = demo ? "公开样例演示" : health.vault_name;
  $("#side-description").textContent = demo ? "没有读取你的私人笔记。" : "只读原笔记，反馈由你主动保存。";
  updateAIMode();
  $("#topic").replaceChildren(new Option("全部主题", ""), ...data.topics.map(topic => new Option(topic, topic)));
  $("#goal").replaceChildren(...data.goals.map(goal => new Option(goal.title, goal.id)));
  $("#start-date").value = data.start_date || "";
  $("#end-date").value = data.end_date || "";
  $("#goal-hint").textContent = "目标来自知识库中的明确记录，行动只采用同一主题的资料。";
  $("#note-list").replaceChildren();
  for (const note of data.notes) {
    const row = el("button", undefined, "note-row");
    row.append(el("strong", note.title), el("small", (note.date || "日期未记录") + " · " + note.path));
    row.addEventListener("click", () => openNote(note.id));
    $("#note-list").append(row);
  }
  try { $("#history-count").textContent = String(records().length); } catch (error) { notify(error.message); }
  $("#status").textContent = health.index_ready ? "资料已准备好，可以从一个问题开始。" : "资料还没有准备好，请先刷新资料。";
}

document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => activate(button.dataset.view)));
document.querySelectorAll("[data-close]").forEach(button => button.addEventListener("click", () => $("#" + button.dataset.close).close()));
document.querySelectorAll("[data-question]").forEach(button => button.addEventListener("click", () => { selectNote(null); $("#query").value = button.dataset.question; run("search"); }));
$("#search").addEventListener("click", () => { selectNote(null); run("search"); });
$("#ask").addEventListener("click", () => {
  if (aiConnection.available && !aiConnection.configured) return showAISettings();
  run("chat");
});
$("#reflect").addEventListener("click", () => run(view));
$("#query").addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); run(selectedNote && useAI ? "chat" : "search"); } });
document.querySelectorAll(".input-card input, .input-card select, .input-card textarea").forEach(input => input.addEventListener("input", clearResult));
$("#browse-notes").addEventListener("click", () => $("#notes-dialog").showModal());
$("#refresh-notes").addEventListener("click", async () => {
  $("#refresh-notes").disabled = true; clearResult();
  try { await api("/v1/index/rebuild", {}); await loadWorkspace(); notify("已重新读取资料。"); }
  catch (error) { notify("刷新没有完成：" + error.message); }
  finally { $("#refresh-notes").disabled = false; }
});
document.querySelectorAll("[data-scenario]").forEach(button => button.addEventListener("click", () => {
  if (!workspace) return notify("资料仍在加载，请稍后再试。");
  const scenario = button.dataset.scenario;
  activate(scenario === "goal" ? "plan" : "review");
  $("#start-date").value = workspace.start_date || ""; $("#end-date").value = workspace.end_date || "";
  $("#scope").value = scenario === "goal" ? "all" : scenario;
  $("#topic").value = scenario === "learning" ? "学习方法" : scenario === "project" ? "个人知识库" : ""; $("#focus").value = "all";
  run(view);
}));
$("#helpful").addEventListener("click", () => saveFeedback("有帮助"));
$("#needs-work").addEventListener("click", () => { $("#feedback-form").hidden = false; $("#reason").focus(); });
$("#save-feedback").addEventListener("click", () => saveFeedback($("#reason").value));
$("#open-history").addEventListener("click", showHistory);
$("#export-result").addEventListener("click", () => { if (lastRun) download("知识库整理结果.md", lastRun.text); });
$("#export-history").addEventListener("click", () => {
  try {
    const items = records();
    if (!items.length) return notify("还没有可导出的记录。");
    download("知识库改进记录.md", "# 个人知识库改进记录\n\n" + items.map(item => "## " + item.reason + "\n记录时间：" + item.created + "\n说明：" + item.comment + "\n状态：" + (item.resolved ? "人工确认已解决" : "待核对") + "\n\n### 原结果\n" + item.before + (item.after === null ? "" : "\n\n### 复查结果\n" + item.after)).join("\n\n---\n\n"));
  } catch (error) { notify("导出没有完成：" + error.message); }
});

function selectNote(note) {
  selectedNote = note;
  $("#note-scope").hidden = !note;
  $("#note-scope-title").textContent = note ? "只阅读这一篇：" + note.title : "";
}
function updateAIMode() {
  $("#ask").textContent = demo ? "整理相关摘录" : "根据资料回答";
  $("#analysis-mode").hidden = !aiConnection.available;
  $("#analysis-mode").value = useAI ? "ai" : "rules";
  $("#open-ai").hidden = !aiConnection.available;
  $("#open-ai").textContent = aiConnection.configured ? "DeepSeek 设置" : "连接 DeepSeek";
  if (aiConnection.available) {
    $("#mode-label").textContent = useAI ? "公开虚构笔记 · DeepSeek 真实阅读 · 结论附出处" : "公开虚构笔记 · 离线整理" + (aiConnection.configured ? " · AI 已暂停" : " · DeepSeek 尚未连接");
    $("#ask").textContent = useAI ? "让 DeepSeek 回答" : aiConnection.configured ? "整理相关摘录" : "连接 AI 来回答";
  }
}
function showAISettings() {
  $("#ai-key").value = "";
  $("#ai-model").value = aiConnection.model || "deepseek-flash";
  $("#ai-error").textContent = "";
  $("#ai-connection-status").textContent = aiConnection.verified ? "当前连接已通过检查。" : aiConnection.configured ? "已有本机密钥，本次启动尚未检查连接。" : "还没有保存密钥，离线查资料仍可使用。";
  $("#ai-dialog").showModal();
}
$("#open-ai").addEventListener("click", showAISettings);
$("#ai-dialog").addEventListener("close", () => { $("#ai-key").value = ""; });
$("#analysis-mode").addEventListener("change", () => {
  useAI = $("#analysis-mode").value === "ai" && aiConnection.configured;
  if ($("#analysis-mode").value === "ai" && !aiConnection.configured) showAISettings();
  if (!useAI) selectNote(null);
  clearResult(); updateAIMode();
});
$("#connect-ai").addEventListener("click", async () => {
  const button = $("#connect-ai"); button.disabled = true;
  const key = $("#ai-key").value;
  $("#ai-key").value = "";
  $("#ai-error").textContent = "正在检查连接，只发送一条简短的测试消息…";
  try {
    aiConnection = await api("/v1/ai/connection", {api_key: key, model: $("#ai-model").value});
    useAI = true; clearResult(); updateAIMode(); $("#ai-dialog").close();
    notify("DeepSeek 已连接。现在可以让 AI 阅读笔记、回答问题或做复盘。");
  } catch (error) { $("#ai-error").textContent = error.message; }
  finally { button.disabled = false; }
});
$("#clear-note-scope").addEventListener("click", () => { selectNote(null); clearResult(); });
$("#read-with-ai").addEventListener("click", () => {
  if (!openedNote) return;
  $("#note-dialog").close(); $("#notes-dialog").close();
  activate("search"); selectNote(openedNote);
  $("#query").value = "请解读这篇笔记：主要内容是什么，哪些事已经完成，哪些仍是计划或问题？";
  if (!aiConnection.configured) return showAISettings();
  useAI = true; updateAIMode(); run("chat");
});

loadWorkspace().catch(error => { $("#status").textContent = "资料没有加载成功，请确认演示已启动后刷新页面。"; $("#status").classList.add("error"); $("#side-mode").textContent = "连接未完成"; $("#mode-label").textContent = "运行方式尚未确认"; });
