const FIXTURES = [
  "doorbell_unknown",
  "doorbell_police_claim",
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
const VERIFICATION_KEY = {
  verified: "verification_verified",
  unverified: "verification_unverified",
  contradiction: "verification_contradiction",
  no_claim: "verification_no_claim",
};
const RISK_KEY = { low: "risk_low", medium: "risk_medium", high: "risk_high" };

// Fixed-prompt phrasebook pairs are served by /api/ui-strings (single source:
// backend/captions.py). Exact-match only — never a free-text translation.
function normalizePrompt(text) {
  return (text || "").trim().toLowerCase().replace(/\s+/g, " ").replace(/[.?!]+$/, "").trim();
}
function lookupPhrasebook(pairs, text) {
  const target = normalizePrompt(text);
  if (!target) return null;
  for (const { en, vi } of pairs || []) {
    if (normalizePrompt(en) === target) return { text: vi, lang: "vi" };
    if (normalizePrompt(vi) === target) return { text: en, lang: "en" };
  }
  return null;
}
const $ = (id) => document.getElementById(id);

const state = {
  lang: "en",
  mode: "both",
  voice: false,
  child: false,
  bilingual: false,
  strings: {},
  phrasebook: [],
  currentEventId: null,
  last: null,
  escalation: null,
  history: new Map(),
  mockMode: false,
  ringScenarios: [],
  alexaEventId: null,
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
  if (new URLSearchParams(window.location.search).get("tv") === "1") {
    document.body.classList.add("tv-mode");
  }
  const tvNote = $("tv-note");
  if (tvNote) {
    tvNote.textContent = state.voice ? `${s("tv_mode_note")} · ${s("voice_on")}` : s("tv_mode_note");
  }
  const health = await (await fetch("/health")).json();
  state.mockMode = Boolean(health.mock_mode);
  const prefsResponse = await fetch("/api/prefs");
  const unauthorized = prefsResponse.status === 401;
  const prefs = unauthorized ? {} : await prefsResponse.json();
  const urlLang = new URLSearchParams(window.location.search).get("lang");
  state.lang = urlLang === "vi" ? "vi" : urlLang === "en" ? "en" : prefs.language === "vi" ? "vi" : "en";
  state.mode = prefs.mode || "both";
  state.child = localStorage.getItem("accessbell_child") === "1";
  state.voice = localStorage.getItem("accessbell_voice") === "1";
  state.bilingual = localStorage.getItem("accessbell_bilingual") === "1";
  await loadStrings();
  applyStatic();
  if (unauthorized) {
    showApiAuthNotice();
    setStatus("status_disconnected", "down");
  }
}

async function loadStrings() {
  const data = await (await fetch(`/api/ui-strings?lang=${state.lang}`)).json();
  state.strings = data.strings || {};
  state.phrasebook = data.phrasebook || [];
  document.documentElement.lang = state.lang;
}

function setText(id, key) {
  const element = $(id);
  if (element) element.textContent = s(key);
}

function showApiAuthNotice() {
  const banner = $("api-auth-note");
  if (!banner) return;
  banner.textContent = s("api_token_required");
  banner.classList.remove("hidden");
}

function applyStatic() {
  document.title = s("app_title");
  setText("brand", "app_title");
  setText("h-advise", "advise_title");
  setText("h-history", "recent_alerts");
  setText("export-log", "export_log");
  setText("h-calendar", "door_calendar");
  setText("h-share", "share_title");
  setText("h-demo", "simulate");
  setText("h-ring", "ring_title");
  setText("ring-note", "ring_note");
  setText("l-ring-scenario", "ring_scenario");
  setText("l-ring-statement", "ring_statement");
  setText("ring-fire", "ring_fire");
  setText("ring-motion", "ring_motion");
  setText("l-window-label", "window_label");
  setText("l-window-start", "window_start");
  setText("l-window-end", "window_end");
  setText("l-recipient", "recipient");
  setText("l-consent", "consent_label");
  setText("add-window", "add_window");
  setText("preview", "preview");
  setText("share", "share_now");
  setText("stop-escalation", "stop_escalation");
  setText("memory-use", "memory_use_same");
  setText("h-talk", "talk_title");
  setText("l-talk-speaker", "talk_speaker");
  setText("opt-visitor", "talk_speaker_visitor");
  setText("opt-resident", "talk_speaker_resident");
  setText("l-talk-lang", "language");
  setText("l-talk-text", "talk_title");
  $("talk-text").placeholder = s("talk_placeholder");
  setText("talk-mic", "talk_mic");
  setText("talk-translate", "talk_translate");
  setText("talk-speak", "talk_speak");
  setText("talk-send", "talk_send");
  $("lang-toggle").textContent = state.lang === "vi" ? "VI" : "EN";
  const bToggle = $("bilingual-toggle");
  if (bToggle) {
    bToggle.textContent = state.bilingual ? s("bilingual_mode_on") : s("bilingual_mode_off");
    bToggle.setAttribute("aria-pressed", String(state.bilingual));
  }
  $("voice-toggle").textContent = state.voice ? s("voice_on") : s("voice_off");
  $("voice-toggle").setAttribute("aria-pressed", String(state.voice));
  $("child-toggle").textContent = state.child ? s("child_mode_on") : s("child_mode_off");
  $("child-toggle").setAttribute("aria-pressed", String(state.child));
  renderReplies();
  buildDemoBar();
  buildAlexaDemo();
  if (state.ringScenarios.length) renderRingOptions();
}

function renderReplies() {
  const container = $("replies");
  container.innerHTML = "";
  let actions = state.child ? CHILD_ACTIONS : ACTIONS;
  if (!state.child && Array.isArray(state.last?.triage?.suggested_replies)) {
    const allowed = state.last.triage.suggested_replies.filter((action) => ACTIONS.includes(action));
    if (allowed.length) actions = allowed;
  }
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

function secondaryCaption(triage) {
  if (state.child) return "";
  const suffix = state.lang === "vi" ? "caption_en" : "caption_vi";
  return triage[suffix] || "";
}

function renderAlert(eventId, triage, why, childCaption, visitorStatement, status) {
  state.currentEventId = eventId ?? state.currentEventId;
  state.last = { eventId: state.currentEventId, triage, why, childCaption, visitorStatement, status };
  const caption = currentCaption(triage);
  const secondary = secondaryCaption(triage);
  $("caption").textContent = caption;
  const subEl = $("caption-sub");
  if (subEl) {
    subEl.textContent = state.bilingual ? secondary : "";
  }
  renderVisitorStatement(visitorStatement);
  $("why").textContent = why ? why[state.lang] || why.en || "" : "";
  $("category").textContent = triage.category || "";
  $("urgency").textContent = triage.urgency != null ? fill("urgency", { value: triage.urgency }) : "";
  $("confidence").textContent =
    triage.confidence != null ? fill("confidence", { value: Math.round(triage.confidence * 100) }) : "";
  $("grounding").textContent = s(GROUNDING_KEY[triage.grounding] || "generic");
  $("context").textContent = triage.context_status === "timeout" ? s("context_timeout") : "";
  const tier2Note = $("tier2-note");
  if (tier2Note) {
    const failed = status === "enrichment_failed";
    tier2Note.textContent = failed ? s("tier2_unavailable") : "";
    tier2Note.classList.toggle("hidden", !failed);
  }
  renderEvidence(triage.evidence);
  renderVerification(triage);
  renderReplies();
  loadTalkTurns(state.currentEventId);
  $("alert").className = `alert ${
    triage.risk_level === "high" && triage.verification_status !== "no_claim"
      ? "u-red"
      : URGENCY_CLASS(triage.urgency || 0)
  }`;
  speak(caption);
  announce(caption);
}

function renderVisitorStatement(statement) {
  const element = $("visitor-said");
  if (statement) {
    element.textContent = fill("visitor_said", { text: statement });
    element.classList.remove("hidden");
  } else {
    element.textContent = "";
    element.classList.add("hidden");
  }
}

function renderVerification(triage) {
  const status = triage.verification_status || "no_claim";
  const box = $("verification");
  if (status === "no_claim") {
    box.classList.add("hidden");
  } else {
    box.classList.remove("hidden");
    $("verification-badge").textContent = s(VERIFICATION_KEY[status] || "verification_no_claim");
    $("risk-badge").textContent = s(RISK_KEY[triage.risk_level || "low"] || "risk_low");
  }
  const challenge = $("challenge");
  const question = state.lang === "vi" ? triage.challenge_question_vi : triage.challenge_question_en;
  if (question) {
    challenge.textContent = question;
    challenge.classList.remove("hidden");
  } else {
    challenge.textContent = "";
    challenge.classList.add("hidden");
  }
  const memory = $("memory");
  if (triage.memory_action) {
    memory.classList.remove("hidden");
    $("memory-text").textContent =
      state.lang === "vi" ? triage.memory_basis_vi || "" : triage.memory_basis_en || "";
    $("memory-use").textContent = s("memory_use_same");
    $("memory-use").onclick = () => sendReply(triage.memory_action);
  } else {
    memory.classList.add("hidden");
  }
}

async function loadTalkTurns(eventId) {
  if (!eventId) return;
  const data = await (await fetch(`/api/events/${eventId}/door-talk`)).json();
  const list = $("talk-turns");
  list.innerHTML = "";
  (data.turns || []).forEach((turn) => {
    const item = document.createElement("li");
    item.textContent = `${turn.speaker} [${turn.lang}]: ${turn.text}`;
    list.appendChild(item);
  });
}

function speakText(text, lang) {
  if (!window.speechSynthesis || !text) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang === "vi" ? "vi-VN" : "en-US";
  window.speechSynthesis.speak(utterance);
}

function renderRaw(msg) {
  $("clock").textContent = new Date().toLocaleTimeString();
  const primary = (state.lang === "vi" ? msg.text_vi : msg.text_en) || msg.text || "";
  const secondary = (state.lang === "vi" ? msg.text_en : msg.text_vi) || "";
  $("caption").textContent = primary;
  const subEl = $("caption-sub");
  if (subEl) {
    subEl.textContent = state.bilingual ? secondary : "";
  }
  renderVisitorStatement(msg.visitor_statement);
  $("category").textContent = msg.category || "";
  $("urgency").textContent = "";
  $("confidence").textContent = "";
  $("grounding").textContent = "";
  $("context").textContent = "";
  $("latency").textContent = msg.latency_ms != null ? fill("latency", { ms: msg.latency_ms }) : "";
  renderEvidence([]);
  $("verification").classList.add("hidden");
  $("challenge").classList.add("hidden");
  $("memory").classList.add("hidden");
  $("alert").className = "alert u-amber";
  upsertHistory(msg.event_id, { caption: primary, tag: msg.category || "", urgency: 4 });
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

function historyClass(values) {
  const verification = values.verification || "";
  if (verification === "verified") return "u-green";
  if (verification === "unverified" || verification === "contradiction") {
    return values.risk === "high" ? "u-red" : "u-amber";
  }
  return URGENCY_CLASS(values.urgency || 0);
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
  item.className = historyClass(values);
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
      renderAlert(
        msg.event_id,
        msg.triage,
        msg.why,
        (msg.caption_child || {})[state.lang],
        msg.visitor_statement,
        msg.status,
      );
      upsertHistory(msg.event_id, {
        caption: (msg.triage && (msg.triage[`caption_${state.lang}`] || msg.triage.caption_en)) || "",
        tag: (msg.triage && msg.triage.category) || "",
        urgency: (msg.triage && msg.triage.urgency) || 0,
        verification: (msg.triage && msg.triage.verification_status) || "",
        risk: (msg.triage && msg.triage.risk_level) || "",
      });
    }
    if (msg.type === "escalation_armed") startEscalation(msg);
    if (msg.type === "escalation_sent") fireEscalation(msg);
    if (msg.type === "escalation_stopped") endEscalation();
  };
}

async function loadHistory() {
  const data = await (await fetch("/api/events?limit=8")).json();
  const events = data.events || [];
  events.forEach((event) => {
    upsertHistory(event.id, {
      caption: (event.triage && (event.triage[`caption_${state.lang}`] || event.triage.caption_en)) || "",
      tag: (event.triage && event.triage.category) || "",
      urgency: (event.triage && event.triage.urgency) || 0,
      verification: (event.triage && event.triage.verification_status) || "",
      risk: (event.triage && event.triage.risk_level) || "",
    });
  });
  // A TV surface shows the latest alert until a new one arrives, so restore it
  // on load instead of leaving the caption screen empty.
  const latest = events.find((event) => event.triage && event.triage.caption_en);
  if (latest && !state.last) {
    renderAlert(
      latest.id,
      latest.triage,
      latest.why,
      (latest.caption_child || {})[state.lang],
      latest.visitor_statement,
      latest.status,
    );
  }
}

async function loadAdvise() {
  const data = await (await fetch("/api/advise")).json();
  const list = $("advise");
  list.innerHTML = "";
  const panel = $("advise-panel");
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
  if (panel) panel.classList.toggle("hidden", list.children.length === 0);
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
    text.textContent = `${window.label} (${window.window_start} -> ${window.window_end})`;
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

function renderRingOptions() {
  const select = $("ring-scenario");
  if (!select) return;
  const current = select.value;
  select.innerHTML = "";
  state.ringScenarios.forEach((scenario) => {
    const option = document.createElement("option");
    option.value = scenario.key;
    option.textContent = s(`ring_scenario_${scenario.key}`) || scenario.key;
    select.appendChild(option);
  });
  if (current && state.ringScenarios.some((scenario) => scenario.key === current)) {
    select.value = current;
  }
  syncRingStatement();
}

function syncRingStatement() {
  const select = $("ring-scenario");
  const scenario = state.ringScenarios.find((item) => item.key === select.value);
  $("ring-statement").value = scenario ? scenario.statement || "" : "";
}

async function loadRingScenarios() {
  const section = $("ring-sim");
  if (!state.mockMode) {
    section.classList.add("hidden");
    return;
  }
  const response = await fetch("/api/simulate/ring/scenarios");
  if (!response.ok) {
    section.classList.add("hidden");
    return;
  }
  const data = await response.json();
  state.ringScenarios = data.scenarios || [];
  if (!state.ringScenarios.length) {
    section.classList.add("hidden");
    return;
  }
  section.classList.remove("hidden");
  renderRingOptions();
}

async function fireRing(scenario, visitorStatement) {
  const response = await fetch("/api/simulate/ring", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ scenario, visitor_statement: visitorStatement }),
  });
  const result = $("ring-result");
  if (!response.ok) {
    result.textContent = `${s("ring_failed")}: ${response.status}`;
    return;
  }
  const data = await response.json();
  const message = fill("ring_sent", { id: data.event_id });
  result.textContent = message;
  announce(message);
}

