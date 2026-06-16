"use strict";

// Personal profile / cabinet view (route: /profile).
//
// Renders the user's overall progress (X / N lessons completed + a progress
// bar) and a per-lesson status list (completed / current / locked with
// solved/total exercise counts). Bilingual via the shared window.Coach.UI
// catalog; re-renders on locale switch through window.Coach.renderProfile.
//
// Loaded after app.js so it can read the shared locale helpers it publishes
// (getLocale, pick, setActiveView) and the UI catalog.

window.Coach = window.Coach || {};

let profileData = null;

function profileT() {
  const locale = window.Coach.getLocale ? window.Coach.getLocale() : "en";
  return window.Coach.UI[locale];
}

// Fetch + render the profile aggregate. Called by the router and locale switch.
async function renderProfile() {
  window.Coach.setActiveView("profile");
  document.getElementById("auth-gate").classList.add("hidden");
  document.getElementById("lesson-list-section").classList.add("hidden");
  document.getElementById("lesson-section").classList.add("hidden");
  document.getElementById("exercise-section").classList.add("hidden");
  document.getElementById("profile-section").classList.remove("hidden");

  if (!profileData) {
    const res = await fetch("/api/profile", { headers: window.Coach.authHeaders() });
    if (res.status === 401) {
      window.Coach.logout();
      return;
    }
    if (!res.ok) return;
    profileData = await res.json();
  }
  paintProfile();
}

// Paint whatever is in profileData in the active locale (no re-fetch).
function paintProfile() {
  if (!profileData) return;
  const t = profileT();

  document.getElementById("profile-heading").textContent = t.profileHeading;
  document.getElementById("profile-email").textContent = profileData.email;

  const completed = profileData.lessons_completed;
  const total = profileData.lessons_total;
  document.getElementById("profile-summary").textContent = t.lessonsCompletedOf(completed, total);

  // Progress bar: width proportional to completed/total (0 when no lessons).
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  const bar = document.getElementById("profile-progress-bar");
  bar.style.width = `${pct}%`;
  bar.setAttribute("aria-valuenow", String(pct));

  const ul = document.getElementById("profile-lessons");
  ul.innerHTML = "";
  // The "current" lesson is the first unlocked-but-not-completed one.
  const current = (profileData.lessons.find((l) => l.is_unlocked && !l.is_completed) || {}).slug;
  for (const lesson of profileData.lessons) {
    ul.appendChild(buildProfileRow(lesson, lesson.slug === current, t));
  }

  document.getElementById("profile-back").textContent = t.backToLessons;
}

// One per-lesson status row: title + state label + solved/total exercise count.
function buildProfileRow(lesson, isCurrent, t) {
  const li = document.createElement("li");
  li.setAttribute("data-testid", "profile-lesson");
  li.setAttribute("data-slug", lesson.slug);

  let state = "unlocked";
  if (!lesson.is_unlocked) state = "locked";
  else if (lesson.is_completed) state = "completed";
  else if (isCurrent) state = "current";
  li.setAttribute("data-state", state);
  li.classList.add(`lesson-${state}`);

  const title = document.createElement("span");
  title.className = "profile-lesson-title";
  title.textContent = window.Coach.pick(lesson.title);
  li.appendChild(title);

  const status = document.createElement("span");
  status.className = "profile-lesson-status";
  status.setAttribute("data-testid", "profile-lesson-status");
  if (state === "completed") status.textContent = t.completedBadge;
  else if (state === "locked") status.textContent = `🔒 ${t.locked}`;
  else if (state === "current") status.textContent = t.current;
  li.appendChild(status);

  const counts = document.createElement("span");
  counts.className = "profile-lesson-counts";
  counts.setAttribute("data-testid", "profile-lesson-counts");
  counts.textContent = t.exercisesOf(lesson.solved_exercises, lesson.total_exercises);
  li.appendChild(counts);

  return li;
}

window.Coach.renderProfile = renderProfile;
