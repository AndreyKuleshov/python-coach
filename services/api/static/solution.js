"use strict";

// Reference-solution reveal module.
//
// Builds the per-exercise "Show reference solution" panel (button + read-only
// textarea) and owns the fetch + toggle logic. Exposes two functions consumed by
// exercise.js:
//
//   window.Coach.Solution.buildPanel(exerciseId, authHeaders)
//     → returns a DOM element to append to the exercise block.
//
//   window.Coach.Solution.refreshButton(exerciseId, isSolved)
//     → shows or hides the button depending on solved state.
//
// This split keeps exercise.js under the 500-line hard cap.

window.Coach = window.Coach || {};
window.Coach.Solution = (function () {
  // ── public: build the panel DOM ───────────────────────────────────────────

  // Build the panel for one exercise and wire the toggle/fetch handler.
  // `authHeaders` is the same closure that exercise.js uses for submissions.
  function buildPanel(exerciseId, authHeaders) {
    const wrapper = document.createElement("div");
    wrapper.className = "solution-panel";
    wrapper.setAttribute("data-solution-exercise-id", String(exerciseId));

    const btn = document.createElement("button");
    btn.className = "solution-btn hidden";
    btn.setAttribute("data-testid", "show-solution-btn");
    btn.textContent = window.Coach.t().showSolution;
    wrapper.appendChild(btn);

    const ta = document.createElement("textarea");
    ta.className = "reference-solution hidden";
    ta.setAttribute("data-testid", "reference-solution");
    ta.setAttribute("readonly", "true");
    ta.setAttribute("rows", "10");
    ta.setAttribute("spellcheck", "false");
    wrapper.appendChild(ta);

    // Toggle: first click fetches + reveals; subsequent clicks hide/show cached.
    let fetched = false;
    btn.addEventListener("click", async () => {
      if (!ta.classList.contains("hidden")) {
        ta.classList.add("hidden");
        btn.textContent = window.Coach.t().showSolution;
        return;
      }
      if (fetched) {
        ta.classList.remove("hidden");
        btn.textContent = window.Coach.t().hideSolution;
        return;
      }
      // First reveal: fetch from the server.
      btn.disabled = true;
      btn.textContent = window.Coach.t().solutionLoading;
      try {
        const res = await fetch(`/api/exercises/${exerciseId}/solution`, {
          headers: authHeaders(),
        });
        if (!res.ok) {
          btn.textContent = window.Coach.t().solutionError;
          btn.disabled = false;
          return;
        }
        const data = await res.json();
        ta.value = data.solution_code || "";
        fetched = true;
        ta.classList.remove("hidden");
        btn.textContent = window.Coach.t().hideSolution;
      } catch (_e) {
        btn.textContent = window.Coach.t().solutionError;
      } finally {
        btn.disabled = false;
      }
    });

    return wrapper;
  }

  // ── public: sync button visibility with solved state ──────────────────────

  // Show or hide the "Show reference solution" button inside an exercise block.
  // Called by exercise.js whenever the solved badge is refreshed.
  function refreshButton(exerciseId, isSolved) {
    const block = document.querySelector(
      `[data-testid="exercise-item"][data-exercise-id="${exerciseId}"]`,
    );
    if (!block) return;
    const btn = block.querySelector("[data-testid='show-solution-btn']");
    if (!btn) return;
    if (isSolved) {
      btn.classList.remove("hidden");
    } else {
      btn.classList.add("hidden");
    }
  }

  // ── public: re-translate visible button label on locale switch ────────────

  // Called by exercise.js rerenderLocale so the button label matches the locale.
  function rerenderButton(block) {
    const btn = block.querySelector("[data-testid='show-solution-btn']");
    if (!btn || btn.classList.contains("hidden")) return;
    const ta = block.querySelector("[data-testid='reference-solution']");
    const isExpanded = ta && !ta.classList.contains("hidden");
    btn.textContent = isExpanded
      ? window.Coach.t().hideSolution
      : window.Coach.t().showSolution;
  }

  return { buildPanel, refreshButton, rerenderButton };
})();