function buildDemoBar() {
  const section = $("demo");
  section.classList.toggle("hidden", !state.mockMode);
  if (!state.mockMode) return;
  const container = $("demo-buttons");
  container.innerHTML = "";

  const btnEn = document.createElement("button");
  btnEn.type = "button";
  btnEn.className = "reply primary";
  btnEn.textContent = s("demo_en") || "Demo EN";
  btnEn.addEventListener("click", async () => {
    if (state.lang !== "en") {
      state.lang = "en";
      try {
        await fetch("/api/prefs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: state.mode, language: "en" }),
        });
      } catch (_) {}
      await loadStrings();
      applyStatic();
    }
    await fetch("/api/simulate?fixture=doorbell_med", { method: "POST" });
  });
  container.appendChild(btnEn);

  const btnVi = document.createElement("button");
  btnVi.type = "button";
  btnVi.className = "reply primary";
  btnVi.textContent = s("demo_vi") || "Demo VI";
  btnVi.addEventListener("click", async () => {
    if (state.lang !== "vi") {
      state.lang = "vi";
      try {
        await fetch("/api/prefs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: state.mode, language: "vi" }),
        });
      } catch (_) {}
      await loadStrings();
      applyStatic();
    }
    await fetch("/api/simulate?fixture=doorbell_med", { method: "POST" });
  });
  container.appendChild(btnVi);

  FIXTURES.forEach((fixture) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "reply";
    const localized = s(`fixture_${fixture}`);
    button.textContent = localized ? `${localized} (${fixture})` : fixture;
    button.addEventListener("click", async () => {
      const response = await fetch(`/api/simulate?fixture=${encodeURIComponent(fixture)}`, { method: "POST" });
      if (!response.ok) $("note").textContent = `${s("reply_failed")}: ${response.status}`;
    });
    container.appendChild(button);
  });
}

