"use strict";

// Single-page lesson UI.
//
// Two views share this module:
//   - LIST VIEW  (no ?lesson= param): fetch /api/lessons and render a
//     clickable curriculum index. Each item links to ?lesson=<slug>.
//   - LESSON VIEW (?lesson=<slug>): load that lesson, render prose + the first
//     exercise, and wire the submit -> sandbox -> result -> progress flow.
//
// Language switching is instant and client-side in both views: the lesson
// payload carries both locales, and the list page renders titles from the
// active locale without a re-fetch.
//
// Auth functions live in auth.js (loaded first). Both files share window.Coach.

// Initialise the shared namespace; auth.js may have already created it.
window.Coach = window.Coach || {};

const params = new URLSearchParams(window.location.search);
const LESSON_SLUG = params.get("lesson"); // null => list view

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
    listHeading: "Lessons",
    backToLessons: "← Back to lessons",
    emptyList: "No lessons published yet.",
    logIn: "Log in",
    logOut: "Log out",
    register: "Register",
    email: "Email",
    password: "Password",
    loginHeading: "Log in",
    registerHeading: "Register",
    noAccount: "No account?",
    haveAccount: "Have an account?",
    checkYourEmail: "Check your email",
    confirmPendingText: (e) =>
      `We sent a confirmation link to ${e}. Open it to activate your account, then log in.`,
    loginRequired: "Log in to check your solution",
    loginToCheck: "Log in to check →",
    invalidCredentials: "Email or password is incorrect.",
    emailNotConfirmed: "Confirm your email before logging in.",
    emailTaken: "That email is already registered.",
    passwordTooShort: "Password must be at least 8 characters.",
    genericError: "Something went wrong. Try again.",
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
    listHeading: "Уроки",
    backToLessons: "← К списку уроков",
    emptyList: "Уроки ещё не опубликованы.",
    logIn: "Войти",
    logOut: "Выйти",
    register: "Регистрация",
    email: "Эл. почта",
    password: "Пароль",
    loginHeading: "Вход",
    registerHeading: "Регистрация",
    noAccount: "Нет аккаунта?",
    haveAccount: "Уже есть аккаунт?",
    checkYourEmail: "Проверьте почту",
    confirmPendingText: (e) =>
      `Мы отправили ссылку для подтверждения на ${e}. Откройте её, чтобы активировать аккаунт, затем войдите.`,
    loginRequired: "Войдите, чтобы проверить решение",
    loginToCheck: "Войдите для проверки →",
    invalidCredentials: "Неверная почта или пароль.",
    emailNotConfirmed: "Подтвердите почту перед входом.",
    emailTaken: "Эта почта уже зарегистрирована.",
    passwordTooShort: "Пароль должен быть не короче 8 символов.",
    genericError: "Что-то пошло не так. Попробуйте снова.",
  },
};

let editor = null;
let currentExerciseId = null;
let lessonData = null; // the both-locales payload (lesson view only)
let currentExercise = null; // the both-locales exercise object
let lastResults = null; // last render payload, so a locale switch re-labels it
let lastProgress = null;
let lessonList = null; // cached list payload (list view only)
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

// Pick a locale from a {en, ru} field, falling back to the other locale.
function pick(localized) {
  if (!localized) return "";
  return localized[locale] || localized.en || localized.ru || "";
}

// Publish the locale getter and lesson slug into the shared namespace so auth.js
// can read them without importing or relying on implicit access.
window.Coach.t = t;
window.Coach.lessonSlug = LESSON_SLUG;

// ── List view ──────────────────────────────────────────────────────────────

async function loadList() {
  const res = await fetch("/api/lessons");
  if (!res.ok) return;
  lessonList = await res.json();
  renderList();
}

function renderList() {
  // Show the list section; hide the lesson/exercise sections used by lesson view.
  document.getElementById("lesson-list-section").classList.remove("hidden");
  document.getElementById("lesson-section").classList.add("hidden");
  document.getElementById("exercise-section").classList.add("hidden");

  document.getElementById("list-heading").textContent = t().listHeading;

  const ul = document.getElementById("lesson-list");
  ul.innerHTML = "";

  // Keep lang-switch buttons in sync on list view too.
  document.querySelectorAll(".lang-switch button").forEach((b) => {
    b.classList.toggle("active", b.dataset.locale === locale);
  });
  document.documentElement.lang = locale;

  if (!lessonList || !lessonList.length) {
    const li = document.createElement("li");
    li.textContent = t().emptyList;
    ul.appendChild(li);
    return;
  }

  for (const lesson of lessonList) {
    const li = document.createElement("li");
    li.setAttribute("data-testid", "lesson-list-item");
    li.setAttribute("data-slug", lesson.slug);

    const a = document.createElement("a");
    a.href = `/?lesson=${encodeURIComponent(lesson.slug)}`;
    a.textContent = pick(lesson.title);
    li.appendChild(a);
    ul.appendChild(li);
  }
}

