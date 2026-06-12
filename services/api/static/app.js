"use strict";

// Minimal single-page lesson UI. Loads ONE fixture lesson by slug, renders the
// first exercise, and wires the submit -> sandbox -> result -> progress flow.
// The slug is read from ?lesson=, defaulting to the placeholder fixture.

const params = new URLSearchParams(window.location.search);
const LESSON_SLUG = params.get("lesson") || "placeholder-intro";

let editor = null;
let currentExerciseId = null;

async function loadLesson() {
  const res = await fetch(`/api/lessons/${encodeURIComponent(LESSON_SLUG)}`);
  if (!res.ok) {
    document.getElementById("lesson-title").textContent = "Lesson not found";
    return;
  }
  const lesson = await res.json();
  document.getElementById("lesson-title").textContent = lesson.title;
  document.getElementById("lesson-body").innerHTML = marked.parse(lesson.body_md || "");

  if (!lesson.exercises.length) {
    document.getElementById("exercise-title").textContent = "(no exercises yet)";
    return;
  }
  renderExercise(lesson.exercises[0]);
}

function renderExercise(ex) {
  currentExerciseId = ex.id;
  document.getElementById("exercise-title").textContent = ex.title;
  document.getElementById("exercise-statement").innerHTML = marked.parse(ex.statement_md || "");

  editor = CodeMirror.fromTextArea(document.getElementById("editor"), {
    mode: "python",
    lineNumbers: true,
    indentUnit: 4,
  });
  editor.setValue(ex.starter_code || "");
  refreshProgress();
}

async function refreshProgress() {
  const res = await fetch(`/api/progress/${currentExerciseId}`);
  if (!res.ok) return;
  const p = await res.json();
  const badge = document.getElementById("progress-badge");
  badge.textContent = p.is_solved
    ? `solved (${p.attempts} attempt${p.attempts === 1 ? "" : "s"})`
    : p.attempts
      ? `${p.attempts} attempt${p.attempts === 1 ? "" : "s"}, not solved`
      : "not attempted";
}

async function check() {
  const btn = document.getElementById("check-btn");
  btn.disabled = true;
  btn.textContent = "Checking…";
  try {
    const res = await fetch("/api/submissions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ exercise_id: currentExerciseId, code: editor.getValue() }),
    });
    const data = await res.json();
    renderResults(data);
    await refreshProgress();
  } catch (e) {
    renderResults({ runner_error: String(e), tests: [] });
  } finally {
    btn.disabled = false;
    btn.textContent = "Check";
  }
}

function renderResults(data) {
  const panel = document.getElementById("results");
  panel.classList.remove("hidden");
  const summary = document.getElementById("results-summary");
  summary.textContent = data.passed
    ? "✓ all passed"
    : `${data.passed_count || 0}/${data.total || 0} passed`;

  const list = document.getElementById("results-list");
  list.innerHTML = "";
  for (const t of data.tests || []) {
    const li = document.createElement("li");
    li.className = t.outcome;
    // Build via DOM, not innerHTML: t.name is a pytest nodeid from user-named
    // files and must not be interpreted as HTML (XSS).
    const outcome = document.createElement("span");
    outcome.className = "outcome";
    outcome.textContent = t.outcome.toUpperCase();
    li.appendChild(outcome);
    li.appendChild(document.createTextNode(t.name));
    if (t.message) {
      const msg = document.createElement("span");
      msg.className = "message";
      msg.textContent = t.message;
      li.appendChild(msg);
    }
    list.appendChild(li);
  }

  const err = document.getElementById("results-error");
  if (data.runner_error) {
    err.classList.remove("hidden");
    err.textContent = `Runner error: ${data.runner_error}\n${data.stderr || ""}`;
  } else {
    err.classList.add("hidden");
  }
}

document.getElementById("check-btn").addEventListener("click", check);
loadLesson();