function buildAlexaDemo() {
  const section = $("alexa-demo");
  if (!section) return;
  section.classList.toggle("hidden", !state.mockMode);
  if (!state.mockMode) return;
  setText("h-alexa", "alexa_title");
  setText("alexa-note", "alexa_note");
  setText("alexa-utterance", "alexa_utterance");
  setText("alexa-ask", "alexa_ask");
  setText("alexa-reply", "alexa_reply");
  $("alexa-transcript").setAttribute("aria-label", s("alexa_transcript"));
  if (section.dataset.wired === "1") return;
  section.dataset.wired = "1";
  $("alexa-ask").addEventListener("click", alexaAsk);
  $("alexa-reply").addEventListener("click", alexaReply);
}

async function alexaRpc(method, params, id) {
  const payload = JSON.stringify({ jsonrpc: "2.0", id, method, params });
  const options = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload,
  };
  let response = await fetch("/mcp", options);
  if (response.status === 401 || response.status === 403) {
    response = await fetch("/api/demo/mcp", options);
  }
  if (!response.ok) throw new Error(String(response.status));
  const body = await response.json();
  if (body.error) throw new Error(body.error.message || "error");
  return body.result || {};
}

function addAlexaStep(text) {
  const item = document.createElement("li");
  item.textContent = text;
  $("alexa-transcript").appendChild(item);
}

