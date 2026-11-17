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

$("file-form").onsubmit = (e) => {
  e.preventDefault();
  const file = $("file").files[0];
  if (!file) return toast("請先選擇 .xlsx 檔案", "error");
  const form = new FormData();
  form.append("file", file);
  run(async () => {
    const r = await api("/api/teacher/import/file", { method: "POST", form });
    toast(`匯入成功，共 ${r.question_count} 題`, "ok");
  });
};

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
  setLink($("btn-export-xlsx"), "/api/teacher/export/guided-notes", p !== "no_questions");
  setLink($("btn-export-csv"), "/api/teacher/export/csv", p !== "no_questions");
  for (const id of ["file-form", "url-form", "settings-form"]) {
    $(id).querySelectorAll("input, button").forEach((el) => (el.disabled = p === "open"));
  }

  // 使用者正在編輯的設定欄位不覆蓋
  const active = document.activeElement;
  if (active !== $("group-count")) $("group-count").value = state.group_count;
  if (active !== $("fair-delay")) $("fair-delay").value = state.fair_delay;
  if (active !== $("time-limit")) $("time-limit").value = state.time_limit;
  if (active !== $("fair-mode")) $("fair-mode").checked = state.fair_mode;

  $("questions").innerHTML = state.questions.length
    ? `<p class="small">來源：<strong>${escapeHtml(state.source_name)}</strong>，共 <strong>${state.questions.length}</strong> 題</p>
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
