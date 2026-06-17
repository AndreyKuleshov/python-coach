"use strict";

// AI features: per-exercise hint buttons + a floating lesson-explanation chat.
//
// Both call OUR backend (which holds the OpenAI key); the browser never sees the
// key. When the backend reports ai_enabled=false (no key configured) the hint
// buttons and the chat widget are not shown at all.
//
// Exposes window.Coach.AI:
//   setEnabled(flag)                  — toggle visibility of all AI affordances.
//   isEnabled()                       — current flag (read by exercise.js).
//   attachHintButton(block, exId)     — append a Hint button + output to a block.
//   mountChatWidget()                 — build the floating widget once.
//
// Kept in its own file (≤500 lines) per the size cap; loaded before exercise.js
// and app.js so the namespace is ready when they render.

window.Coach = window.Coach || {};
window.Coach.AI = (function () {
  let _enabled = false;

  // ── enable / disable ────────────────────────────────────────────────────────

  function setEnabled(flag) {
    _enabled = Boolean(flag);
    const widget = document.getElementById("ai-chat-widget");
    if (widget) widget.classList.toggle("hidden", !_enabled);
    // Hint buttons already rendered: hide/show them in place.
    document.querySelectorAll("[data-testid='hint-btn']").forEach((b) => {
      b.classList.toggle("hidden", !_enabled);
    });
  }

  function isEnabled() {
    return _enabled;
  }

  // ── per-exercise hint ─────────────────────────────────────────────────────────

  // Append a Hint button + a (hidden) hint output area to an exercise block's
  // controls row. The button asks OUR backend for an approach hint in the
  // active locale and renders it below the controls.
  function attachHintButton(block, exerciseId) {
    const controls = block.querySelector(".controls");
    if (!controls) return;

    const hintBtn = document.createElement("button");
    hintBtn.type = "button";
    hintBtn.className = "hint-btn";
    hintBtn.setAttribute("data-testid", "hint-btn");

    // Icon + bilingual label structure so both light and dark themes render clearly.
    const icon = document.createElement("span");
    icon.className = "hint-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = "💡";
    const label = document.createElement("span");
    label.className = "hint-label";
    label.textContent = window.Coach.t().hint;
    hintBtn.appendChild(icon);
    hintBtn.appendChild(label);

    hintBtn.classList.toggle("hidden", !_enabled);
    controls.appendChild(hintBtn);

    const hintOut = document.createElement("p");
    hintOut.className = "hint-text hidden";
    hintOut.setAttribute("data-testid", "hint-text");
    block.appendChild(hintOut);

    hintBtn.addEventListener("click", () => _requestHint(exerciseId, hintBtn, hintOut));
  }

  async function _requestHint(exerciseId, hintBtn, hintOut) {
    hintBtn.disabled = true;
    const labelEl = hintBtn.querySelector(".hint-label");
    const originalLabel = window.Coach.t().hint;
    if (labelEl) labelEl.textContent = window.Coach.t().hintLoading;
    hintOut.classList.remove("hidden");
    hintOut.textContent = window.Coach.t().hintLoading;
    try {
      const res = await fetch(`/api/exercises/${exerciseId}/hint`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.Coach.authHeaders() },
        body: JSON.stringify({ locale: window.Coach.getLocale() }),
      });
      if (res.status === 401) {
        window.Coach.logout();
        return;
      }
      if (!res.ok) {
        hintOut.textContent = window.Coach.t().hintError;
        return;
      }
      const data = await res.json();
      hintOut.textContent = data.hint || window.Coach.t().hintError;
    } catch (e) {
      hintOut.textContent = window.Coach.t().hintError;
    } finally {
      hintBtn.disabled = false;
      if (labelEl) labelEl.textContent = originalLabel;
    }
  }

  // ── floating chat widget ──────────────────────────────────────────────────────

  // Build the widget once and append it to <body>. It is fixed bottom-right and
  // starts collapsed; the toggle shows the panel. Hidden entirely when AI is off.
  function mountChatWidget() {
    if (document.getElementById("ai-chat-widget")) return;

    const widget = document.createElement("div");
    widget.id = "ai-chat-widget";
    widget.className = "ai-chat-widget hidden";
    widget.setAttribute("data-testid", "ai-chat-widget");

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "ai-chat-toggle";
    toggle.setAttribute("data-testid", "chat-toggle");
    toggle.textContent = window.Coach.t().chatOpen;
    widget.appendChild(toggle);

    const panel = document.createElement("div");
    panel.className = "ai-chat-panel hidden";
    panel.setAttribute("data-testid", "chat-panel");

    const header = document.createElement("div");
    header.className = "ai-chat-header";
    const title = document.createElement("span");
    title.setAttribute("data-testid", "chat-title");
    title.textContent = window.Coach.t().chatTitle;
    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "ai-chat-close";
    closeBtn.setAttribute("data-testid", "chat-close");
    closeBtn.textContent = window.Coach.t().chatClose;
    header.appendChild(title);
    header.appendChild(closeBtn);
    panel.appendChild(header);

    const intro = document.createElement("p");
    intro.className = "ai-chat-intro";
    intro.setAttribute("data-testid", "chat-intro");
    intro.textContent = window.Coach.t().chatIntro;
    panel.appendChild(intro);

    const excerptLabel = document.createElement("label");
    excerptLabel.setAttribute("data-testid", "chat-excerpt-label");
    excerptLabel.textContent = window.Coach.t().chatExcerptLabel;
    panel.appendChild(excerptLabel);

    const excerpt = document.createElement("textarea");
    excerpt.className = "ai-chat-excerpt";
    excerpt.setAttribute("data-testid", "chat-input");
    excerpt.maxLength = 6000;
    panel.appendChild(excerpt);

    const questionLabel = document.createElement("label");
    questionLabel.setAttribute("data-testid", "chat-question-label");
    questionLabel.textContent = window.Coach.t().chatQuestionLabel;
    panel.appendChild(questionLabel);

    const question = document.createElement("input");
    question.type = "text";
    question.className = "ai-chat-question";
    question.setAttribute("data-testid", "chat-question");
    question.maxLength = 1000;
    panel.appendChild(question);

    const send = document.createElement("button");
    send.type = "button";
    send.className = "ai-chat-send";
    send.setAttribute("data-testid", "chat-send");
    send.textContent = window.Coach.t().chatSend;
    panel.appendChild(send);

    const answer = document.createElement("div");
    answer.className = "ai-chat-answer hidden markdown";
    answer.setAttribute("data-testid", "chat-answer");
    panel.appendChild(answer);

    widget.appendChild(panel);
    document.body.appendChild(widget);

    toggle.addEventListener("click", () => {
      panel.classList.toggle("hidden");
    });
    closeBtn.addEventListener("click", () => panel.classList.add("hidden"));
    send.addEventListener("click", () => _sendChat(excerpt, question, send, answer));

    setEnabled(_enabled);
  }

  async function _sendChat(excerptEl, questionEl, sendBtn, answerEl) {
    const excerpt = excerptEl.value.trim();
    answerEl.classList.remove("hidden");
    if (!excerpt) {
      answerEl.textContent = window.Coach.t().chatNeedExcerpt;
      return;
    }
    const original = window.Coach.t().chatSend;
    sendBtn.disabled = true;
    sendBtn.textContent = window.Coach.t().chatSending;
    answerEl.textContent = window.Coach.t().chatSending;
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...window.Coach.authHeaders() },
        body: JSON.stringify({
          excerpt,
          question: questionEl.value.trim(),
          locale: window.Coach.getLocale(),
        }),
      });
      if (res.status === 401) {
        window.Coach.logout();
        return;
      }
      if (!res.ok) {
        answerEl.textContent = window.Coach.t().chatError;
        return;
      }
      const data = await res.json();
      // Sanitize before innerHTML: model output is user-influenced, so we pass
      // marked's HTML through DOMPurify to neutralize any injected scripts/handlers.
      const raw = data.answer || "";
      const html = window.marked ? marked.parse(raw) : raw || window.Coach.t().chatError;
      answerEl.innerHTML = window.DOMPurify
        ? DOMPurify.sanitize(html)
        : html;
    } catch (e) {
      answerEl.textContent = window.Coach.t().chatError;
    } finally {
      sendBtn.disabled = false;
      sendBtn.textContent = original;
    }
  }

  // Re-translate the widget's static chrome on a locale switch.
  function relocalize() {
    const widget = document.getElementById("ai-chat-widget");
    if (!widget) return;
    const t = window.Coach.t();
    const set = (testid, text) => {
      const el = widget.querySelector(`[data-testid='${testid}']`);
      if (el) el.textContent = text;
    };
    set("chat-toggle", t.chatOpen);
    set("chat-title", t.chatTitle);
    set("chat-close", t.chatClose);
    set("chat-intro", t.chatIntro);
    set("chat-excerpt-label", t.chatExcerptLabel);
    set("chat-question-label", t.chatQuestionLabel);
    set("chat-send", t.chatSend);
    document.querySelectorAll("[data-testid='hint-btn']").forEach((b) => {
      if (!b.disabled) {
        const lbl = b.querySelector(".hint-label");
        if (lbl) lbl.textContent = t.hint;
      }
    });
  }

  return { setEnabled, isEnabled, attachHintButton, mountChatWidget, relocalize };
})();