async function alexaAsk() {
  const button = $("alexa-ask");
  const reply = $("alexa-reply");
  const answer = $("alexa-answer");
  $("alexa-transcript").innerHTML = "";
  answer.textContent = s("alexa_working");
  state.alexaEventId = null;
  button.disabled = true;
  reply.disabled = true;
  try {
    const init = await alexaRpc(
      "initialize",
      {
        protocolVersion: "2025-11-25",
        capabilities: {},
        clientInfo: { name: "accessbell-pwa-demo", version: "1.0" },
      },
      1,
    );
    addAlexaStep(fill("alexa_init", { value: init.protocolVersion || "2025-11-25" }));

    const listed = await alexaRpc("tools/list", {}, 2);
    addAlexaStep(fill("alexa_tools", { value: (listed.tools || []).length }));

    const called = await alexaRpc("tools/call", { name: "get_door_alerts", arguments: { limit: 5 } }, 3);
    const content = (called.content || [])[0];
    const payload = content ? JSON.parse(content.text) : {};
    const alerts = payload.alerts || [];
    addAlexaStep(fill("alexa_alerts", { value: alerts.length }));
    if (!alerts.length) {
      answer.textContent = s("alexa_no_alert");
      return;
    }
    const alert = alerts[0];
    const caption = state.lang === "vi" ? alert.caption_vi : alert.caption_en;
    const challenge = state.lang === "vi" ? alert.challenge_question_vi : alert.challenge_question_en;
    answer.textContent = [caption, challenge].filter(Boolean).join(" ");
    state.alexaEventId = alert.event_id;
    reply.disabled = false;
    announce(answer.textContent);
  } catch (error) {
    answer.textContent = fill("alexa_failed", { value: error.message || "error" });
  } finally {
    button.disabled = false;
  }
}

