"use strict";

// Per-lesson multi-exercise rendering module.
//
// Renders ALL exercises of a lesson as independent blocks: title, statement,
// CodeMirror editor, Check button, results panel, and a per-exercise solved
// badge. Each block is self-contained: the Check button posts only that
// exercise's code and updates only that block's UI.
//
// Reference-solution reveal (post-solve) is delegated to solution.js to keep
// this file under the 500-line hard cap.
//
// Exposes window.Coach.Exercise.renderExercises(lessonData, slug, authHeaders)
// and window.Coach.Exercise.rerenderLocale(lessonData) so app.js can call in
// and locale-switch without rebuilding the DOM tree.

window.Coach = window.Coach || {};
window.Coach.Exercise = (function () {
  // One CodeMirror instance per exercise; keyed by exercise id so a locale
  // switch can target the right editor without iterating the DOM.
  const _editors = {};

  // Solved state per exercise id: updated optimistically on a passing check
  // and seeded from the progress fetch on load so badges appear immediately.
  const _solved = {};

  // Live lessonData reference (both-locales) kept so rerenderLocale can
  // re-pick the right locale without a re-fetch.
  let _lessonData = null;

  // The LESSON_SLUG is not available inside this module, so app.js injects it.
  let _slug = null;
  let _authHeaders = null;

  // ── public API ─────────────────────────────────────────────────────────────

  // Render all exercises into the container and load per-exercise progress.
  // `solvedIds` is an array of exercise ids already solved (from a prior fetch);
  // each may arrive asynchronously, so renderExercises must accept an empty
  // array and rely on loadProgress for the initial badge state.
  async function renderExercises(lessonData, slug, authHeaders) {
    _lessonData = lessonData;
    _slug = slug;
    _authHeaders = authHeaders;

    // Reset per-session editor map (navigating between lessons without reload).
    for (const key of Object.keys(_editors)) delete _editors[key];
    for (const key of Object.keys(_solved)) delete _solved[key];

    const container = document.getElementById("exercises-container");
    container.innerHTML = "";

    const locale = window.Coach.getLocale();

    if (!lessonData.exercises.length) {
      const msg = document.createElement("p");
      msg.textContent = window.Coach.t().noExercises;
      container.appendChild(msg);
      _renderProgressCounter();
      return;
    }

    for (const ex of lessonData.exercises) {
      container.appendChild(_buildBlock(ex, locale));
    }

    // CodeMirror measures editor dimensions on mount. When the textarea is
    // inside a detached DOM fragment, those dimensions are zero and the
    // starter code is painted only after the first focus/click (which triggers
    // an internal refresh). Forcing a refresh in the next animation frame —
    // after every block is attached to the visible DOM — makes the starter code
    // appear immediately on load with no user interaction required.
    requestAnimationFrame(() => {
      for (const cm of Object.values(_editors)) {
        cm.refresh();
      }
    });

    // Fetch progress for every exercise in parallel, then refresh badges.
    await _loadAllProgress();
    _renderProgressCounter();
    _renderCompletion();
  }

  // Re-render every locale-sensitive string in all existing blocks. Called by
  // app.js on a locale switch so we update exercise titles, statements, button
  // labels, and result text without rebuilding the editor instances.
  function rerenderLocale(lessonData) {
    _lessonData = lessonData;
    const locale = window.Coach.getLocale();
    if (!lessonData || !lessonData.exercises.length) return;

    for (const ex of lessonData.exercises) {
      const block = document.querySelector(
        `[data-testid="exercise-item"][data-exercise-id="${ex.id}"]`,
      );
      if (!block) continue;

      const titleEl = block.querySelector("[data-testid='exercise-item-title']");
      if (titleEl) titleEl.textContent = _pick(ex.title, locale);

      const stmtEl = block.querySelector("[data-testid='exercise-item-statement']");
      if (stmtEl) stmtEl.innerHTML = marked.parse(_pick(ex.statement_md, locale) || "");

      const labelEl = block.querySelector("[data-testid='editor-label']");
      if (labelEl) labelEl.textContent = window.Coach.t().editorLabel;

      const checkBtn = block.querySelector("[data-testid='check-btn']");
      if (checkBtn && checkBtn.textContent !== window.Coach.t().checking) {
        checkBtn.textContent = window.Coach.t().check;
      }

      const solvedBadge = block.querySelector("[data-testid='solved-badge']");
      if (solvedBadge) _refreshSolvedBadge(solvedBadge, ex.id);

      // Re-translate the reference-solution button label (delegated to solution.js).
      if (window.Coach.Solution) window.Coach.Solution.rerenderButton(block);

      // Re-render results panel summary text if results are showing.
      const resultSummary = block.querySelector("[data-testid='results-summary']");
      if (resultSummary && resultSummary.dataset.passedCount !== undefined) {
        const p = parseInt(resultSummary.dataset.passedCount, 10);
        const total = parseInt(resultSummary.dataset.total, 10);
        const passed = resultSummary.dataset.passed === "true";
        resultSummary.textContent = passed
          ? window.Coach.t().allPassed
          : window.Coach.t().passedOf(p, total);
      }

      const errEl = block.querySelector("[data-testid='results-error']");
      if (errEl && errEl.dataset.runnerError) {
        errEl.textContent = `${window.Coach.t().runnerError(errEl.dataset.runnerError)}\n${errEl.dataset.stderr || ""}`;
      }
    }

    _renderProgressCounter();
    _renderCompletion();
  }

  // ── DOM construction ───────────────────────────────────────────────────────

  function _buildBlock(ex, locale) {
    const block = document.createElement("div");
    block.className = "exercise-item";
    block.setAttribute("data-testid", "exercise-item");
    block.setAttribute("data-slug", ex.slug);
    block.setAttribute("data-exercise-id", String(ex.id));

    // Title
    const title = document.createElement("h3");
    title.className = "exercise-item-title";
    title.setAttribute("data-testid", "exercise-item-title");
    title.textContent = _pick(ex.title, locale);
    block.appendChild(title);

    // Statement (markdown)
    const stmt = document.createElement("div");
    stmt.className = "markdown exercise-item-statement";
    stmt.setAttribute("data-testid", "exercise-item-statement");
    stmt.innerHTML = marked.parse(_pick(ex.statement_md, locale) || "");
    block.appendChild(stmt);

    // Editor label + textarea
    const label = document.createElement("label");
    label.setAttribute("data-testid", "editor-label");
    label.textContent = window.Coach.t().editorLabel;
    block.appendChild(label);

    const ta = document.createElement("textarea");
    block.appendChild(ta);

    // Controls row: Check button + solved badge
    const controls = document.createElement("div");
    controls.className = "controls";

    const checkBtn = document.createElement("button");
    checkBtn.setAttribute("data-testid", "check-btn");
    checkBtn.textContent = window.Coach.t().check;
    controls.appendChild(checkBtn);

    const solvedBadge = document.createElement("span");
    solvedBadge.className = "badge";
    solvedBadge.setAttribute("data-testid", "solved-badge");
    controls.appendChild(solvedBadge);

    block.appendChild(controls);

    // AI hint button (hidden by ai.js when no OpenAI key is configured).
    if (window.Coach.AI) window.Coach.AI.attachHintButton(block, ex.id);

    // Results panel (hidden until first check)
    const results = _buildResultsPanel();
    block.appendChild(results);

    // Mount the CodeMirror editor after the block is in the DOM buffer.
    // Defer to after append via a microtask is not needed — CodeMirror can
    // initialise on a detached textarea; the widget replaces it in-place.
    // Resolve the active CodeMirror theme from the theme module (dark/light).
    const cmTheme =
      window.Coach.Theme && window.Coach.Theme.getTheme() === "dark" ? "material" : "default";
    const cm = CodeMirror.fromTextArea(ta, {
      mode: "python",
      lineNumbers: true,
      indentUnit: 4,
      theme: cmTheme,
    });
    cm.setValue(ex.starter_code || "");
    _editors[ex.id] = cm;

    // Wire the Check button to this block.
    checkBtn.addEventListener("click", () => _check(ex.id, checkBtn, results, solvedBadge));

    // Reference-solution panel (hidden until solved; delegated to solution.js).
    if (window.Coach.Solution) {
      block.appendChild(window.Coach.Solution.buildPanel(ex.id, () => _authHeaders()));
    }

    return block;
  }

  function _buildResultsPanel() {
    const panel = document.createElement("div");
    panel.className = "results hidden";
    panel.setAttribute("data-testid", "results-panel");

    const heading = document.createElement("h4");
    const headingLabel = document.createElement("span");
    headingLabel.setAttribute("data-testid", "results-heading");
    headingLabel.textContent = window.Coach.t().resultsHeading;
    const summary = document.createElement("span");
    summary.setAttribute("data-testid", "results-summary");
    heading.appendChild(headingLabel);
    heading.appendChild(document.createTextNode(" "));
    heading.appendChild(summary);
    panel.appendChild(heading);

    const list = document.createElement("ul");
    list.setAttribute("data-testid", "results-list");
    panel.appendChild(list);

    const errPre = document.createElement("pre");
    errPre.className = "error hidden";
    errPre.setAttribute("data-testid", "results-error");
    panel.appendChild(errPre);

    return panel;
  }

  // ── Check / grading ───────────────────────────────────────────────────────

  async function _check(exerciseId, checkBtn, resultsPanel, solvedBadge) {
    // Guard: editor must exist (should always be true when wired correctly).
    const cm = _editors[exerciseId];
    if (!cm) return;

    checkBtn.disabled = true;
    checkBtn.textContent = window.Coach.t().checking;

    try {
      const res = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json", ..._authHeaders() },
        body: JSON.stringify({ exercise_id: exerciseId, code: cm.getValue() }),
      });
      if (res.status === 401) {
        window.Coach.logout();
        return;
      }
      const data = await res.json();
      _renderResults(data, resultsPanel);

      if (data.passed) {
        _solved[exerciseId] = true;
        _refreshSolvedBadge(solvedBadge, exerciseId);
        _renderProgressCounter();
        // A passing check may have completed the lesson: re-fetch to confirm.
        await _refreshLessonCompletion();
      }
    } catch (e) {
      _renderResults({ runner_error: String(e), tests: [] }, resultsPanel);
    } finally {
      checkBtn.disabled = false;
      checkBtn.textContent = window.Coach.t().check;
    }
  }

  // ── Progress fetching ─────────────────────────────────────────────────────

  async function _loadAllProgress() {
    if (!_lessonData || !_lessonData.exercises.length) return;

    // Fetch all exercise progress in parallel.
    const fetches = _lessonData.exercises.map((ex) =>
      fetch(`/api/progress/${ex.id}`, { headers: _authHeaders() }).then((r) =>
        r.ok ? r.json() : null,
      ),
    );
    const results = await Promise.all(fetches);
    for (const prog of results) {
      if (prog && prog.is_solved) {
        _solved[prog.exercise_id] = true;
        _refreshSolvedBadgeForExercise(prog.exercise_id);
      }
    }
  }

  // ── Lesson completion re-fetch ────────────────────────────────────────────

  async function _refreshLessonCompletion() {
    const res = await fetch(`/api/lessons/${encodeURIComponent(_slug)}`, {
      headers: _authHeaders(),
    });
    if (!res.ok) return;
    const fresh = await res.json();
    _lessonData.is_completed = fresh.is_completed;
    _lessonData.next_slug = fresh.next_slug;
    _renderCompletion();
  }

  // ── Completion panel ──────────────────────────────────────────────────────

  function _renderCompletion() {
    const panel = document.getElementById("lesson-completion");
    if (!panel) return;
    if (!_lessonData || !_lessonData.is_completed) {
      panel.classList.add("hidden");
      return;
    }
    panel.classList.remove("hidden");
    document.getElementById("completion-text").textContent = window.Coach.t().lessonCompleted;

    const nextBtn = document.getElementById("next-lesson-btn");
    const allDone = document.getElementById("all-complete-msg");
    if (_lessonData.next_slug) {
      nextBtn.classList.remove("hidden");
      nextBtn.textContent = window.Coach.t().nextLesson;
      nextBtn.onclick = () => {
        window.location.href = `/?lesson=${encodeURIComponent(_lessonData.next_slug)}`;
      };
      allDone.classList.add("hidden");
    } else {
      nextBtn.classList.add("hidden");
      allDone.classList.remove("hidden");
      allDone.textContent = window.Coach.t().allLessonsComplete;
    }
  }

  // ── Progress counter ──────────────────────────────────────────────────────

  function _renderProgressCounter() {
    const el = document.getElementById("progress-counter");
    if (!el || !_lessonData) return;
    const total = _lessonData.exercises.length;
    const solved = Object.values(_solved).filter(Boolean).length;
    el.textContent = window.Coach.t().progressOf(solved, total);
  }

  // ── Results rendering ─────────────────────────────────────────────────────

  function _renderResults(data, panel) {
    panel.classList.remove("hidden");

    const summary = panel.querySelector("[data-testid='results-summary']");
    const passed = Boolean(data.passed);
    const passedCount = data.passed_count || 0;
    const total = data.total || 0;
    summary.textContent = passed
      ? window.Coach.t().allPassed
      : window.Coach.t().passedOf(passedCount, total);
    // Store on the element so rerenderLocale can re-translate without re-running.
    summary.dataset.passedCount = passedCount;
    summary.dataset.total = total;
    summary.dataset.passed = String(passed);

    const list = panel.querySelector("[data-testid='results-list']");
    list.innerHTML = "";
    for (const item of data.tests || []) {
      const li = document.createElement("li");
      li.className = item.outcome;
      li.setAttribute("data-testid", "result-item");
      li.setAttribute("data-outcome", item.outcome);
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

    const err = panel.querySelector("[data-testid='results-error']");
    if (data.runner_error) {
      err.classList.remove("hidden");
      err.textContent = `${window.Coach.t().runnerError(data.runner_error)}\n${data.stderr || ""}`;
      err.dataset.runnerError = data.runner_error;
      err.dataset.stderr = data.stderr || "";
    } else {
      err.classList.add("hidden");
      delete err.dataset.runnerError;
    }
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  // Pick the active locale's string from a {en, ru} field.
  function _pick(localized, locale) {
    if (!localized) return "";
    return localized[locale] || localized.en || localized.ru || "";
  }

  // Update a solved badge by element reference; also sync the solution button.
  function _refreshSolvedBadge(badgeEl, exerciseId) {
    if (_solved[exerciseId]) {
      badgeEl.textContent = window.Coach.t().solved(1);
      badgeEl.classList.add("solved-badge-active");
    } else {
      badgeEl.textContent = "";
      badgeEl.classList.remove("solved-badge-active");
    }
    // Keep the solution button visibility in sync (delegated to solution.js).
    if (window.Coach.Solution) {
      window.Coach.Solution.refreshButton(exerciseId, Boolean(_solved[exerciseId]));
    }
  }

  // Update the solved badge for an exercise by looking it up in the DOM.
  function _refreshSolvedBadgeForExercise(exerciseId) {
    const block = document.querySelector(
      `[data-testid="exercise-item"][data-exercise-id="${exerciseId}"]`,
    );
    if (!block) return;
    const badge = block.querySelector("[data-testid='solved-badge']");
    if (badge) _refreshSolvedBadge(badge, exerciseId);
  }

  // Expose the editors map so theme.js can re-apply the CM theme on toggle.
  function getEditors() {
    return _editors;
  }

  return { renderExercises, rerenderLocale, getEditors };
})();
