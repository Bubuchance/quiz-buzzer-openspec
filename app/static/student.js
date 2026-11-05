// 學生頁：依快照重畫；尚未送出的草稿保存在 drafts，重畫時不會被清掉。
if (!Auth.token) location.href = "/";

const $ = (id) => document.getElementById(id);
const drafts = {}; // key: "題號-小題索引" -> 文字

const BANNERS = {
  no_questions: "等待老師匯入題目…",
  ready: "題目已就緒，等待老師開啟搶答…",
  open: "搶答開始！填好答案就按「送出」，每題本組只能送出一次。",
  closed: "搶答已結束，請看下方結果。",
};

function inputId(number, index) {
  return `ans-${number}-${index}`;
}

function questionCard(q, state) {
  const mine = state.my_submissions[String(q.number)];
  const open = state.phase === "open";
  const count = Math.max(q.sub_count, 1);
  let body;
  if (mine) {
    body = `<p class="sent">✔ 本組已送出：${answerText(q, mine.answers)} <span class="muted small">（${escapeHtml(mine.student)}）</span></p>`;
  } else {
    const inputs = Array.from({ length: count }, (_, i) => {
      const id = inputId(q.number, i);
      const label = q.sub_count ? `第 ${q.number}-${i + 1} 小題` : `第 ${q.number} 題答案`;
      return `<label class="sr-only" for="${id}">${label}</label>
        <input id="${id}" data-key="${q.number}-${i}" maxlength="500" ${open ? "" : "disabled"}
               placeholder="${q.sub_count ? `(${i + 1})` : "輸入答案"}" value="${escapeHtml(drafts[`${q.number}-${i}`] || "")}">`;
    }).join("");
    body = `<form class="answer-form" data-number="${q.number}" data-count="${count}">
        <div class="inputs">${inputs}</div>
        <button type="submit" class="primary" ${open ? "" : "disabled"}>送出</button>
      </form>`;
  }
  return `<article class="card qcard ${mine ? "done" : ""}"><h2>${escapeHtml(questionLabel(q))}</h2>${body}</article>`;
}

function render(state) {
  $("who").textContent = `${state.me.group_name}／${state.me.name}`;
  $("phase").innerHTML = phaseBadge(state);
  $("banner").className = `banner banner-${state.phase}`;
  $("banner").textContent = state.group_valid ? BANNERS[state.phase] : "你的組別已不存在，請按「離開」後重新加入。";

  const focused = document.activeElement?.id;
  $("questions").innerHTML = state.phase === "closed" ? "" : state.questions.map((q) => questionCard(q, state)).join("");
  if (focused && $(focused) && !$(focused).disabled) $(focused).focus();

  $("results-card").hidden = !state.results;
  $("results").innerHTML = state.results ? renderResults(state) : "";
}

document.addEventListener("input", (e) => {
  if (e.target.dataset.key) drafts[e.target.dataset.key] = e.target.value;
});

document.addEventListener("submit", async (e) => {
  const form = e.target.closest(".answer-form");
  if (!form) return;
  e.preventDefault();
  const number = Number(form.dataset.number);
  const count = Number(form.dataset.count);
  const answers = Array.from({ length: count }, (_, i) => $(inputId(number, i)).value);
  if (answers.some((a) => !a.trim())) {
    return toast(count > 1 ? "題組需填完所有小題" : "答案不可空白", "error");
  }
  try {
    await api("/api/student/submit", { method: "POST", body: { number, answers } });
    toast(`第 ${number} 題已送出`, "ok");
  } catch (err) {
    toast(err.message, "error");
  }
});

connectLive(render, (online) => {
  $("live").textContent = online ? "即時連線" : "重新連線中…";
  $("live").className = `live ${online ? "on" : "off"}`;
});