async function alexaReply() {
  if (!state.alexaEventId) return;
  const button = $("alexa-reply");
  button.disabled = true;
  try {
    await alexaRpc(
      "tools/call",
      { name: "send_quick_reply", arguments: { event_id: state.alexaEventId, action: "coming" } },
      4,
    );
    addAlexaStep(fill("alexa_replied", { value: s("reply_coming") }));
    announce(fill("alexa_replied", { value: s("reply_coming") }));
  } catch (error) {
    $("alexa-answer").textContent = fill("alexa_failed", { value: error.message || "error" });
    button.disabled = false;
  }
}

function wireControls() {
  $("stop-escalation").addEventListener("click", stopEscalation);
  $("ring-scenario").addEventListener("change", syncRingStatement);
  $("ring-fire").addEventListener("click", () =>
    fireRing($("ring-scenario").value, $("ring-statement").value),
  );
  $("ring-motion").addEventListener("click", () => fireRing("motion", ""));
  $("export-log").addEventListener("click", async () => {
    const response = await fetch(`/api/door-log.txt?lang=${state.lang}`);
    if (!response.ok) {
      announce(s("export_log_failed"));
      return;
    }
    const blob = await response.blob();
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "accessbell-door-log.txt";
    link.click();
    URL.revokeObjectURL(link.href);
  });
  const bToggle = $("bilingual-toggle");
  if (bToggle) {
    bToggle.addEventListener("click", () => {
      state.bilingual = !state.bilingual;
      localStorage.setItem("accessbell_bilingual", state.bilingual ? "1" : "0");
      applyStatic();
      if (state.last) {
        renderAlert(
          state.last.eventId,
          state.last.triage,
          state.last.why,
          state.last.childCaption,
          state.last.visitorStatement,
          state.last.status,
        );
      }
    });
  }
  $("voice-toggle").addEventListener("click", () => {
    state.voice = !state.voice;
    localStorage.setItem("accessbell_voice", state.voice ? "1" : "0");
    applyStatic();
  });
  $("child-toggle").addEventListener("click", () => {
    state.child = !state.child;
    localStorage.setItem("accessbell_child", state.child ? "1" : "0");
    applyStatic();
    if (state.last) {
      renderAlert(
        state.last.eventId,
        state.last.triage,
        state.last.why,
        state.last.childCaption,
        state.last.visitorStatement,
        state.last.status,
      );
    }
  });
  $("lang-toggle").addEventListener("click", async () => {
    const next = state.lang === "vi" ? "en" : "vi";
    state.lang = next;
    try {
      await fetch("/api/prefs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: state.mode, language: next }),
      });
    } catch (_) {}
    await loadStrings();
    applyStatic();
    if (state.last) {
      renderAlert(
        state.last.eventId,
        state.last.triage,
        state.last.why,
        state.last.childCaption,
        state.last.visitorStatement,
        state.last.status,
      );
    }
    await Promise.all([loadHistory(), loadAdvise(), loadWindows(), loadShares()]);
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
  $("talk-translate").addEventListener("click", () => {
    // Preview only — does NOT store a turn.
    const found = lookupPhrasebook(state.phrasebook, $("talk-text").value);
    $("talk-translation").textContent = found ? found.text : s("talk_no_translation");
  });
  $("talk-speak").addEventListener("click", () => {
    speakText($("talk-text").value, $("talk-lang").value);
  });
  $("talk-mic").addEventListener("click", () => {
    const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Rec) {
      $("talk-translation").textContent = s("talk_mic_unsupported");
      return;
    }
    const rec = new Rec();
    rec.lang = $("talk-lang").value === "vi" ? "vi-VN" : "en-US";
    rec.onresult = (event) => {
      $("talk-text").value = event.results[0][0].transcript;
    };
    rec.start();
  });
  $("talk-send").addEventListener("click", async () => {
    if (!state.currentEventId) {
      $("talk-translation").textContent = s("no_events");
      return;
    }
    const response = await fetch(`/api/events/${state.currentEventId}/door-talk`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        speaker: $("talk-speaker").value,
        text: $("talk-text").value,
        lang: $("talk-lang").value,
      }),
    });
    $("talk-translation").textContent = response.ok ? s("talk_sent") : s("reply_failed");
    $("talk-text").value = "";
    loadTalkTurns(state.currentEventId);
  });
}

function enableDpadNavigation() {
  const NAV_KEYS = ["ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown"];
  const focusables = () =>
    Array.from(document.querySelectorAll("button, input, select")).filter((el) => el.offsetParent !== null);
  document.addEventListener("keydown", (event) => {
    if (!NAV_KEYS.includes(event.key)) return;
    const target = event.target;
    const tag = target && target.tagName ? target.tagName : "";
    if (target && (target.isContentEditable || tag === "SELECT" || tag === "TEXTAREA")) return;
    if (tag === "INPUT" && (event.key === "ArrowLeft" || event.key === "ArrowRight")) return;
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
  await loadRingScenarios();
  connectStream();
  await Promise.all([loadHistory(), loadAdvise(), loadWindows(), loadShares()]);
}

boot();