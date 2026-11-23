// 老師頁：所有操作走 REST，畫面只依 WebSocket 推來的快照重畫。
if (!Auth.token) location.href = "/";

const $ = (id) => document.getElementById(id);
let current = null;

async function run(action, successMessage) {
  try {
    await action();
    if (successMessage) toast(successMessage, "ok");
  } catch (err) {
    toast(err.message, "error");
  }
}

$("btn-open").onclick = () => run(() => api("/api/teacher/open", { method: "POST" }), "搶答開始！");
$("btn-close").onclick = () => run(() => api("/api/teacher/close", { method: "POST" }), "搶答已結束");
$("btn-reset").onclick = () => {
  if (confirm("確定要清除所有作答紀錄嗎？題目會保留。")) {
    run(() => api("/api/teacher/reset", { method: "POST" }), "已重設");
  }
};

// Google Sheets 服務帳號狀態：告訴老師要把試算表共用給哪個 email
async function loadSheetsStatus() {
  const el = $("sheets-status");
  try {
    const s = await api("/api/teacher/sheets-status");
    if (s.configured) {
      el.className = "sheets-status ok";
      el.innerHTML = `請在 Google Sheets 按「共用」，把 <code class="copy">${escapeHtml(s.service_account_email)}</code>
        加為<strong>編輯者</strong>，再貼上網址匯入。`;
    } else {
      el.className = "sheets-status warn";
      el.innerHTML = `<strong>尚未設定 Google 服務帳號。</strong>${escapeHtml(s.hint || "")}`;
    }
  } catch (err) {
    el.className = "sheets-status warn";
    el.textContent = err.message;
  }
}
loadSheetsStatus();

$("btn-writeback").onclick = () => run(async () => {
  $("btn-writeback").disabled = true;
  try {
    const r = await api("/api/teacher/export/google-sheets", { method: "POST" });
    toast(`已寫回 Google Sheets：${r.answered} 題有答案`, "ok");
    window.open(r.url, "_blank", "noopener");
  } finally {
    $("btn-writeback").disabled = current?.phase !== "closed";
  }
});

$("url-form").onsubmit = (e) => {
  e.preventDefault();
  run(async () => {
    const r = await api("/api/teacher/import/url", { method: "POST", body: { url: $("url").value } });
    toast(`匯入成功，共 ${r.question_count} 題`, "ok");
  });
};

$("settings-form").onsubmit = (e) => {
  e.preventDefault();
  run(() => api("/api/teacher/settings", {
    method: "POST",
    body: {
      group_count: Number($("group-count").value),
      fair_mode: $("fair-mode").checked,
      fair_delay: Number($("fair-delay").value),
      time_limit: Number($("time-limit").value),
    },
  }), "設定已儲存");
};

function setLink(el, path, enabled) {
  el.classList.toggle("disabled", !enabled);
  if (enabled) el.href = `${path}?token=${encodeURIComponent(Auth.token)}`;
  else el.removeAttribute("href");
}

function render(state) {
  current = state;
  $("phase").innerHTML = phaseBadge(state);
  const p = state.phase;
  $("btn-open").disabled = p !== "ready";
  $("btn-close").disabled = p !== "open";
  $("btn-reset").disabled = !(p === "ready" || p === "closed");
  $("btn-writeback").disabled = p !== "closed";
  $("btn-writeback").title = p === "closed" ? "把搶答成功的答案直接寫進雲端試算表" : "搶答結束後才能寫回";
  setLink($("btn-export-csv"), "/api/teacher/export/csv", p !== "no_questions");
  for (const id of ["url-form", "settings-form"]) {
    $(id).querySelectorAll("input, button").forEach((el) => (el.disabled = p === "open"));
  }

  // 使用者正在編輯的設定欄位不覆蓋
  const active = document.activeElement;
  if (active !== $("group-count")) $("group-count").value = state.group_count;
  if (active !== $("fair-delay")) $("fair-delay").value = state.fair_delay;
  if (active !== $("time-limit")) $("time-limit").value = state.time_limit;
  if (active !== $("fair-mode")) $("fair-mode").checked = state.fair_mode;

  $("questions").innerHTML = state.questions.length
    ? `<p class="small">來源：<a href="${escapeHtml(state.spreadsheet_url || "#")}" target="_blank" rel="noopener"><strong>${escapeHtml(state.source_name)}</strong></a>，共 <strong>${state.questions.length}</strong> 題</p>
       <ul class="qlist">${state.questions.map((q) =>
         `<li><span>${escapeHtml(questionLabel(q))}</span><code>${escapeHtml([...new Set(q.locations)].join(", "))}</code></li>`).join("")}</ul>`
    : `<p class="muted">尚未匯入題目</p>`;

  $("members").innerHTML = state.groups.map((g) => {
    const names = state.members[String(g.group)] || [];
    return `<li><strong>${escapeHtml(g.group_name)}</strong> ${names.length
      ? names.map(escapeHtml).join("、") : '<span class="muted">尚無成員</span>'}</li>`;
  }).join("");

  $("provisional").textContent = p === "open" ? "（搶答中，結果為暫定）"
    : p === "closed" ? "（可標記成功答案的對錯，計分板會即時更新）" : "";
  $("results").innerHTML = state.questions.length
    ? renderResults(state, { editable: p === "closed" }) : `<p class="muted">尚無資料</p>`;
  showCountdown($("countdown"), state);
}

connectLive(render, (online) => {
  $("live").textContent = online ? "即時連線" : "重新連線中…";
  $("live").className = `live ${online ? "on" : "off"}`;
});

// 標記對錯（事件委派：結果表每次重畫，按鈕都會重新產生）
$("results").addEventListener("click", (e) => {
  const btn = e.target.closest(".mark-btn");
  if (!btn) return;
  const mark = btn.dataset.mark || null;
  run(() => api("/api/teacher/mark", { method: "POST", body: { number: Number(btn.dataset.number), mark } }));
});
