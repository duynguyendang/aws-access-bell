const FIXTURES = [
  "doorbell_unknown",
  "doorbell_package_window",
  "doorbell_med",
  "doorbell_family",
  "motion_only",
  "motion_night",
];

const ACTIONS = ["leave_at_door", "coming", "not_now", "waiting_for_parent"];
const CHILD_ACTIONS = ["waiting_for_parent", "leave_at_door"];
const GROUNDING_KEY = {
  grounded: "grounded",
  generic: "generic",
  demoted_insufficient_evidence: "demoted",
};
const URGENCY_CLASS = (urgency) =>
  urgency >= 7 ? "u-red" : urgency >= 5 ? "u-amber" : "u-green";
const $ = (id) => document.getElementById(id);

const state = {
  lang: "en",
  mode: "both",
  voice: false,
  child: false,
  strings: {},
  currentEventId: null,
  last: null,
  escalation: null,
  history: new Map(),
  mockMode: false,
};

function bootTokenFromUrl() {
  const url = new URL(window.location.href);
  const token = url.searchParams.get("token");
  if (!token) return;
  document.cookie = `accessbell_token=${encodeURIComponent(token)};path=/;samesite=strict`;
  url.searchParams.delete("token");
  const rest = url.searchParams.toString();
  window.history.replaceState({}, "", url.pathname + (rest ? `?${rest}` : ""));
}

function s(key) {
  return state.strings[key] || "";
}

function fill(key, values) {
  return s(key).replace(/\{(\w+)\}/g, (_, name) => (values[name] ?? ""));
}

function announce(text) {
  $("sr-live").textContent = text;
}

function speak(text) {
  if (!state.voice || state.mode === "caption" || !window.speechSynthesis || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = state.lang === "vi" ? "vi-VN" : "en-US";
  window.speechSynthesis.speak(utterance);
}

const REPLY_KEY = {
  leave_at_door: "reply_leave",
  coming: "reply_coming",
  not_now: "reply_not_now",
  waiting_for_parent: "reply_waiting",
};

function replyLabel(action) {
  return s(REPLY_KEY[action] || "") || action;
}

async function loadMeta() {
  bootTokenFromUrl();
  const health = await (await fetch("/health")).json();
  state.mockMode = Boolean(health.mock_mode);
  const prefs = await (await fetch("/api/prefs")).json();
  state.lang = prefs.language === "vi" ? "vi" : "en";
  state.mode = prefs.mode || "both";
  state.child = localStorage.getItem("accessbell_child") === "1";
  state.voice = localStorage.getItem("accessbell_voice") === "1";
  await loadStrings();
  applyStatic();
}

async function loadStrings() {
  const data = await (await fetch(`/api/ui-strings?lang=${state.lang}`)).json();
  state.strings = data.strings || {};
  document.documentElement.lang = state.lang;
}

function setText(id, key) {
  const element = $(id);
  if (element) element.textContent = s(key);
}

function applyStatic() {
  document.title = s("app_title");
  setText("brand", "app_title");
  setText("h-advise", "recent_alerts");
  setText("h-history", "recent_alerts");
  setText("h-calendar", "door_calendar");
  setText("h-share", "share_title");
  setText("h-demo", "simulate");
  setText("l-window-label", "window_label");
  setText("l-window-start", "window_start");
  setText("l-window-end", "window_end");
  setText("l-recipient", "recipient");
  setText("l-consent", "consent_label");
  setText("add-window", "add_window");
  setText("preview", "preview");
  setText("share", "share_now");
  setText("stop-escalation", "stop_escalation");
  $("lang-toggle").textContent = state.lang === "vi" ? "VI" : "EN";
  $("voice-toggle").textContent = state.voice ? s("voice_on") : s("voice_off");
  $("voice-toggle").setAttribute("aria-pressed", String(state.voice));
  $("child-toggle").textContent = state.child ? s("child_mode_on") : s("child_mode_off");
  $("child-toggle").setAttribute("aria-pressed", String(state.child));
  renderReplies();
  buildDemoBar();
}

function renderReplies() {
  const container = $("replies");
  container.innerHTML = "";
  const actions = state.child ? CHILD_ACTIONS : ACTIONS;
  actions.forEach((action) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "reply";
    button.dataset.action = action;
    button.textContent = replyLabel(action);
    button.addEventListener("click", () => sendReply(action));
    container.appendChild(button);
  });
}

