"use strict";

// Minimal single-page lesson UI. Loads ONE fixture lesson by slug (both
// locales in one payload), renders the first exercise, and wires the
// submit -> sandbox -> result -> progress flow. The slug is read from
// ?lesson=, defaulting to the placeholder fixture.
//
// Language switching is instant and client-side: the lesson payload carries
// both locales, so toggling EN/RU swaps lesson/exercise prose AND the UI
// chrome strings below with no reload and no re-fetch.

const params = new URLSearchParams(window.location.search);
const LESSON_SLUG = params.get("lesson") || "placeholder-intro";

const SUPPORTED = ["en", "ru"];
const LOCALE_KEY = "python-coach.locale";

// UI chrome strings per locale. No i18n framework — a tiny catalog is enough
// for two locales. Functions handle pluralisation/interpolation.
const UI = {
  en: {
    editorLabel: "Your solution",
    check: "Check",
    checking: "Checking…",
    resultsHeading: "Results",
    allPassed: "✓ all passed",
    passedOf: (p, t) => `${p}/${t} passed`,
    lessonNotFound: "Lesson not found",
    noExercises: "(no exercises yet)",
    notAttempted: "not attempted",
    solved: (n) => `solved (${n} attempt${n === 1 ? "" : "s"})`,
    notSolved: (n) => `${n} attempt${n === 1 ? "" : "s"}, not solved`,
    runnerError: (msg) => `Runner error: ${msg}`,
  },
  ru: {
    editorLabel: "Ваше решение",
    check: "Проверить",
    checking: "Проверяем…",
    resultsHeading: "Результаты",
    allPassed: "✓ все пройдены",
    passedOf: (p, t) => `пройдено ${p}/${t}`,
    lessonNotFound: "Урок не найден",
    noExercises: "(пока нет заданий)",
    notAttempted: "нет попыток",
    solved: (n) => `решено (попыток: ${n})`,
    notSolved: (n) => `попыток: ${n}, не решено`,
    runnerError: (msg) => `Ошибка запуска: ${msg}`,
  },
};

let editor = null;
let currentExerciseId = null;
let lessonData = null; // the both-locales payload
let currentExercise = null; // the both-locales exercise object
let lastResults = null; // last render payload, so a locale switch re-labels it
let locale = resolveInitialLocale();

// navigator.language wins on first visit; a persisted manual choice wins after.
function resolveInitialLocale() {
  const stored = localStorage.getItem(LOCALE_KEY);
  if (stored && SUPPORTED.includes(stored)) return stored;
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  return SUPPORTED.includes(nav) ? nav : "en";
}

function t() {
  return UI[locale];
}

async function loadLesson() {
  const res = await fetch(`/api/lessons/${encodeURIComponent(LESSON_SLUG)}`);
  if (!res.ok) {
    document.getElementById("lesson-title").textContent = t().lessonNotFound;
    return;
  }
  lessonData = await res.json();

  if (!lessonData.exercises.length) {
    currentExercise = null;
  } else {
    currentExercise = lessonData.exercises[0];
    currentExerciseId = currentExercise.id;
    // Create the editor once; a language switch must not rebuild it (and lose
    // the learner's edits). Seed it with starter code only on first render.
    editor = CodeMirror.fromTextArea(document.getElementById("editor"), {
      mode: "python",
      lineNumbers: true,
      indentUnit: 4,
    });
    editor.setValue(currentExercise.starter_code || "");
  }

  renderProse();
  if (currentExerciseId !== null) await refreshProgress();
}

// Re-render every locale-dependent surface. Safe to call on load and on switch.
function renderProse() {
  document.querySelectorAll(".lang-switch button").forEach((b) => {
    b.classList.toggle("active", b.dataset.locale === locale);
  });
  document.documentElement.lang = locale;
  document.getElementById("editor-label").textContent = t().editorLabel;
  document.getElementById("results-heading").textContent = t().resultsHeading;

  if (!lessonData) return;
  document.getElementById("lesson-title").textContent = pick(lessonData.title);
  document.getElementById("lesson-body").innerHTML = marked.parse(pick(lessonData.body_md) || "");

  if (!currentExercise) {
    document.getElementById("exercise-title").textContent = t().noExercises;
    return;
  }
  document.getElementById("exercise-title").textContent = pick(currentExercise.title);
  document.getElementById("exercise-statement").innerHTML = marked.parse(
    pick(currentExercise.statement_md) || "",
  );

  const btn = document.getElementById("check-btn");
  if (!btn.disabled) btn.textContent = t().check;
  if (lastResults) renderResults(lastResults);
  renderProgressBadge();
}

// Pick a locale from a {en, ru} field, falling back to the other locale.
function pick(localized) {
  if (!localized) return "";
  return localized[locale] || localized.en || localized.ru || "";
}

let lastProgress = null;

async function refreshProgress() {
  const res = await fetch(`/api/progress/${currentExerciseId}`);
  if (!res.ok) return;
  lastProgress = await res.json();
  renderProgressBadge();
}

function renderProgressBadge() {
  if (!lastProgress) return;
  const p = lastProgress;
  const badge = document.getElementById("progress-badge");
  badge.textContent = p.is_solved
    ? t().solved(p.attempts)
    : p.attempts
      ? t().notSolved(p.attempts)
      : t().notAttempted;
}

async function check() {
  const btn = document.getElementById("check-btn");
  btn.disabled = true;
  btn.textContent = t().checking;
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
    btn.textContent = t().check;
  }
}

function renderResults(data) {
  lastResults = data;
  const panel = document.getElementById("results");
  panel.classList.remove("hidden");
  const summary = document.getElementById("results-summary");
  summary.textContent = data.passed
    ? t().allPassed
    : t().passedOf(data.passed_count || 0, data.total || 0);

  const list = document.getElementById("results-list");
  list.innerHTML = "";
  for (const item of data.tests || []) {
    const li = document.createElement("li");
    li.className = item.outcome;
    li.setAttribute("data-testid", "result-item");
    li.setAttribute("data-outcome", item.outcome);
    // Build via DOM, not innerHTML: item.name is a pytest nodeid from user-named
    // files and must not be interpreted as HTML (XSS).
    const outcome = document.createElement("span");
    outcome.className = "outcome";
    outcome.setAttribute("data-testid", "result-outcome");
    outcome.textContent = item.outcome.toUpperCase();
    li.appendChild(outcome);
    li.appendChild(document.createTextNode(item.name));
    if (item.message) {
      const msg = document.createElement("span");
      msg.className = "message";
      msg.textContent = item.message;
      li.appendChild(msg);
    }
    list.appendChild(li);
  }

  const err = document.getElementById("results-error");
  if (data.runner_error) {
    err.classList.remove("hidden");
    err.textContent = `${t().runnerError(data.runner_error)}\n${data.stderr || ""}`;
  } else {
    err.classList.add("hidden");
  }
}

function switchLocale(next) {
  if (!SUPPORTED.includes(next) || next === locale) return;
  locale = next;
  localStorage.setItem(LOCALE_KEY, next);
  renderProse();
}

document.getElementById("check-btn").addEventListener("click", check);
document.querySelectorAll(".lang-switch button").forEach((b) => {
  b.addEventListener("click", () => switchLocale(b.dataset.locale));
});
loadLesson();
