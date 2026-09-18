/* Committee member — protocol review.
   - Conflict page: one shared <dialog> filled from the clicked row.
   - Deliberation thread: reply toggles, character counter, Ctrl/Cmd+Enter to post.
   - (Forms with data-confirm are handled by the dashboard's generic modal in script.js.)
   - Recommendations: open the accordion a #p<id> link points at. */
(function () {
  "use strict";

  /* ---- declaration dialog ---- */
  var dialog = document.getElementById("declareDialog");
  if (dialog && typeof dialog.showModal === "function") {
    var form = document.getElementById("declareForm");
    var template = form.getAttribute("data-action-template");

    document.querySelectorAll("[data-declare]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        form.action = template.replace(/\/0\//, "/" + btn.dataset.app + "/");
        document.getElementById("declareRef").textContent = btn.dataset.ref || "";
        document.getElementById("declareStudy").textContent = btn.dataset.title || "";
        document.getElementById("declareType").value = btn.dataset.type || "";
        document.getElementById("declareDesc").value = btn.dataset.desc || "";
        var wantsChair = btn.dataset.recuse === "0";
        form.querySelector("input[name=action][value=recuse]").checked = !wantsChair;
        form.querySelector("input[name=action][value=chair]").checked = wantsChair;
        dialog.showModal();
        document.getElementById("declareType").focus();
      });
    });

    dialog.querySelectorAll("[data-close-dialog]").forEach(function (b) {
      b.addEventListener("click", function () { dialog.close(); });
    });
    dialog.addEventListener("click", function (e) {
      if (e.target === dialog) dialog.close(); // click on the backdrop
    });
  }

  /* ---- thread: replies + counter ---- */
  document.querySelectorAll("[data-reply-toggle]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var f = document.getElementById(btn.getAttribute("data-reply-toggle"));
      if (!f) return;
      f.hidden = !f.hidden;
      if (!f.hidden) f.querySelector("textarea").focus();
    });
  });

  document.querySelectorAll("form textarea[name=body]").forEach(function (ta) {
    var counter = ta.form.querySelector("[data-count]");
    if (counter) {
      var update = function () { counter.textContent = ta.value.length + " / " + (ta.maxLength || 3000); };
      ta.addEventListener("input", update);
      update();
    }
    ta.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && ta.value.trim()) {
        e.preventDefault();
        ta.form.requestSubmit();
      }
    });
  });

  /* ---- recommendations: open the targeted accordion ---- */
  function openFromHash() {
    var id = window.location.hash.slice(1);
    var el = id && document.getElementById(id);
    if (el && el.tagName === "DETAILS") {
      el.open = true;
      el.scrollIntoView({ block: "start" });
    }
  }
  openFromHash();
  window.addEventListener("hashchange", openFromHash);
})();
