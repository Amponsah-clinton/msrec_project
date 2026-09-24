/* Site Settings > Approval Documents: switch between the email / letter /
   certificate forms, insert {placeholders} where the cursor is, and keep
   the little certificate sketch in step with the title fields. */
(function () {
  var root = document.getElementById("approval-docs");
  if (!root) return;

  var cards = root.querySelectorAll("[data-apd-card]");
  var buttons = root.querySelectorAll("[data-apd-show]");
  var lastField = null;

  function show(name) {
    cards.forEach(function (card) { card.hidden = card.getAttribute("data-apd-card") !== name; });
    buttons.forEach(function (btn) {
      var on = btn.getAttribute("data-apd-show") === name;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
    lastField = null;
    try { sessionStorage.setItem("apd:card", name); } catch (e) {}
  }
  buttons.forEach(function (btn) {
    btn.addEventListener("click", function () { show(btn.getAttribute("data-apd-show")); });
  });
  try {
    var remembered = sessionStorage.getItem("apd:card");
    if (remembered && root.querySelector('[data-apd-card="' + remembered + '"]')) show(remembered);
  } catch (e) {}

  // Remember the last text field used, so a chip inserts into it.
  root.addEventListener("focusin", function (evt) {
    var el = evt.target;
    if ((el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && el.type === "text")) && el.closest("[data-apd-card]")) {
      lastField = el;
    }
  });

  root.querySelectorAll("[data-apd-insert]").forEach(function (chip) {
    // mousedown would steal focus from the field before click; keep it.
    chip.addEventListener("mousedown", function (evt) { evt.preventDefault(); });
    chip.addEventListener("click", function () {
      var token = chip.getAttribute("data-apd-insert");
      var field = lastField;
      if (!field || field.closest("[data-apd-card]").hidden) {
        var visible = root.querySelector("[data-apd-card]:not([hidden])");
        field = visible && visible.querySelector("textarea");
      }
      if (!field) return;
      var start = field.selectionStart == null ? field.value.length : field.selectionStart;
      var end = field.selectionEnd == null ? start : field.selectionEnd;
      field.value = field.value.slice(0, start) + token + field.value.slice(end);
      field.focus();
      var caret = start + token.length;
      try { field.setSelectionRange(caret, caret); } catch (e) {}
      field.dispatchEvent(new Event("input", { bubbles: true }));
      chip.classList.add("is-flash");
      setTimeout(function () { chip.classList.remove("is-flash"); }, 350);
    });
  });

  root.querySelectorAll("[data-apd-sketch]").forEach(function (input) {
    var target = document.getElementById(input.getAttribute("data-apd-sketch"));
    if (!target) return;
    input.addEventListener("input", function () { target.textContent = input.value; });
  });

  // "Certificates" link in the intro switches settings tab.
  root.querySelectorAll("[data-apd-tab-link]").forEach(function (link) {
    link.addEventListener("click", function (evt) {
      var tab = document.querySelector('.settings-tab[data-target="' + link.getAttribute("data-apd-tab-link") + '"]');
      if (tab) { evt.preventDefault(); tab.click(); window.scrollTo({ top: 0, behavior: "smooth" }); }
    });
  });
})();
