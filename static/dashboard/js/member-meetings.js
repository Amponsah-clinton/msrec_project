/* Committee member — Meetings & Agenda.
   1. Meeting lists: live search + type filter (client-side; the lists are small).
   2. Agenda: meeting picker jumps on change.
   3. Agenda: private notes autosave (debounced) and "Mark as prepared", posted
      to the same endpoint the no-JS <form> uses, so the page works either way. */
(function () {
  "use strict";
  document.documentElement.classList.add("mm-js");

  /* ---------------- 1. list search + filter ---------------- */
  var list = document.getElementById("mmList");
  if (list) {
    var search = document.getElementById("mmSearch");
    var filters = document.getElementById("mmFilters");
    var empty = document.getElementById("mmNoMatch");
    var cards = Array.prototype.slice.call(list.querySelectorAll("[data-search]"));
    var activeType = "all";

    var apply = function () {
      var q = search ? search.value.trim().toLowerCase() : "";
      var shown = 0;
      cards.forEach(function (card) {
        var ok = (activeType === "all" || card.dataset.type === activeType) &&
                 (!q || (card.dataset.search || "").indexOf(q) !== -1);
        card.hidden = !ok;
        if (ok) shown++;
      });
      if (empty) empty.hidden = shown !== 0;
    };

    if (search) search.addEventListener("input", apply);
    if (filters) {
      filters.addEventListener("click", function (e) {
        var btn = e.target.closest("button[data-type]");
        if (!btn) return;
        activeType = btn.dataset.type;
        filters.querySelectorAll("button").forEach(function (b) { b.classList.toggle("active", b === btn); });
        apply();
      });
    }
  }

  /* ---------------- 2. agenda picker ---------------- */
  var select = document.getElementById("mmMeetingSelect");
  if (select) {
    select.addEventListener("change", function () {
      var form = document.getElementById("mmPicker");
      if (form) form.submit();
    });
  }

  /* ---------------- 3. notes autosave ---------------- */
  var forms = document.querySelectorAll("[data-note-form]");
  if (!forms.length) return;

  var total = document.querySelectorAll(".mm-item").length;
  var countEl = document.getElementById("mmReviewedCount");
  var ringEl = document.getElementById("mmRing");
  var ringPct = document.getElementById("mmRingPct");

  function csrf(form) {
    var el = form.querySelector("input[name=csrfmiddlewaretoken]");
    return el ? el.value : "";
  }

  function setStatus(el, text, kind) {
    el.textContent = text;
    el.className = "mm-saved" + (kind ? " " + kind : "");
  }

  function updateProgress(reviewed) {
    if (countEl) countEl.textContent = reviewed;
    var pct = total ? Math.round((100 * reviewed) / total) : 0;
    if (ringEl) ringEl.style.setProperty("--p", pct);
    if (ringPct) ringPct.textContent = pct + "%";
  }

  function post(form, extra) {
    var data = new FormData();
    data.append("csrfmiddlewaretoken", csrf(form));
    var ta = form.querySelector("textarea");
    if (ta) data.append("note", ta.value);
    Object.keys(extra || {}).forEach(function (k) { data.append(k, extra[k]); });
    return fetch(form.action, {
      method: "POST",
      body: data,
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch" }
    }).then(function (res) {
      return res.json().catch(function () { return { ok: false, error: "Unexpected response." }; })
        .then(function (json) { json.httpOk = res.ok; return json; });
    });
  }

  forms.forEach(function (form) {
    var status = form.querySelector("[data-status]");
    var ta = form.querySelector("textarea");
    var toggle = form.querySelector("[data-toggle-reviewed]");
    var item = form.closest(".mm-item");
    var timer = null;
    var lastSaved = ta ? ta.value : "";

    function save(extra, quiet) {
      setStatus(status, "Saving…", "");
      return post(form, extra).then(function (json) {
        if (json && json.ok) {
          lastSaved = ta ? ta.value : "";
          setStatus(status, "Saved" + (json.saved_at ? " at " + json.saved_at : ""), "ok");
          if (typeof json.reviewed_count === "number") updateProgress(json.reviewed_count);
          return json;
        }
        setStatus(status, (json && json.error) || "Couldn't save. Try again.", "err");
        return null;
      }).catch(function () {
        setStatus(status, "You appear to be offline — not saved.", "err");
        return null;
      });
    }

    if (ta) {
      ta.addEventListener("input", function () {
        setStatus(status, "Unsaved changes…", "");
        clearTimeout(timer);
        timer = setTimeout(function () { if (ta.value !== lastSaved) save({}, true); }, 900);
      });
      ta.addEventListener("blur", function () {
        clearTimeout(timer);
        if (ta.value !== lastSaved) save({}, true);
      });
    }

    if (toggle) {
      toggle.addEventListener("click", function (e) {
        e.preventDefault();
        clearTimeout(timer);
        var next = toggle.getAttribute("aria-pressed") !== "true";
        save({ is_reviewed: next ? "1" : "0" }).then(function (json) {
          if (!json) return;
          var on = !!json.is_reviewed;
          toggle.setAttribute("aria-pressed", on ? "true" : "false");
          toggle.value = on ? "0" : "1";
          var label = toggle.querySelector("[data-toggle-label]");
          if (label) label.textContent = on ? "Prepared" : "Mark as prepared";
          if (item) item.classList.toggle("is-reviewed", on);
        });
      });
    }

    form.addEventListener("submit", function (e) {
      // Enter can't submit a textarea, so this is the "Save note" button (only
      // visible without JS anyway) -- keep it on the fetch path if it ever fires.
      if (e.submitter && e.submitter.hasAttribute("data-toggle-reviewed")) return;
      e.preventDefault();
      save({});
    });
  });

  // Don't lose a note the member just typed if they navigate away mid-debounce.
  window.addEventListener("beforeunload", function (e) {
    var pending = false;
    forms.forEach(function (f) {
      var s = f.querySelector("[data-status]");
      if (s && s.textContent.indexOf("Unsaved") === 0) pending = true;
    });
    if (pending) { e.preventDefault(); e.returnValue = ""; }
  });
})();