function currentCaption(triage) {
  const suffix = state.lang === "vi" ? "caption_vi" : "caption_en";
  if (state.child && state.last && state.last.childCaption) {
    return state.last.childCaption;
  }
  return triage[suffix] || triage.caption_en || "";
}

function renderAlert(eventId, triage, why, childCaption) {
  state.currentEventId = eventId ?? state.currentEventId;
  state.last = { eventId: state.currentEventId, triage, why, childCaption };
  const caption = currentCaption(triage);
  $("caption").textContent = caption;
  $("why").textContent = why ? `${s("why")}: ${why[state.lang] || why.en || ""}` : "";
  $("category").textContent = triage.category || "";
  $("urgency").textContent = triage.urgency != null ? fill("urgency", { value: triage.urgency }) : "";
  $("confidence").textContent =
    triage.confidence != null ? fill("confidence", { value: Math.round(triage.confidence * 100) }) : "";
  $("grounding").textContent = s(GROUNDING_KEY[triage.grounding] || "generic");
  $("context").textContent = triage.context_status === "timeout" ? s("context_timeout") : "";
  renderEvidence(triage.evidence);
  $("alert").className = `alert ${URGENCY_CLASS(triage.urgency || 0)}`;
  speak(caption);
  announce(caption);
}

function renderRaw(msg) {
  $("clock").textContent = new Date().toLocaleTimeString();
  $("caption").textContent = msg.text || "";
  $("category").textContent = msg.category || "";
  $("urgency").textContent = "";
  $("confidence").textContent = "";
  $("grounding").textContent = "";
  $("context").textContent = "";
  $("latency").textContent = msg.latency_ms != null ? fill("latency", { ms: msg.latency_ms }) : "";
  renderEvidence([]);
  $("alert").className = "alert u-amber";
  upsertHistory(msg.event_id, { caption: msg.text || "", tag: msg.category || "", urgency: 4 });
}

function renderEvidence(evidence) {
  const container = $("evidence");
  container.innerHTML = "";
  (evidence || []).forEach((item) => {
    const span = document.createElement("span");
    span.textContent = item;
    container.appendChild(span);
  });
}

function upsertHistory(eventId, values) {
  let item = state.history.get(eventId);
  if (!item) {
    item = document.createElement("li");
    item.dataset.eventId = String(eventId);
    const time = document.createElement("time");
    time.textContent = new Date().toLocaleTimeString();
    const caption = document.createElement("span");
    caption.className = "h-caption";
    const tag = document.createElement("span");
    tag.className = "h-tag";
    item.appendChild(time);
    item.appendChild(caption);
    item.appendChild(tag);
    state.history.set(eventId, item);
    $("history").prepend(item);
  }
  item.querySelector(".h-caption").textContent = values.caption || "";
  item.querySelector(".h-tag").textContent = values.tag || "";
  item.className = URGENCY_CLASS(values.urgency || 0);
  while ($("history").children.length > 8) {
    const last = $("history").lastChild;
    state.history.delete(Number(last.dataset.eventId));
    last.remove();
  }
}

function setStatus(key, cls) {
  const element = $("status");
  element.textContent = s(key);
  element.className = `status status-${cls}`;
}

async function sendReply(action) {
  if (!state.currentEventId) return;
  const response = await fetch(`/api/events/${state.currentEventId}/reply`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }),
  });
  const message = response.ok ? fill("reply_sent", { label: replyLabel(action) }) : s("reply_failed");
  $("note").textContent = message;
  announce(message);
}

