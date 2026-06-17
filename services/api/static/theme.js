"use strict";

// Theme management: light / dark mode with OS-preference default, localStorage
// persistence, no-flash guarantee (this script is loaded synchronously before
// any content), and CodeMirror theme switching.
//
// Exposes window.Coach.Theme:
//   getTheme()           — "light" | "dark" (current)
//   setTheme(t)          — apply + persist a theme
//   toggle()             — flip between light and dark
//   applyToEditor(cm)    — apply the current CodeMirror theme to one editor
//   applyToAllEditors()  — re-apply to every editor tracked by Exercise module
//
// The root attribute driven: <html data-theme="dark"> / <html data-theme="light">
// CodeMirror dark theme: "material" from cdnjs (pinned 5.65.16, same as main CM).

window.Coach = window.Coach || {};

window.Coach.Theme = (function () {
  const STORAGE_KEY = "python-coach.theme";
  const ATTR = "data-theme";
  // CodeMirror "material" dark theme — pinned to match existing CM 5.65.16 CDN.
  const CM_DARK_THEME = "material";
  const CM_LIGHT_THEME = "default";

  // Resolve the initial theme: explicit user choice wins, then OS preference,
  // then light fallback. Called before the first paint (no-flash).
  function _resolve() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "dark" || stored === "light") return stored;
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
      return "dark";
    }
    return "light";
  }

  // Apply theme to <html> without persisting (used during init and toggle).
  function _apply(theme) {
    document.documentElement.setAttribute(ATTR, theme);
  }

  // Get the currently active theme from the root attribute.
  function getTheme() {
    return document.documentElement.getAttribute(ATTR) || "light";
  }

  // Apply and persist a theme, then update CodeMirror editors.
  function setTheme(theme) {
    if (theme !== "light" && theme !== "dark") return;
    _apply(theme);
    localStorage.setItem(STORAGE_KEY, theme);
    _syncToggleButton();
    applyToAllEditors();
  }

  function toggle() {
    setTheme(getTheme() === "dark" ? "light" : "dark");
  }

  // Apply the current CodeMirror theme to a single editor instance.
  function applyToEditor(cm) {
    if (!cm || typeof cm.setOption !== "function") return;
    cm.setOption("theme", getTheme() === "dark" ? CM_DARK_THEME : CM_LIGHT_THEME);
  }

  // Re-apply the CodeMirror theme to every live editor (called after toggle).
  // Reads from window.Coach.Exercise._editors if available; safe to call before
  // exercises are rendered (no-op).
  function applyToAllEditors() {
    const ex = window.Coach && window.Coach.Exercise;
    if (!ex || !ex.getEditors) return;
    for (const cm of Object.values(ex.getEditors())) {
      applyToEditor(cm);
    }
  }

  // Keep the toggle button icon/label in sync with the active theme.
  function _syncToggleButton() {
    const theme = getTheme();
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;
    const isDark = theme === "dark";
    btn.setAttribute("data-theme-active", theme);
    // Sun icon for "switch to light", moon icon for "switch to dark".
    btn.querySelector(".theme-toggle-icon").textContent = isDark ? "☀" : "☾";
    const label = btn.querySelector(".theme-toggle-label");
    if (label) {
      const t = window.Coach && window.Coach.t ? window.Coach.t() : null;
      label.textContent = t
        ? (isDark ? t.themeLight : t.themeDark)
        : (isDark ? "Light" : "Dark");
    }
    const ariaLabel = isDark
      ? (window.Coach && window.Coach.t ? window.Coach.t().themeLightAriaLabel : "Switch to light mode")
      : (window.Coach && window.Coach.t ? window.Coach.t().themeDarkAriaLabel : "Switch to dark mode");
    btn.setAttribute("aria-label", ariaLabel);
    btn.setAttribute("title", ariaLabel);
  }

  // Called by app.js on locale switch to re-translate the toggle label.
  function relocalize() {
    _syncToggleButton();
  }

  // ── No-flash init: apply saved/OS theme immediately ──────────────────────────
  // This runs synchronously when the script is parsed (before body renders).
  _apply(_resolve());

  return { getTheme, setTheme, toggle, applyToEditor, applyToAllEditors, relocalize };
})();
