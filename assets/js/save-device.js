/* ==========================================================
   MSREC — "Save to this device" prompt
   Exposes window.MSRECSaveDevice with:
     .prompt({ name, email })  -> show the modal after auth success
     .getSaved()               -> read the remembered account (or null)
     .forget()                 -> clear it
   On the login page it also pre-fills a remembered account and
   shows a small welcome banner.

   Note: only the display name + email are stored, in localStorage,
   on this device. The raw password is never persisted.
========================================================== */
(function () {
  "use strict";

  var STORAGE_KEY = "msrec_saved_account";

  function safeGet() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function safeSet(account) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(account));
      return true;
    } catch (e) {
      return false;
    }
  }

  function safeClear() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
  }

  function initials(name, email) {
    var src = (name || email || "?").trim();
    var parts = src.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]);
    return src.slice(0, 2);
  }

  function esc(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var overlay = null;
  var lastFocused = null;

  function buildModal(account) {
    var name = account.name || "Your account";
    var email = account.email || "";

    overlay = document.createElement("div");
    overlay.className = "sd-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "sdTitle");

    overlay.innerHTML =
      '<div class="sd-modal" role="document">' +
        '<button type="button" class="sd-close" aria-label="Dismiss"><i class="bi bi-x-lg"></i></button>' +
        '<div class="sd-icon">' +
          '<i class="bi bi-phone"></i>' +
          '<span class="sd-icon-badge"><i class="bi bi-check-lg"></i></span>' +
        '</div>' +
        '<h2 class="sd-title" id="sdTitle">Stay signed in on this device?</h2>' +
        '<p class="sd-text">Save your details to this device so MSREC recognises you and signs you in faster next time. Only do this on a device that’s yours.</p>' +
        '<div class="sd-account">' +
          '<span class="sd-avatar">' + esc(initials(name, email)) + '</span>' +
          '<span class="sd-account-meta">' +
            '<span class="sd-account-name">' + esc(name) + '</span>' +
            '<span class="sd-account-email">' + esc(email) + '</span>' +
          '</span>' +
        '</div>' +
        '<div class="sd-actions">' +
          '<button type="button" class="sd-btn sd-btn-primary" data-sd-save><i class="bi bi-shield-check"></i> Save to this device</button>' +
          '<button type="button" class="sd-btn sd-btn-ghost" data-sd-skip>Not now</button>' +
        '</div>' +
        '<p class="sd-note"><i class="bi bi-lock-fill"></i> Stored on this device only · never shared</p>' +
      '</div>';

    document.body.appendChild(overlay);
    return overlay;
  }

  function closeModal() {
    if (!overlay) return;
    overlay.classList.remove("is-open");
    document.removeEventListener("keydown", onKeydown);
    var el = overlay;
    window.setTimeout(function () {
      if (el && el.parentNode) el.parentNode.removeChild(el);
    }, 320);
    overlay = null;
    if (lastFocused && lastFocused.focus) lastFocused.focus();
  }

  function onKeydown(e) {
    if (!overlay) return;
    if (e.key === "Escape") {
      closeModal();
      return;
    }
    if (e.key === "Tab") {
      var focusables = overlay.querySelectorAll("button");
      if (!focusables.length) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  function prompt(account) {
    account = account || {};
    if (!account.email) return;

    lastFocused = document.activeElement;
    buildModal(account);

    overlay.querySelector("[data-sd-save]").addEventListener("click", function () {
      safeSet({ name: account.name || "", email: account.email, savedAt: Date.now() });
      closeModal();
    });
    overlay.querySelector("[data-sd-skip]").addEventListener("click", closeModal);
    overlay.querySelector(".sd-close").addEventListener("click", closeModal);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeModal();
    });
    document.addEventListener("keydown", onKeydown);

    // force reflow so the transition runs, then open + focus primary
    void overlay.offsetWidth;
    overlay.classList.add("is-open");
    window.setTimeout(function () {
      var save = overlay && overlay.querySelector("[data-sd-save]");
      if (save) save.focus();
    }, 60);
  }

  // ---- Login page: pre-fill a remembered account ----
  function hydrateLoginPage() {
    var form = document.getElementById("loginForm");
    if (!form) return;
    var saved = safeGet();
    if (!saved || !saved.email) return;

    var emailInput = document.getElementById("email");
    var remember = form.querySelector('input[name="remember"]');
    if (emailInput) emailInput.value = saved.email;
    if (remember) remember.checked = true;

    var banner = document.createElement("div");
    banner.className = "sd-welcome";
    banner.innerHTML =
      '<span class="sd-avatar">' + esc(initials(saved.name, saved.email)) + '</span>' +
      '<span class="sd-welcome-meta">' +
        '<span class="sd-welcome-hi">Welcome back' + (saved.name ? ", " + esc(saved.name.split(/\s+/)[0]) : "") + '</span>' +
        '<span class="sd-welcome-email">' + esc(saved.email) + '</span>' +
      '</span>' +
      '<button type="button" class="sd-welcome-forget">Not you?</button>';

    form.parentNode.insertBefore(banner, form);

    banner.querySelector(".sd-welcome-forget").addEventListener("click", function () {
      safeClear();
      if (emailInput) { emailInput.value = ""; emailInput.focus(); }
      if (remember) remember.checked = false;
      banner.parentNode.removeChild(banner);
    });

    // put the cursor where the user still needs to type
    var pwd = document.getElementById("password");
    if (pwd) window.setTimeout(function () { pwd.focus(); }, 0);
  }

  window.MSRECSaveDevice = {
    prompt: prompt,
    getSaved: safeGet,
    forget: safeClear
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", hydrateLoginPage);
  } else {
    hydrateLoginPage();
  }
})();
