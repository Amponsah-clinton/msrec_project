/* Site Settings > Legal Pages: the Terms of Service / Privacy Policy editor
   (templates/dashboards/admin/settings.html, #legal-pages).

   Switches between the two pages, and runs each page's section list: add,
   remove, move up / down, collapse, and keep the numbers and card titles
   in step with what's typed. The sections are plain form fields in display
   order, so whatever order they're in when Save is pressed is the order the
   public page shows (admin_dashboard.views._handle_settings_legal_page). */
(function () {
  "use strict";

  var root = document.getElementById("legal-pages");
  if (!root) return;

  // ---- which page is being edited ----
  var switches = root.querySelectorAll(".lp-switch-btn");
  var pages = root.querySelectorAll("[data-lp-page]");
  function showPage(slug) {
    Array.prototype.forEach.call(switches, function (b) {
      var on = b.getAttribute("data-lp") === slug;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    Array.prototype.forEach.call(pages, function (p) {
      p.hidden = p.getAttribute("data-lp-page") !== slug;
    });
    try { sessionStorage.setItem("lpPage", slug); } catch (e) {}
  }
  Array.prototype.forEach.call(switches, function (b) {
    b.addEventListener("click", function () { showPage(b.getAttribute("data-lp")); });
  });
  // Come back to the page that was just saved.
  try {
    var last = sessionStorage.getItem("lpPage");
    if (last && root.querySelector('[data-lp-page="' + last + '"]')) showPage(last);
  } catch (e) {}

  var template = document.getElementById("lpSectionTemplate");

  function setOpen(sec, open) {
    var fields = sec.querySelector(".lp-sec-fields");
    var toggle = sec.querySelector("[data-lp-toggle]");
    fields.hidden = !open;
    sec.classList.toggle("is-open", open);
    if (toggle) toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function renumber(list) {
    var secs = list.querySelectorAll("[data-lp-sec]");
    Array.prototype.forEach.call(secs, function (sec, i) {
      var num = sec.querySelector("[data-lp-num]");
      if (num) num.textContent = (i + 1 < 10 ? "0" : "") + (i + 1);
      var up = sec.querySelector("[data-lp-up]");
      var down = sec.querySelector("[data-lp-down]");
      if (up) up.disabled = i === 0;
      if (down) down.disabled = i === secs.length - 1;
    });
    var count = list.closest(".lp-card").querySelector("[data-lp-count]");
    if (count) count.textContent = secs.length;
  }

  Array.prototype.forEach.call(root.querySelectorAll(".lp-form"), function (form) {
    var list = form.querySelector("[data-lp-sections]");
    var dirty = false;
    renumber(list);

    form.addEventListener("input", function (e) {
      dirty = true;
      // The collapsed card's title follows its Heading field.
      if (e.target.hasAttribute("data-lp-heading")) {
        var title = e.target.closest("[data-lp-sec]").querySelector("[data-lp-title]");
        title.textContent = e.target.value.trim() || "Untitled section";
      }
    });
    form.addEventListener("submit", function () { dirty = false; });
    window.addEventListener("beforeunload", function (e) {
      if (!dirty) return;
      e.preventDefault();
      e.returnValue = "";
    });

    list.addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      var sec = btn.closest("[data-lp-sec]");
      if (!sec) return;
      if (btn.hasAttribute("data-lp-toggle")) {
        setOpen(sec, sec.querySelector(".lp-sec-fields").hidden);
      } else if (btn.hasAttribute("data-lp-up") && sec.previousElementSibling) {
        list.insertBefore(sec, sec.previousElementSibling);
        dirty = true;
      } else if (btn.hasAttribute("data-lp-down") && sec.nextElementSibling) {
        list.insertBefore(sec.nextElementSibling, sec);
        dirty = true;
      } else if (btn.hasAttribute("data-lp-remove")) {
        var heading = sec.querySelector("[data-lp-heading]").value.trim();
        if (!window.confirm("Remove " + (heading ? "“" + heading + "”" : "this section") + "? It's gone from the page once you save.")) return;
        sec.remove();
        dirty = true;
      } else {
        return;
      }
      renumber(list);
      if (btn.isConnected) btn.focus();
    });

    // Clicking a collapsed card's title opens it.
    list.addEventListener("click", function (e) {
      var bar = e.target.closest(".lp-sec-bar");
      if (!bar || e.target.closest("button")) return;
      var sec = bar.closest("[data-lp-sec]");
      setOpen(sec, sec.querySelector(".lp-sec-fields").hidden);
    });

    var add = form.querySelector("[data-lp-add]");
    if (add && template) add.addEventListener("click", function () {
      var node = template.content.firstElementChild.cloneNode(true);
      list.appendChild(node);
      renumber(list);
      dirty = true;
      setOpen(node, true);
      node.scrollIntoView({ behavior: "smooth", block: "center" });
      var h = node.querySelector("[data-lp-heading]");
      setTimeout(function () { h.focus(); }, 250);
    });

    var expand = form.querySelector("[data-lp-expand]");
    if (expand) expand.addEventListener("click", function () {
      var secs = list.querySelectorAll("[data-lp-sec]");
      var anyClosed = Array.prototype.some.call(secs, function (s) { return s.querySelector(".lp-sec-fields").hidden; });
      Array.prototype.forEach.call(secs, function (s) { setOpen(s, anyClosed); });
      expand.textContent = anyClosed ? "Collapse all" : "Expand all";
    });
  });
})();