function startEscalation(msg) {
  clearEscalationTimer();
  state.escalation = { eventId: msg.event_id, remaining: msg.timeout_seconds, contact: (msg.contacts || []).join(", ") };
  $("escalation").classList.remove("hidden");
  renderEscalationText();
  state.escalation.timer = setInterval(tickEscalation, 1000);
}

function renderEscalationText() {
  $("escalation-text").textContent = fill("escalation_waiting", {
    seconds: Math.max(state.escalation.remaining, 0),
    contact: state.escalation.contact,
  });
}

function tickEscalation() {
  if (!state.escalation) return;
  state.escalation.remaining -= 1;
  if (state.escalation.remaining <= 0) {
    clearEscalationTimer();
    return;
  }
  renderEscalationText();
}

function clearEscalationTimer() {
  if (state.escalation && state.escalation.timer) clearInterval(state.escalation.timer);
}

function stopEscalation() {
  if (!state.escalation) return;
  fetch("/api/escalation/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event_id: state.escalation.eventId, source: "pwa" }),
  });
}

function endEscalation() {
  clearEscalationTimer();
  state.escalation = null;
  $("escalation").classList.add("hidden");
  $("note").textContent = s("escalation_stopped");
  announce(s("escalation_stopped"));
}

function fireEscalation(msg) {
  const contact = (msg.contacts || []).join(", ");
  clearEscalationTimer();
  state.escalation = null;
  $("escalation").classList.add("hidden");
  const message = fill("escalation_sent", { contact });
  $("note").textContent = message;
  announce(message);
  upsertHistory(msg.event_id, { caption: message, tag: "escalation", urgency: 9 });
}

function connectStream() {
  const source = new EventSource("/api/stream");
  source.onopen = () => setStatus("status_live", "live");
  source.onerror = () => setStatus("status_disconnected", "down");
  source.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === "alert_raw") renderRaw(msg);
    if (msg.type === "alert_enriched") {
      renderAlert(msg.event_id, msg.triage, msg.why, (msg.caption_child || {})[state.lang]);
      upsertHistory(msg.event_id, {
        caption: (msg.triage && (msg.triage[`caption_${state.lang}`] || msg.triage.caption_en)) || "",
        tag: (msg.triage && msg.triage.category) || "",
        urgency: (msg.triage && msg.triage.urgency) || 0,
      });
    }
    if (msg.type === "escalation_armed") startEscalation(msg);
    if (msg.type === "escalation_sent") fireEscalation(msg);
    if (msg.type === "escalation_stopped") endEscalation();
  };
}

async function loadHistory() {
  const data = await (await fetch("/api/events?limit=8")).json();
  (data.events || []).forEach((event) => {
    upsertHistory(event.id, {
      caption: (event.triage && (event.triage[`caption_${state.lang}`] || event.triage.caption_en)) || "",
      tag: (event.triage && event.triage.category) || "",
      urgency: (event.triage && event.triage.urgency) || 0,
    });
  });
}

async function loadAdvise() {
  const data = await (await fetch("/api/advise")).json();
  const list = $("advise");
  list.innerHTML = "";
  (data.suggestions || []).forEach((suggestion) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = suggestion.reason || suggestion.kind;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = s("add_window");
    button.addEventListener("click", () => {
      $("w-label").value = suggestion.reason || "";
      $("w-label").focus();
    });
    item.appendChild(text);
    item.appendChild(button);
    list.appendChild(item);
  });
}

async function loadWindows() {
  const data = await (await fetch("/api/expected")).json();
  const list = $("windows");
  list.innerHTML = "";
  const windows = data.windows || [];
  if (!windows.length) {
    const empty = document.createElement("li");
    empty.textContent = s("no_windows");
    list.appendChild(empty);
    return;
  }
  windows.forEach((window) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = `${window.label} (${window.window_start} → ${window.window_end})`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = s("clear");
    button.addEventListener("click", async () => {
      await fetch(`/api/expected/${window.id}`, { method: "DELETE" });
      loadWindows();
    });
    item.appendChild(text);
    item.appendChild(button);
    list.appendChild(item);
  });
}

