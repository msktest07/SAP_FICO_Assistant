const state = { currentAnswerId: null, history: [], editId: null, feedbackId: null, toastTimer: null };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const titles = { assistant: "Ask the assistant", history: "Question history", topics: "Topic explorer", dashboard: "Quality dashboard" };

function showToast(message, type = "success") {
  const toast = $("#toast");
  toast.textContent = message;
  toast.className = `toast show ${type === "error" ? "error" : ""}`;
  clearTimeout(state.toastTimer);
  state.toastTimer = setTimeout(() => { toast.className = "toast"; }, 3800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });

  const text = await response.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch {
      throw new Error(`The server returned an unreadable response: ${text.slice(0, 200)}`);
    }
  }

  if (!response.ok) {
    const details = Array.isArray(data?.details) ? ` ${data.details.join(" ")}` : "";
    throw new Error(`${data?.error || "Request failed."}${details}`);
  }
  return data;
}

function navigate(route) {
  $$(".nav-link").forEach(link => link.classList.toggle("active", link.dataset.route === route));
  $$(".view").forEach(view => view.classList.toggle("active", view.dataset.view === route));
  $("#pageTitle").textContent = titles[route];
  location.hash = route;
  closeMenu();
  if (route === "history") loadHistory();
  if (route === "topics") loadTopics();
  if (route === "dashboard") loadDashboard();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function openMenu() { $("#sidebar").classList.add("open"); $("#overlay").classList.add("show"); $("#menuButton").setAttribute("aria-expanded", "true"); }
function closeMenu() { $("#sidebar").classList.remove("open"); $("#overlay").classList.remove("show"); $("#menuButton").setAttribute("aria-expanded", "false"); }

function validateQuestion(value = $("#question").value.trim(), field = $("#question"), errorId = "#questionError") {
  let message = "";
  if (!value) message = "Enter a SAP FICO question.";
  else if (value.length < 8) message = "Use at least 8 characters so the assistant can understand the question.";
  else if (value.length > 1000) message = "Question must not exceed 1,000 characters.";
  if (field) field.classList.toggle("invalid", Boolean(message));
  if (errorId && $(errorId)) $(errorId).textContent = message;
  return !message;
}

function syncProductRelease(productId = "#product", releaseId = "#release") {
  const product = $(productId).value;
  const release = $(releaseId);
  [...release.options].forEach(option => {
    option.disabled = product === "SAP ECC" ? option.value !== "ECC 6.0" : option.value === "ECC 6.0";
  });
  if (product === "SAP ECC") release.value = "ECC 6.0";
  else if (release.value === "ECC 6.0") release.value = "Current";
}

function clearQuestionComposer() {
  const question = $("#question");
  const wrap = document.querySelector(".question-wrap");
  question.value = "";
  question.classList.remove("invalid");
  $("#questionError").textContent = "";
  if (wrap) {
    wrap.classList.remove("empty-reset");
    void wrap.offsetWidth;
    wrap.classList.add("empty-reset");
    setTimeout(() => wrap.classList.remove("empty-reset"), 380);
  }
  updateCount();
  question.focus();
}

async function askQuestion(event) {
  event.preventDefault();
  if (!validateQuestion()) return;
  const button = $("#askButton");
  button.disabled = true;
  button.querySelector("span").textContent = "Analyzing...";
  const payload = { question: $("#question").value.trim(), module: $("#module").value, product: $("#product").value, release: $("#release").value, country: $("#country").value };
  try {
    const result = await api("/api/ask", { method: "POST", body: JSON.stringify(payload) });
    renderAnswer(result);
    clearQuestionComposer();
    showToast(result.matched ? "Answer generated and saved to history." : "More information is needed for a reliable answer.", result.matched ? "success" : "error");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    button.disabled = false;
    button.querySelector("span").textContent = "Ask assistant";
  }
}

function renderAnswer(result) {
  state.currentAnswerId = result.id;
  $("#answerTopic").textContent = result.topic;
  $("#confidence").textContent = `${result.confidence}% evidence match`;
  $("#answerCopy").textContent = result.answer;
  $("#answerSource").textContent = result.source;
  $("#answerNotice").textContent = result.notice;
  $("#answerSteps").replaceChildren(...result.steps.map(text => { const li = document.createElement("li"); li.textContent = text; return li; }));
  $("#stepsBlock").classList.toggle("hidden", !result.steps.length);
  $("#transactions").replaceChildren(...result.transactions.map(text => { const span = document.createElement("span"); span.textContent = text; return span; }));
  $(".transaction-block").classList.toggle("hidden", !result.transactions.length);
  $("#followupChips").replaceChildren(...(result.followups || []).map(text => { const button = document.createElement("button"); button.textContent = text; button.addEventListener("click", () => { $("#question").value = text; updateCount(); navigate("assistant"); }); return button; }));
  $$(".feedback-button").forEach(button => button.classList.remove("selected"));
  $("#answerCard").classList.remove("hidden");
  $("#answerCard").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function sendFeedback(rating, button) {
  if (!state.currentAnswerId) return;
  try {
    const result = await api("/api/feedback", { method: "POST", body: JSON.stringify({ conversationId: state.currentAnswerId, rating, comment: "" }) });
    $$(".feedback-button").forEach(item => item.classList.remove("selected"));
    button.classList.add("selected");
    showToast(result.message);
    loadHistory();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function formatDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

async function loadHistory() {
  try {
    const data = await api("/api/conversations");
    state.history = data.items;
    renderHistory();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function historyRowActions(item) {
  const wrap = document.createElement("div");
  wrap.className = "row-actions";
  const editButton = document.createElement("button");
  editButton.className = "secondary-button";
  editButton.textContent = "Edit";
  editButton.addEventListener("click", () => openEditModal(item));
  const feedbackButton = document.createElement("button");
  feedbackButton.className = "secondary-button";
  feedbackButton.textContent = "Feedback";
  feedbackButton.addEventListener("click", () => openFeedbackModal(item));
  const deleteButton = document.createElement("button");
  deleteButton.className = "secondary-button danger";
  deleteButton.textContent = "Delete";
  deleteButton.addEventListener("click", () => deleteConversation(item.id));
  wrap.append(editButton, feedbackButton, deleteButton);
  return wrap;
}

function renderHistory() {
  const query = $("#historySearch").value.toLowerCase().trim();
  const module = $("#historyModule").value;
  const items = state.history.filter(item => (!query || `${item.question} ${item.topic}`.toLowerCase().includes(query)) && (!module || item.module === module));
  const body = $("#historyBody");
  body.replaceChildren(...items.map(item => {
    const row = document.createElement("tr");
    const values = [item.question, item.topic, `${item.product} · ${item.release_name}`, `${item.confidence}%`, item.rating ? item.rating.replace("_", " ") : "—", "", formatDate(item.created_at)];
    values.forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 1) { const tag = document.createElement("span"); tag.className = "table-tag"; tag.textContent = value; cell.append(tag); }
      else if (index === 5) cell.append(historyRowActions(item));
      else cell.textContent = value;
      row.append(cell);
    });
    return row;
  }));
  $("#historyEmpty").classList.toggle("hidden", items.length > 0);
  $(".table-wrap").classList.toggle("hidden", items.length === 0);
}

async function openEditModal(item) {
  state.editId = item.id;
  $("#editQuestion").value = item.question;
  $("#editModule").value = item.module;
  $("#editProduct").value = item.product;
  $("#editRelease").value = item.release_name;
  $("#editCountry").value = item.country;
  $("#editModal").showModal();
}

async function saveEdit(event) {
  event.preventDefault();
  const question = $("#editQuestion").value.trim();
  if (!validateQuestion(question, $("#editQuestion"), null)) return;
  try {
    const result = await api(`/api/conversations/${state.editId}`, {
      method: "POST",
      body: JSON.stringify({ action: "update", question, module: $("#editModule").value, product: $("#editProduct").value, release: $("#editRelease").value, country: $("#editCountry").value }),
    });
    $("#editModal").close();
    showToast("Question updated.");
    renderAnswer(result);
    loadHistory();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function deleteConversation(id) {
  if (!confirm("Delete this saved question and any feedback?")) return;
  try {
    const result = await api(`/api/conversations/${id}`, { method: "DELETE", body: JSON.stringify({}) });
    showToast(result.message);
    loadHistory();
  } catch (error) {
    showToast(error.message, "error");
  }
}

function openFeedbackModal(item) {
  state.feedbackId = item.id;
  $("#feedbackRating").value = item.rating || "helpful";
  $("#feedbackComment").value = item.feedback_comment || "";
  $("#deleteFeedbackButton").disabled = !item.rating;
  $("#feedbackModal").showModal();
}

async function saveFeedback(event) {
  event.preventDefault();
  try {
    const result = await api(`/api/feedback/${state.feedbackId}`, {
      method: "PUT",
      body: JSON.stringify({ rating: $("#feedbackRating").value, comment: $("#feedbackComment").value.trim() }),
    });
    $("#feedbackModal").close();
    showToast(result.message);
    loadHistory();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function removeFeedback(id = state.feedbackId) {
  if (!confirm("Delete feedback for this question?")) return;
  try {
    const result = await api(`/api/feedback/${id}`, { method: "DELETE", body: JSON.stringify({}) });
    showToast(result.message);
    $("#feedbackModal").close();
    loadHistory();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadTopics() {
  try {
    const data = await api("/api/topics");
    const cards = data.items.map(item => {
      const card = document.createElement("article");
      card.className = "topic-card";
      const badge = document.createElement("span");
      badge.textContent = item.module;
      const heading = document.createElement("h3");
      heading.textContent = item.topic;
      const copy = document.createElement("p");
      copy.textContent = `Common references: ${item.transactions.join(", ")}`;
      const button = document.createElement("button");
      button.textContent = "Ask about this topic ->";
      button.addEventListener("click", () => {
        $("#question").value = `Explain the key process and controls for ${item.topic}`;
        updateCount();
        navigate("assistant");
        $("#question").focus();
      });
      card.append(badge, heading, copy, button);
      return card;
    });
    $("#topicGrid").replaceChildren(...cards);
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function loadDashboard() {
  try {
    const data = await api("/api/dashboard");
    $("#questionMetric").textContent = data.questions;
    $("#helpfulMetric").textContent = data.helpful;
    $("#knowledgeMetric").textContent = data.knowledgeTopics;
    const max = Math.max(...data.topics.map(item => item.count), 1);
    const rows = data.topics.map(item => {
      const row = document.createElement("div");
      row.className = "bar-row";
      const label = document.createElement("span");
      label.textContent = item.topic;
      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      fill.style.width = `${(item.count / max) * 100}%`;
      track.append(fill);
      const value = document.createElement("b");
      value.textContent = item.count;
      row.append(label, track, value);
      return row;
    });
    if (!rows.length) {
      const empty = document.createElement("p");
      empty.textContent = "Topic activity will appear after the first question.";
      empty.style.color = "var(--muted)";
      rows.push(empty);
    }
    $("#popularTopics").replaceChildren(...rows);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function updateCount() {
  $("#characterCount").textContent = $("#question").value.length;
  if ($("#question").classList.contains("invalid")) validateQuestion();
}

document.addEventListener("DOMContentLoaded", () => {
  $$("[data-route]").forEach(item => item.addEventListener("click", event => { event.preventDefault(); navigate(item.dataset.route); }));
  $("#questionForm").addEventListener("submit", askQuestion);
  $("#question").addEventListener("input", updateCount);
  $("#question").addEventListener("keydown", (event) => {
    if ((event.key === "Enter" && !event.shiftKey) || ((event.ctrlKey || event.metaKey) && event.key === "Enter")) {
      event.preventDefault();
      $("#questionForm").requestSubmit();
    }
  });
  $("#product").addEventListener("change", syncProductRelease);
  $$("[data-question]").forEach(button => button.addEventListener("click", () => { $("#question").value = button.dataset.question; updateCount(); $("#question").focus(); }));
  $("#askAnotherQuestion").addEventListener("click", () => {
    clearQuestionComposer();
    $("#answerCard").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  $$(".feedback-button").forEach(button => button.addEventListener("click", () => sendFeedback(button.dataset.rating, button)));
  $("#historySearch").addEventListener("input", renderHistory);
  $("#historyModule").addEventListener("change", renderHistory);
  $("#refreshHistory").addEventListener("click", loadHistory);
  $("#refreshDashboard").addEventListener("click", loadDashboard);
  $("#menuButton").addEventListener("click", () => $("#sidebar").classList.contains("open") ? closeMenu() : openMenu());
  $("#overlay").addEventListener("click", closeMenu);
  $("#themeButton").addEventListener("click", () => { document.body.classList.toggle("dark"); localStorage.setItem("sap-fico-theme", document.body.classList.contains("dark") ? "dark" : "light"); });
  $("#editForm").addEventListener("submit", saveEdit);
  $("#feedbackForm").addEventListener("submit", saveFeedback);
  $("#deleteFeedbackButton").addEventListener("click", () => removeFeedback());
  $("#editModal").addEventListener("close", () => { state.editId = null; });
  $("#feedbackModal").addEventListener("close", () => { state.feedbackId = null; });
  if (localStorage.getItem("sap-fico-theme") === "dark") document.body.classList.add("dark");
  syncProductRelease();
  updateCount();
  const initialRoute = location.hash.slice(1);
  navigate(titles[initialRoute] ? initialRoute : "assistant");
});