// ── Lesson view ────────────────────────────────────────────────────────────

async function loadLesson() {
  // Show lesson/exercise sections; hide the list section.
  document.getElementById("lesson-list-section").classList.add("hidden");
  document.getElementById("lesson-section").classList.remove("hidden");
  document.getElementById("exercise-section").classList.remove("hidden");

  // Wire the back link before the fetch so it is always present.
  const backLink = document.getElementById("back-to-lessons");
  if (backLink) backLink.textContent = t().backToLessons;

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

  const backLink = document.getElementById("back-to-lessons");
  if (backLink) backLink.textContent = t().backToLessons;

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
  renderCheckGate();
}

async function refreshProgress() {
  // Progress is per-account and protected; only fetch it when logged in.
  if (!window.Coach.isLoggedIn()) {
    lastProgress = null;
    renderProgressBadge();
    return;
  }
  const res = await fetch(`/api/progress/${currentExerciseId}`, {
    headers: window.Coach.authHeaders(),
  });
  if (!res.ok) return;
  lastProgress = await res.json();
  renderProgressBadge();
}

function renderProgressBadge() {
  const badge = document.getElementById("progress-badge");
  if (!window.Coach.isLoggedIn() || !lastProgress) {
    badge.textContent = "";
    return;
  }
  const p = lastProgress;
  badge.textContent = p.is_solved
    ? t().solved(p.attempts)
    : p.attempts
      ? t().notSolved(p.attempts)
      : t().notAttempted;
}

// Gate the Check button behind login: when logged out, disable it and show a
// "log in to check" prompt that opens the auth modal.
function renderCheckGate() {
  const btn = document.getElementById("check-btn");
  const prompt = document.getElementById("login-prompt");
  if (!btn || !prompt) return;
  // The button label is always the localized "Check"; login state is conveyed
  // by the disabled attribute + the adjacent login prompt, not by the label.
  if (btn.textContent !== t().checking) btn.textContent = t().check;
  if (window.Coach.isLoggedIn()) {
    btn.disabled = false;
    btn.removeAttribute("title");
    prompt.classList.add("hidden");
    return;
  }
  btn.disabled = true;
  btn.title = t().loginRequired;
  prompt.textContent = t().loginToCheck;
  prompt.classList.remove("hidden");
}

async function check() {
  // Submitting requires auth: prompt to log in rather than firing a 401.
  if (!window.Coach.isLoggedIn()) {
    window.Coach.openAuth();
    return;
  }
  const btn = document.getElementById("check-btn");
  btn.disabled = true;
  btn.textContent = t().checking;
  try {
    const res = await fetch("/api/submissions", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.Coach.authHeaders() },
      body: JSON.stringify({ exercise_id: currentExerciseId, code: editor.getValue() }),
    });
    // Token expired/invalid: drop it and ask the user to log in again.
    if (res.status === 401) {
      window.Coach.logout();
      window.Coach.openAuth();
      return;
    }
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

// ── Locale switch ──────────────────────────────────────────────────────────

function switchLocale(next) {
  if (!SUPPORTED.includes(next) || next === locale) return;
  locale = next;
  localStorage.setItem(LOCALE_KEY, next);
  window.Coach.renderAuthChrome();
  // Re-render whichever view is active.
  if (LESSON_SLUG) {
    renderProse();
  } else {
    renderList();
  }
}

// Publish lesson-view callbacks for auth.js to call on auth state changes.
window.Coach.renderCheckGate = renderCheckGate;
window.Coach.refreshProgress = refreshProgress;

// ── Boot ───────────────────────────────────────────────────────────────────

document.getElementById("check-btn").addEventListener("click", check);
document.querySelectorAll(".lang-switch button").forEach((b) => {
  b.addEventListener("click", () => switchLocale(b.dataset.locale));
});
// Auth event listeners are wired by auth.js (loaded first) — no call needed here.

// Restore session on load: if a token is stored, fetch the user; then render.
async function boot() {
  if (window.Coach.isLoggedIn()) await window.Coach.loadCurrentUser();
  window.Coach.renderAuthChrome();
  if (LESSON_SLUG) {
    await loadLesson();
  } else {
    await loadList();
  }
}

boot();