async function loadShares() {
  const data = await (await fetch("/api/share/log")).json();
  const list = $("shares");
  list.innerHTML = "";
  const entries = data.log || [];
  if (!entries.length) {
    const empty = document.createElement("li");
    empty.textContent = s("no_shares");
    list.appendChild(empty);
    return;
  }
  entries.forEach((entry) => {
    const item = document.createElement("li");
    const text = document.createElement("span");
    text.textContent = `${entry.recipient}: ${entry.message.split("\n")[0]}`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = s("revoke");
    button.addEventListener("click", async () => {
      await fetch(`/api/share/${entry.id}/revoke`, { method: "POST" });
      loadShares();
    });
    item.appendChild(text);
    item.appendChild(button);
    list.appendChild(item);
  });
}

function buildDemoBar() {
  const section = $("demo");
  section.classList.toggle("hidden", !state.mockMode);
  if (!state.mockMode) return;
  const container = $("demo-buttons");
  container.innerHTML = "";
  FIXTURES.forEach((fixture) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "reply";
    button.textContent = fixture;
    button.addEventListener("click", async () => {
      const response = await fetch(`/api/simulate?fixture=${encodeURIComponent(fixture)}`, { method: "POST" });
      if (!response.ok) $("note").textContent = `${s("reply_failed")}: ${response.status}`;
    });
    container.appendChild(button);
  });
}

function wireControls() {
  $("stop-escalation").addEventListener("click", stopEscalation);
  $("voice-toggle").addEventListener("click", () => {
    state.voice = !state.voice;
    localStorage.setItem("accessbell_voice", state.voice ? "1" : "0");
    applyStatic();
  });
  $("child-toggle").addEventListener("click", () => {
    state.child = !state.child;
    localStorage.setItem("accessbell_child", state.child ? "1" : "0");
    applyStatic();
    if (state.last) renderAlert(state.last.eventId, state.last.triage, state.last.why, state.last.childCaption);
  });
  $("lang-toggle").addEventListener("click", async () => {
    const next = state.lang === "vi" ? "en" : "vi";
    await fetch("/api/prefs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: state.mode, language: next }),
    });
    window.location.reload();
  });
  $("calendar-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    await fetch("/api/expected", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        kind: "ding",
        label: $("w-label").value,
        window_start: $("w-start").value,
        window_end: $("w-end").value,
        source: "pwa",
      }),
    });
    $("calendar-form").reset();
    loadWindows();
  });
  $("consent").addEventListener("change", () => {
    $("share").disabled = !$("consent").checked;
  });
  $("preview").addEventListener("click", async () => {
    const response = await fetch("/api/share/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent: false, recipient: $("recipient").value }),
    });
    const data = await response.json();
    $("share-preview").textContent = data.message || "";
  });
  $("share").addEventListener("click", async () => {
    await fetch("/api/share", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ consent: true, recipient: $("recipient").value }),
    });
    $("consent").checked = false;
    $("share").disabled = true;
    loadShares();
  });
}

function enableDpadNavigation() {
  const NAV_KEYS = ["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"];
  const focusables = () =>
    Array.from(document.querySelectorAll("button, input, select")).filter((el) => el.offsetParent !== null);
  document.addEventListener("keydown", (event) => {
    if (!NAV_KEYS.includes(event.key)) return;
    const items = focusables();
    if (!items.length) return;
    const index = items.indexOf(document.activeElement);
    let next = 0;
    if (index !== -1) {
      const forward = event.key === "ArrowRight" || event.key === "ArrowDown";
      next = forward ? (index + 1) % items.length : (index - 1 + items.length) % items.length;
    }
    items[next].focus();
    event.preventDefault();
  });
}

function startClock() {
  const tick = () => {
    $("clock").textContent = new Date().toLocaleTimeString();
  };
  setInterval(tick, 1000);
  tick();
}

async function boot() {
  wireControls();
  enableDpadNavigation();
  startClock();
  setStatus("status_connecting", "connecting");
  await loadMeta();
  connectStream();
  await Promise.all([loadHistory(), loadAdvise(), loadWindows(), loadShares()]);
}

boot();