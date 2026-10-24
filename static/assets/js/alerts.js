/**
 * MSREC alerts -- behaviour for the .ms-alert boxes rendered by
 * templates/_alerts.html.
 *
 * Loaded on both the public site and the dashboards, so it must not
 * depend on Bootstrap's JS: the dashboards never load the bundle, which
 * is why the close button is wired here rather than left to
 * data-bs-dismiss.
 *
 * Behaviour:
 *   - The X closes the alert (click, Enter or Space -- it is a <button>,
 *     so the keyboard cases come free).
 *   - Success/info alerts fade themselves out after a few seconds;
 *     warnings and errors stay put, because something went wrong and the
 *     reader may still need to act on it. The partial decides which is
 *     which via data-ms-auto-dismiss (in ms; absent = stays).
 *   - Hovering or focusing inside an alert cancels its auto-dismiss, so
 *     a long message never disappears mid-sentence.
 *   - MSRECAlerts.show() raises the same box from page JS (a floating
 *     toast), so client-side success/failure feedback matches what the
 *     server renders.
 */
(function (window, document) {
  "use strict";

  var DISMISSING = "is-dismissing";
  var REMOVE_FALLBACK_MS = 600;

  var ICONS = {
    success: '<path d="M20 6 9 17l-5-5"/>',
    danger: '<path d="M18 6 6 18M6 6l12 12"/>',
    warning: '<path d="M12 8v5"/><path d="M12 17h.01"/>',
    info: '<path d="M12 16v-5"/><path d="M12 8h.01"/>'
  };

  function prefersReducedMotion() {
    return window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  /** Collapse an alert out of the stack and drop it from the DOM. */
  function dismiss(alert) {
    if (!alert || alert.classList.contains(DISMISSING)) return;
    clearTimer(alert);
    alert.classList.add(DISMISSING);

    var done = false;
    function remove() {
      if (done) return;
      done = true;
      if (alert.parentNode) alert.parentNode.removeChild(alert);
    }
    alert.addEventListener("transitionend", remove, { once: true });
    // transitionend never fires where the transition is suppressed
    // (reduced motion, a hidden tab), so the by-then invisible box would
    // otherwise sit in the layout forever.
    window.setTimeout(remove, prefersReducedMotion() ? 50 : REMOVE_FALLBACK_MS);
  }

  function clearTimer(alert) {
    if (alert._msTimer) {
      window.clearTimeout(alert._msTimer);
      alert._msTimer = null;
    }
  }

  /** Start (or restart) the auto-dismiss countdown an alert asked for. */
  function arm(alert) {
    var delay = parseInt(alert.getAttribute("data-ms-auto-dismiss"), 10);
    if (!delay || delay <= 0) return;
    clearTimer(alert);
    alert._msTimer = window.setTimeout(function () {
      dismiss(alert);
    }, delay);
  }

  function setUp(alert) {
    if (alert._msReady) return;
    alert._msReady = true;

    // Fade in alerts added after first paint; server-rendered ones are
    // already on screen by the time this runs, so leave them alone.
    if (alert.classList.contains("is-entering")) {
      window.requestAnimationFrame(function () {
        window.requestAnimationFrame(function () {
          alert.classList.remove("is-entering");
        });
      });
    }

    arm(alert);

    if (alert.hasAttribute("data-ms-auto-dismiss")) {
      // Reading or interacting with an alert should not race its timer.
      alert.addEventListener("mouseenter", function () { clearTimer(alert); });
      alert.addEventListener("mouseleave", function () { arm(alert); });
      alert.addEventListener("focusin", function () { clearTimer(alert); });
      alert.addEventListener("focusout", function () { arm(alert); });
    }
  }

  function setUpAll(root) {
    (root || document).querySelectorAll(".ms-alert").forEach(setUp);
  }

  // Delegated so alerts injected later (htmx swaps, MSRECAlerts.show,
  // a modal built on the fly) get a working close button for free.
  document.addEventListener("click", function (event) {
    var target = event.target;
    var button = target && target.closest
      ? target.closest("[data-ms-dismiss]")
      : null;
    if (!button) return;
    event.preventDefault();
    dismiss(button.closest(".ms-alert"));
  });

  /** The floating stack JS-raised alerts go into, created on first use. */
  function toastStack() {
    var stack = document.querySelector(".ms-alerts--toast");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "ms-alerts ms-alerts--toast";
      document.body.appendChild(stack);
    }
    return stack;
  }

  function escapeHtml(value) {
    var div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  /**
   * Raise an alert from page JS.
   *   MSRECAlerts.show({ level: "success", title: "Saved", text: "..." })
   * Returns the element, so a caller can dismiss it early.
   */
  function show(options) {
    var opts = options || {};
    var level = ICONS[opts.level] ? opts.level : "info";
    var title = opts.title || "";
    var text = opts.text || "";
    var autoDismiss = opts.autoDismiss;
    if (autoDismiss === undefined) {
      autoDismiss = (level === "success" || level === "info") ? 6000 : 0;
    }

    var alert = document.createElement("div");
    alert.className = "ms-alert ms-alert--" + level + " is-entering" +
      (title ? "" : " ms-alert--slim");
    alert.setAttribute("role", level === "danger" ? "alert" : "status");
    if (autoDismiss) alert.setAttribute("data-ms-auto-dismiss", autoDismiss);
    alert.innerHTML =
      '<span class="ms-alert__icon" aria-hidden="true">' +
        '<svg viewBox="0 0 24 24">' + ICONS[level] + "</svg>" +
      "</span>" +
      '<div class="ms-alert__content">' +
        (title ? '<h6 class="ms-alert__title">' + escapeHtml(title) + "</h6>" : "") +
        '<div class="ms-alert__text">' + escapeHtml(text) + "</div>" +
      "</div>" +
      '<button type="button" class="ms-alert__close" data-ms-dismiss aria-label="Dismiss this message">' +
        '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>' +
      "</button>";

    (opts.container || toastStack()).appendChild(alert);
    setUp(alert);
    return alert;
  }

  window.MSRECAlerts = { show: show, dismiss: dismiss, refresh: setUpAll };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { setUpAll(); });
  } else {
    setUpAll();
  }
})(window, document);
