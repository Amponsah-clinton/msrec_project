/**
 * Site-wide search modal -- opened from the topbar's search icon.
 * Searches a static index of the public site's pages and named
 * sections (rendered server-side into #siteSearchIndex, so its URLs
 * always match {% url %}) and lists each match as a direct link.
 * Dashboard pages are never in that index -- they need a signed-in
 * session, so there is nowhere useful for a public visitor to land.
 */
(function () {
  "use strict";

  var toggle = document.getElementById("siteSearchToggle");
  var overlay = document.getElementById("siteSearchOverlay");
  var input = document.getElementById("siteSearchInput");
  var resultsEl = document.getElementById("siteSearchResults");
  var closeBtn = document.getElementById("siteSearchClose");
  var cancelBtn = document.getElementById("siteSearchCancel");
  var indexEl = document.getElementById("siteSearchIndex");
  if (!toggle || !overlay || !input || !resultsEl || !indexEl) return;

  var INDEX = [];
  try {
    INDEX = JSON.parse(indexEl.textContent);
  } catch (err) {
    INDEX = [];
  }

  var activeIndex = -1;

  function escapeHtml(value) {
    var div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }

  function highlight(text, query) {
    var idx = text.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return escapeHtml(text);
    return (
      escapeHtml(text.slice(0, idx)) +
      "<mark>" + escapeHtml(text.slice(idx, idx + query.length)) + "</mark>" +
      escapeHtml(text.slice(idx + query.length))
    );
  }

  function renderHint() {
    resultsEl.innerHTML = '<p class="site-search-hint"></p>';
    activeIndex = -1;
  }

  function renderResults(query, matches) {
    if (!matches.length) {
      resultsEl.innerHTML =
        '<p class="site-search-empty">No results for &ldquo;' + escapeHtml(query) + '&rdquo;. Try a different word.</p>';
      activeIndex = -1;
      return;
    }

    resultsEl.innerHTML = matches
      .map(function (item) {
        var q = query.trim();
        var titleHtml = item.title.toLowerCase().indexOf(q.toLowerCase()) !== -1
          ? highlight(item.title, q)
          : escapeHtml(item.title);
        return (
          '<a class="site-search-result" href="' + item.url + '">' +
            '<span class="site-search-result-icon"><i class="bi ' + (item.icon || "bi-file-text") + '"></i></span>' +
            '<span class="site-search-result-body">' +
              '<span class="site-search-result-title">' + titleHtml + "</span>" +
              '<span class="site-search-result-path">' + escapeHtml(item.breadcrumb || "") + "</span>" +
            "</span>" +
          "</a>"
        );
      })
      .join("");
    activeIndex = -1;
  }

  function runSearch(rawQuery) {
    var query = rawQuery.trim();
    if (!query) {
      renderHint();
      return;
    }
    var q = query.toLowerCase();
    var matches = INDEX.filter(function (item) {
      return (
        item.title.toLowerCase().indexOf(q) !== -1 ||
        (item.keywords || "").toLowerCase().indexOf(q) !== -1
      );
    }).slice(0, 12);
    renderResults(query, matches);
  }

  function setActive(nextIndex) {
    var items = resultsEl.querySelectorAll(".site-search-result");
    if (!items.length) return;
    items.forEach(function (el) { el.classList.remove("is-active"); });
    var wrapped = ((nextIndex % items.length) + items.length) % items.length;
    items[wrapped].classList.add("is-active");
    items[wrapped].scrollIntoView({ block: "nearest" });
    activeIndex = wrapped;
  }

  function open() {
    overlay.hidden = false;
    document.body.classList.add("site-search-open");
    input.value = "";
    renderHint();
    window.setTimeout(function () { input.focus(); }, 10);
  }

  function close() {
    overlay.hidden = true;
    document.body.classList.remove("site-search-open");
  }

  toggle.addEventListener("click", open);
  closeBtn.addEventListener("click", close);
  cancelBtn.addEventListener("click", close);

  overlay.addEventListener("click", function (event) {
    if (event.target === overlay) close();
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !overlay.hidden) {
      close();
      return;
    }
    // "/" opens search from anywhere on the page, as long as the
    // visitor isn't already typing into some other field.
    if (
      event.key === "/" &&
      overlay.hidden &&
      document.activeElement.tagName !== "INPUT" &&
      document.activeElement.tagName !== "TEXTAREA"
    ) {
      event.preventDefault();
      open();
    }
  });

  input.addEventListener("input", function () { runSearch(input.value); });

  input.addEventListener("keydown", function (event) {
    var items = resultsEl.querySelectorAll(".site-search-result");
    if (!items.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive(activeIndex + 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive(activeIndex - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      var target = items[activeIndex] || items[0];
      if (target) window.location.href = target.getAttribute("href");
    }
  });
})();
