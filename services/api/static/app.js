"use strict";

// Single-page lesson UI with an auth gate + client-side router.
//
// Access model: NO content is reachable while logged out. Routes:
//   /, /lessons     authenticated lessons-list view (sequential-unlock gated).
//   /?lesson=<slug> authenticated lesson view (locked => 403 => redirect).
//   /profile        personal cabinet (rendered by profile.js).
//
// A logged-out deep link stashes the destination so login returns the user to
// it. Language switching is instant/client-side (payloads carry both locales).
// Strings live in i18n.js; auth in auth.js; profile in profile.js — all share
// window.Coach.

// Initialise the shared namespace; auth.js may have already created it.
window.Coach = window.Coach || {};

const params = new URLSearchParams(window.location.search);
const LESSON_SLUG = params.get("lesson"); // set => lesson view requested
const IS_LESSONS_PATH = window.location.pathname === "/lessons";
const IS_PROFILE_PATH = window.location.pathname === "/profile";

const SUPPORTED = ["en", "ru"];
const LOCALE_KEY = "python-coach.locale";
// Where to send the user after a successful login if they deep-linked a lesson.
const REDIRECT_KEY = "python-coach.redirect";

// UI chrome strings live in i18n.js (loaded first) as window.Coach.UI.
const UI = window.Coach.UI;

let editor = null;
let currentExerciseId = null;
let lessonData = null; // the both-locales payload (lesson view only)
let currentExercise = null; // the both-locales exercise object
let lastResults = null; // last render payload, so a locale switch re-labels it
let lastProgress = null;
let lessonList = null; // cached list payload (list view only)
let activeView = "auth"; // "auth" | "list" | "lesson" — drives locale re-render
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

// Publish the locale getter into the shared namespace so auth.js can read it.
window.Coach.t = t;

// Keep the header lang-switch buttons + <html lang> in sync with the locale.
function syncLangChrome() {
  document.querySelectorAll(".lang-switch button").forEach((b) => {
    b.classList.toggle("active", b.dataset.locale === locale);
  });
  document.documentElement.lang = locale;
}

// ── List view ──────────────────────────────────────────────────────────────

async function loadList() {
  const res = await fetch("/api/lessons", { headers: window.Coach.authHeaders() });
  // An expired/invalid token mid-session: drop to the auth gate, no leak.
  if (res.status === 401) {
    window.Coach.logout();
    return;
  }
  if (!res.ok) return;
  lessonList = await res.json();
  renderList();
}

function renderList() {
  activeView = "list";
  document.getElementById("auth-gate").classList.add("hidden");
  document.getElementById("lesson-list-section").classList.remove("hidden");
  document.getElementById("lesson-section").classList.add("hidden");
  document.getElementById("exercise-section").classList.add("hidden");
  document.getElementById("profile-section").classList.add("hidden");

  document.getElementById("list-heading").textContent = t().listHeading;
  syncLangChrome();

  // If we arrived here via a locked-lesson redirect, surface the reason once.
  const hint = document.getElementById("locked-hint");
  if (sessionStorage.getItem("python-coach.lockedMsg")) {
    sessionStorage.removeItem("python-coach.lockedMsg");
    hint.textContent = t().lockedRedirect;
    hint.classList.remove("hidden");
  } else {
    hint.classList.add("hidden");
  }

  const ul = document.getElementById("lesson-list");
  ul.innerHTML = "";

  if (!lessonList || !lessonList.length) {
    const li = document.createElement("li");
    li.textContent = t().emptyList;
    ul.appendChild(li);
    return;
  }

  // The "current" lesson is the first unlocked-but-not-completed one.
  const currentSlug = (lessonList.find((l) => l.is_unlocked && !l.is_completed) || {}).slug;

  for (const lesson of lessonList) {
    ul.appendChild(buildListItem(lesson, lesson.slug === currentSlug));
  }
}

