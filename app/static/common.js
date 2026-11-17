// 共用工具：身分 token（存在分頁的 sessionStorage）、API 呼叫、WebSocket 自動重連。
const TOKEN_KEY = "buzzer_token";

const Auth = {
  get token() {
    try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; }
  },
  save(token) {
    try { sessionStorage.setItem(TOKEN_KEY, token); } catch { /* 無法儲存時仍可使用到關閉分頁為止 */ }
  },
  clear() {
    try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* ignore */ }
  },
};

async function api(path, { method = "GET", body, form } = {}) {
  const headers = {};
  if (Auth.token) headers.Authorization = `Bearer ${Auth.token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(path, { method, headers, body: payload });
  let data = {};
  try { data = await res.json(); } catch { /* 非 JSON 回應 */ }
  if (!res.ok) {
    let message = data.detail;
    if (Array.isArray(message)) message = "輸入格式不正確";
    const err = new Error(message || `發生錯誤（${res.status}）`);
    err.status = res.status;
    throw err;
  }
  return data;
}

// 建立 WebSocket；斷線後每 1.5 秒重連，重連成功時伺服器會立即送最新快照。
function connectLive(onState, onStatus) {
  let ws;
  let heartbeat;
  let closedByAuth = false;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(Auth.token || "")}`);
    ws.onopen = () => {
      onStatus?.(true);
      heartbeat = setInterval(() => ws.readyState === 1 && ws.send("ping"), 20000);
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "state") onState(msg.state);
    };
    ws.onclose = (event) => {
      clearInterval(heartbeat);
      onStatus?.(false);
      if (event.code === 4401) {
        closedByAuth = true;
        Auth.clear();
        location.href = "/";
        return;
      }
      if (!closedByAuth) setTimeout(open, 1500);
    };
  };
  open();
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

let toastTimer;
function toast(message, kind = "info") {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.setAttribute("role", "status");
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), 3200);
}

function phaseBadge(state) {
  return `<span class="phase phase-${state.phase}">${escapeHtml(state.phase_label)}</span>`;
}

function questionLabel(q) {
  return q.sub_count ? `第 ${q.number} 題（題組 ${q.sub_count} 小題）` : `第 ${q.number} 題`;
}

function answerText(q, answers) {
  if (!q.sub_count) return escapeHtml(answers[0]);
  return answers.map((a, i) => `(${i + 1}) ${escapeHtml(a)}`).join("　");
}

const MARK_LABELS = { correct: "對", wrong: "錯" };

// 結果表；editable=true 時（老師、已結束）每題顯示「對／錯」標記按鈕
function renderResults(state, { editable = false } = {}) {
  const results = state.results;
  if (!results) return "";
  const qmap = Object.fromEntries(state.questions.map((q) => [q.number, q]));
  const rows = results.questions.map((r) => {
    const q = qmap[r.number] || r;
    const markBadge = r.mark && !editable ? `<span class="mark mark-${r.mark}">${MARK_LABELS[r.mark]}</span>` : "";
    const markButtons = editable && r.winner ? `
      <span class="mark-buttons" role="group" aria-label="標記第 ${r.number} 題">
        ${["correct", "wrong"].map((m) => `<button type="button" class="mark-btn ${r.mark === m ? "on " + m : ""}"
            data-number="${r.number}" data-mark="${r.mark === m ? "" : m}">${MARK_LABELS[m]}</button>`).join("")}
      </span>` : "";
    const winner = r.winner
      ? `<strong>${escapeHtml(r.winner.group_name)}</strong>：${answerText(q, r.winner.answers)} ${markBadge}${markButtons}`
      : `<span class="muted">無人搶答</span>`;
    const ranks = r.submissions.length
      ? `<ol class="ranks">${r.submissions.map((s) => `
          <li class="${s.success ? "win" : ""}">
            <span class="who">${escapeHtml(s.group_name)}</span>
            <span class="ans">${answerText(q, s.answers)}</span>
            <span class="meta">${s.elapsed.toFixed(2)} 秒${s.delayed ? `（有效 ${s.effective.toFixed(2)} 秒）` : ""}・${escapeHtml(s.student)}${s.success ? "・成功" : ""}</span>
          </li>`).join("")}</ol>`
      : "";
    return `<tr><th scope="row">${escapeHtml(questionLabel(q))}</th><td>${winner}${ranks}</td></tr>`;
  }).join("");
  const board = results.scoreboard.map((b) =>
    `<tr><td>${escapeHtml(b.group_name)}</td><td><strong>${b.score}</strong></td><td>${b.wins}</td></tr>`).join("");
  return `
    <div class="results">
      <table class="result-table"><thead><tr><th>題號</th><th>成功組別與順位</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="scoreboard"><h3>計分板</h3>
        <table><thead><tr><th>組別</th><th>得分</th><th>成功</th></tr></thead><tbody>${board}</tbody></table>
        <p class="muted small">得分＝老師標記為「對」的題數</p></div>
    </div>`;
}

function logout() {
  Auth.clear();
  location.href = "/";
}

// 倒數顯示：以伺服器給的剩餘秒數為準，本機每 0.25 秒更新；每次新快照重新校正
let countdownTimer;
function showCountdown(el, state) {
  clearInterval(countdownTimer);
  if (state.remaining_seconds == null) {
    el.hidden = true;
    return;
  }
  const endAt = Date.now() + state.remaining_seconds * 1000;
  const tick = () => {
    const left = Math.max(0, Math.ceil((endAt - Date.now()) / 1000));
    el.textContent = `剩餘 ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
    el.classList.toggle("urgent", left <= 10);
  };
  el.hidden = false;
  tick();
  countdownTimer = setInterval(tick, 250);
}
