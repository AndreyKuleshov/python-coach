"use strict";

// Auth-UI block: token helpers, auth modal, login/register handlers, auth chrome.
//
// Loaded before app.js. Writes public functions into window.Coach so app.js can
// call them without relying on implicit globals, and reads Coach.* callbacks that
// app.js registers for the reverse direction (renderCheckGate, refreshProgress).
//
// Load order in index.html: auth.js → app.js.
// Shared namespace contract:
//   auth.js writes: Coach.isLoggedIn, Coach.authHeaders, Coach.openAuth,
//                   Coach.logout, Coach.renderAuthChrome, Coach.refreshAuthDependentUI
//   app.js writes:  Coach.t (locale getter), Coach.lessonSlug,
//                   Coach.renderCheckGate, Coach.refreshProgress

// Initialise the shared namespace if app.js has not done so yet.
window.Coach = window.Coach || {};

// ── Token helpers ────────────────────────────────────────────────────────────

const TOKEN_KEY = "python-coach.token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function isLoggedIn() {
  return Boolean(getToken());
}

// Authorization header attached to protected (submit/progress) requests.
function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

let currentUserEmail = null;

// ── Auth modal helpers ───────────────────────────────────────────────────────

function openAuth() {
  document.getElementById("auth-modal").classList.remove("hidden");
  showLoginForm();
}

function closeAuth() {
  document.getElementById("auth-modal").classList.add("hidden");
  clearAuthErrors();
}

function showLoginForm() {
  document.getElementById("login-form").classList.remove("hidden");
  document.getElementById("register-form").classList.add("hidden");
  document.getElementById("confirm-pending").classList.add("hidden");
  clearAuthErrors();
}

function showRegisterForm() {
  document.getElementById("login-form").classList.add("hidden");
  document.getElementById("register-form").classList.remove("hidden");
  document.getElementById("confirm-pending").classList.add("hidden");
  clearAuthErrors();
}

function clearAuthErrors() {
  for (const id of ["login-error", "register-error"]) {
    const el = document.getElementById(id);
    el.classList.add("hidden");
    el.textContent = "";
  }
}

function showError(id, message) {
  const el = document.getElementById(id);
  el.textContent = message;
  el.classList.remove("hidden");
}

// Render every auth-related chrome string + the logged-in/out state.
function renderAuthChrome() {
  // t() is provided by app.js via Coach.t(); fall back to a no-op stub during
  // the brief window between auth.js load and app.js load (should never happen
  // in practice since scripts are sequential, but guards against future reorder).
  const t = window.Coach.t ? window.Coach.t() : null;
  if (!t) return;

  document.getElementById("open-auth-btn").textContent = t.logIn;
  document.getElementById("logout-btn").textContent = t.logOut;
  document.getElementById("login-heading").textContent = t.loginHeading;
  document.getElementById("register-heading").textContent = t.registerHeading;
  document.getElementById("login-email-label").textContent = t.email;
  document.getElementById("login-password-label").textContent = t.password;
  document.getElementById("register-email-label").textContent = t.email;
  document.getElementById("register-password-label").textContent = t.password;
  document.getElementById("login-submit").textContent = t.logIn;
  document.getElementById("register-submit").textContent = t.register;
  document.getElementById("login-switch-prompt").textContent = t.noAccount;
  document.getElementById("show-register").textContent = t.register;
  document.getElementById("register-switch-prompt").textContent = t.haveAccount;
  document.getElementById("show-login").textContent = t.logIn;
  document.getElementById("confirm-pending-heading").textContent = t.checkYourEmail;

  const loggedIn = isLoggedIn();
  document.getElementById("open-auth-btn").classList.toggle("hidden", loggedIn);
  document.getElementById("auth-user").classList.toggle("hidden", !loggedIn);
  if (loggedIn && currentUserEmail) {
    document.getElementById("auth-email").textContent = currentUserEmail;
  }
}

// Map a backend auth error to a localized message.
function authErrorMessage(status, detail) {
  const t = window.Coach.t ? window.Coach.t() : null;
  if (!t) return String(detail);
  if (status === 401) return t.invalidCredentials;
  if (status === 403) return t.emailNotConfirmed;
  if (status === 409) return t.emailTaken;
  if (status === 422) return t.passwordTooShort;
  return t.genericError;
}

async function doLogin(email, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    showError("login-error", authErrorMessage(res.status, body.detail));
    return;
  }
  const data = await res.json();
  setToken(data.access_token);
  await loadCurrentUser();
  closeAuth();
  refreshAuthDependentUI();
}

async function doRegister(email, password) {
  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    showError("register-error", authErrorMessage(res.status, body.detail));
    return;
  }
  // Success: account is unconfirmed -> show the "check your email" state.
  document.getElementById("login-form").classList.add("hidden");
  document.getElementById("register-form").classList.add("hidden");
  document.getElementById("confirm-pending").classList.remove("hidden");
  const t = window.Coach.t ? window.Coach.t() : null;
  if (t) {
    document.getElementById("confirm-pending-text").textContent = t.confirmPendingText(email);
  }
}

async function loadCurrentUser() {
  const res = await fetch("/api/auth/me", { headers: authHeaders() });
  if (!res.ok) {
    logout();
    return;
  }
  const data = await res.json();
  currentUserEmail = data.email;
}

function logout() {
  clearToken();
  currentUserEmail = null;
  refreshAuthDependentUI();
}

// Re-render UI that depends on auth state (badge, check gate, chrome, progress).
// Calls back into app.js via the Coach namespace for lesson-view-specific concerns.
function refreshAuthDependentUI() {
  renderAuthChrome();
  const lessonSlug = window.Coach.lessonSlug;
  if (lessonSlug) {
    if (window.Coach.renderCheckGate) window.Coach.renderCheckGate();
    if (window.Coach.refreshProgress) window.Coach.refreshProgress();
  }
}

function wireAuthUI() {
  document.getElementById("open-auth-btn").addEventListener("click", openAuth);
  document.getElementById("auth-close-btn").addEventListener("click", closeAuth);
  document.getElementById("logout-btn").addEventListener("click", logout);
  document.getElementById("show-register").addEventListener("click", (e) => {
    e.preventDefault();
    showRegisterForm();
  });
  document.getElementById("show-login").addEventListener("click", (e) => {
    e.preventDefault();
    showLoginForm();
  });
  const loginPrompt = document.getElementById("login-prompt");
  if (loginPrompt) loginPrompt.addEventListener("click", (e) => {
    e.preventDefault();
    openAuth();
  });
  document.getElementById("login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    doLogin(
      document.getElementById("login-email").value,
      document.getElementById("login-password").value,
    );
  });
  document.getElementById("register-form").addEventListener("submit", (e) => {
    e.preventDefault();
    doRegister(
      document.getElementById("register-email").value,
      document.getElementById("register-password").value,
    );
  });
}

// Wire the auth UI event listeners immediately on script load (DOM is ready by
// the time deferred scripts run, so getElementById is safe here).
wireAuthUI();

// ── Publish auth API into the shared namespace ───────────────────────────────

window.Coach.isLoggedIn = isLoggedIn;
window.Coach.authHeaders = authHeaders;
window.Coach.openAuth = openAuth;
window.Coach.logout = logout;
window.Coach.renderAuthChrome = renderAuthChrome;
window.Coach.refreshAuthDependentUI = refreshAuthDependentUI;
window.Coach.loadCurrentUser = loadCurrentUser;