// Build one list row reflecting completed / current / unlocked / locked state.
// Locked rows are NOT links and do not navigate; clicking shows a hint.
function buildListItem(lesson, isCurrent) {
  const li = document.createElement("li");
  li.setAttribute("data-testid", "lesson-list-item");
  li.setAttribute("data-slug", lesson.slug);

  let state = "unlocked";
  if (!lesson.is_unlocked) state = "locked";
  else if (lesson.is_completed) state = "completed";
  else if (isCurrent) state = "current";
  li.setAttribute("data-state", state);
  li.classList.add(`lesson-${state}`);

  const title = pick(lesson.title);

  if (state === "locked") {
    const span = document.createElement("span");
    span.className = "lesson-locked-title";
    span.setAttribute("data-testid", "lesson-locked");
    span.textContent = title;
    const lock = document.createElement("span");
    lock.className = "lock-indicator";
    lock.setAttribute("data-testid", "lock-indicator");
    lock.textContent = ` 🔒 ${t().locked}`;
    span.appendChild(lock);
    // Clicking a locked row shows a hint instead of navigating.
    span.addEventListener("click", () => {
      const hint = document.getElementById("locked-hint");
      hint.textContent = t().lockedHint;
      hint.classList.remove("hidden");
    });
    li.appendChild(span);
    return li;
  }

  const a = document.createElement("a");
  a.href = `/?lesson=${encodeURIComponent(lesson.slug)}`;
  a.textContent = title;
  li.appendChild(a);

  if (lesson.is_completed) {
    const badge = document.createElement("span");
    badge.className = "completed-badge";
    badge.setAttribute("data-testid", "completed-badge");
    badge.textContent = ` ${t().completedBadge}`;
    li.appendChild(badge);
  } else if (isCurrent) {
    const badge = document.createElement("span");
    badge.className = "current-badge";
    badge.setAttribute("data-testid", "current-badge");
    badge.textContent = ` ${t().current}`;
    li.appendChild(badge);
  }
  return li;
}

// ── Lesson view ────────────────────────────────────────────────────────────

async function loadLesson() {
  activeView = "lesson";
  document.getElementById("auth-gate").classList.add("hidden");
  document.getElementById("lesson-list-section").classList.add("hidden");
  document.getElementById("lesson-section").classList.remove("hidden");
  document.getElementById("exercise-section").classList.remove("hidden");
  document.getElementById("profile-section").classList.add("hidden");

  // Wire the back link before the fetch so it is always present.
  const backLink = document.getElementById("back-to-lessons");
  if (backLink) backLink.textContent = t().backToLessons;

  const res = await fetch(`/api/lessons/${encodeURIComponent(LESSON_SLUG)}`, {
    headers: window.Coach.authHeaders(),
  });
  if (res.status === 401) {
    window.Coach.logout();
    return;
  }
  // A locked lesson is the real 403 server gate: never render content. Bounce
  // back to the list with a message rather than showing a broken page.
  if (res.status === 403) {
    sessionStorage.setItem("python-coach.lockedMsg", "1");
    window.location.href = "/lessons";
    return;
  }
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
  syncLangChrome();
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
  if (btn.textContent !== t().checking) btn.textContent = t().check;
  if (lastResults) renderResults(lastResults);
  renderProgressBadge();
  renderCompletion();
}

// Render the lesson-completed state + the "Next lesson" / "all complete" CTA.
// Driven by lessonData.is_completed (server-derived) and lessonData.next_slug.
function renderCompletion() {
  const panel = document.getElementById("lesson-completion");
  if (!panel) return;
  if (!lessonData || !lessonData.is_completed) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  document.getElementById("completion-text").textContent = t().lessonCompleted;

  const nextBtn = document.getElementById("next-lesson-btn");
  const allDone = document.getElementById("all-complete-msg");
  if (lessonData.next_slug) {
    nextBtn.classList.remove("hidden");
    nextBtn.textContent = t().nextLesson;
    nextBtn.onclick = () => {
      window.location.href = `/?lesson=${encodeURIComponent(lessonData.next_slug)}`;
    };
    allDone.classList.add("hidden");
  } else {
    // Last lesson: no next; show the all-complete message + a profile link.
    nextBtn.classList.add("hidden");
    allDone.classList.remove("hidden");
    allDone.textContent = t().allLessonsComplete;
  }
}

async function refreshProgress() {
  const res = await fetch(`/api/progress/${currentExerciseId}`, {
    headers: window.Coach.authHeaders(),
  });
  if (res.status === 401) {
    window.Coach.logout();
    return;
  }
  if (!res.ok) return;
  lastProgress = await res.json();
  renderProgressBadge();
}

function renderProgressBadge() {
  const badge = document.getElementById("progress-badge");
  if (!lastProgress) {
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

async function check() {
  const btn = document.getElementById("check-btn");
  btn.disabled = true;
  btn.textContent = t().checking;
  try {
    const res = await fetch("/api/submissions", {
      method: "POST",
      headers: { "Content-Type": "application/json", ...window.Coach.authHeaders() },
      body: JSON.stringify({ exercise_id: currentExerciseId, code: editor.getValue() }),
    });
    // Token expired/invalid: drop it and bounce to the auth gate.
    if (res.status === 401) {
      window.Coach.logout();
      return;
    }
    const data = await res.json();
    renderResults(data);
    await refreshProgress();
    // A pass may complete the lesson: re-fetch to refresh is_completed/next_slug.
    if (data.passed) await refreshLessonCompletion();
  } catch (e) {
    renderResults({ runner_error: String(e), tests: [] });
  } finally {
    btn.disabled = false;
    btn.textContent = t().check;
  }
}

// Re-fetch the lesson to pick up freshly-derived is_completed/next_slug after a
// passing submission, then re-render the completion CTA. Preserves the editor.
async function refreshLessonCompletion() {
  const res = await fetch(`/api/lessons/${encodeURIComponent(LESSON_SLUG)}`, {
    headers: window.Coach.authHeaders(),
  });
  if (!res.ok) return;
  const fresh = await res.json();
  lessonData.is_completed = fresh.is_completed;
  lessonData.next_slug = fresh.next_slug;
  renderCompletion();
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
  syncLangChrome();
  // Re-render whichever view is active.
  if (activeView === "lesson") {
    renderProse();
  } else if (activeView === "list") {
    renderList();
  } else if (activeView === "profile" && window.Coach.renderProfile) {
    window.Coach.renderProfile();
  }
}

// Locale/view helpers so profile.js integrates with the shared locale switch.
window.Coach.getLocale = () => locale;
window.Coach.setActiveView = (view) => (activeView = view);
window.Coach.pick = pick;

// ── Router / auth gate ───────────────────────────────────────────────────────

// Render the content view the URL asks for. Caller guarantees the user is
// authenticated; this never runs while logged out.
async function renderRequestedView() {
  if (IS_PROFILE_PATH && window.Coach.renderProfile) {
    await window.Coach.renderProfile();
    return;
  }
  if (LESSON_SLUG) {
    await loadLesson();
    return;
  }
  // Both / and /lessons (when authenticated) show the lessons list. Keep the
  // list on its own /lessons URL so the landing and the list are distinct.
  if (!IS_LESSONS_PATH) {
    window.history.replaceState(null, "", "/lessons");
  }
  await loadList();
}

// Post-login router (called by auth.js after a successful login): return the
// user to the lesson they deep-linked, else show the lessons list.
async function onAuthenticated() {
  const stashed = sessionStorage.getItem(REDIRECT_KEY);
  if (stashed) {
    sessionStorage.removeItem(REDIRECT_KEY);
    window.location.href = stashed; // full nav so ?lesson= drives the lesson view
    return;
  }
  if (LESSON_SLUG) {
    await loadLesson();
    return;
  }
  await renderRequestedView();
}

// Post-logout router: collapse to the auth gate without leaking the URL's view.
function onLoggedOut() {
  window.Coach.showAuthGate();
  syncLangChrome();
}

window.Coach.onAuthenticated = onAuthenticated;
window.Coach.onLoggedOut = onLoggedOut;

// ── Boot ───────────────────────────────────────────────────────────────────

document.getElementById("check-btn").addEventListener("click", check);
document.querySelectorAll(".lang-switch button").forEach((b) => {
  b.addEventListener("click", () => switchLocale(b.dataset.locale));
});

async function boot() {
  syncLangChrome();
  if (!window.Coach.isLoggedIn()) {
    // Logged out: stash a deep-linked destination and show the gate. No content.
    if (LESSON_SLUG || IS_LESSONS_PATH || IS_PROFILE_PATH) {
      sessionStorage.setItem(REDIRECT_KEY, window.location.pathname + window.location.search);
    }
    activeView = "auth";
    window.Coach.showAuthGate();
    return;
  }
  // Token present: confirm it resolves to a user, then render the requested view.
  await window.Coach.loadCurrentUser();
  if (!window.Coach.isLoggedIn()) {
    // loadCurrentUser hit a 401 and logged us out -> gate already shown.
    return;
  }
  window.Coach.renderAuthChrome();
  await renderRequestedView();
}

boot();
