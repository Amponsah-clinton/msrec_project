document.addEventListener("DOMContentLoaded", () => {

  /* ============================================================
     FAQ accordion (single-open)
  ============================================================ */
  document.querySelectorAll(".res-faq-question").forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = btn.closest(".res-faq-item");
      const wasActive = item.classList.contains("is-active");
      item.parentElement.querySelectorAll(".res-faq-item").forEach((el) => el.classList.remove("is-active"));
      if (!wasActive) item.classList.add("is-active");
    });
  });

  /* ============================================================
     Category nav — smooth scroll + scrollspy
  ============================================================ */
  const catLinks = Array.from(document.querySelectorAll(".res-cat-nav a"));
  const sections = catLinks.map((link) => document.getElementById(link.dataset.cat)).filter(Boolean);

  catLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const target = document.getElementById(link.dataset.cat);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + target.id);
    });
  });

  const SCROLLSPY_OFFSET = 210; // toolbar (sticky) + section scroll-margin-top
  function refreshActiveCat() {
    let activeId = sections[0] && sections[0].id;
    for (const s of sections) {
      if (s.getBoundingClientRect().top <= SCROLLSPY_OFFSET) activeId = s.id;
      else break;
    }
    catLinks.forEach((l) => l.classList.toggle("is-active", l.dataset.cat === activeId));
  }
  let spyTicking = false;
  window.addEventListener("scroll", () => {
    if (spyTicking) return;
    spyTicking = true;
    requestAnimationFrame(() => { refreshActiveCat(); spyTicking = false; });
  }, { passive: true });
  refreshActiveCat();

  /* ============================================================
     Live search — filters doc cards, training cards, and FAQ items
     by their data-search text; hides a whole section only when every
     item within it is filtered out.
  ============================================================ */
  const searchInput = document.getElementById("resSearch");
  const searchClear = document.getElementById("resSearchClear");
  const noResults = document.getElementById("resNoResults");
  const noResultsTerm = document.getElementById("resNoResultsTerm");

  const searchableItems = Array.from(document.querySelectorAll("[data-search]"));

  function runSearch() {
    const query = searchInput.value.trim().toLowerCase();
    searchClear.hidden = !query;

    let anyVisible = false;
    searchableItems.forEach((item) => {
      const matches = !query || item.dataset.search.toLowerCase().includes(query);
      item.classList.toggle("is-filtered-out", !matches);
      if (matches) anyVisible = true;
    });

    document.querySelectorAll(".res-section").forEach((section) => {
      const items = Array.from(section.querySelectorAll("[data-search]"));
      if (!items.length) return;
      const sectionHasMatch = items.some((item) => !item.classList.contains("is-filtered-out"));
      section.hidden = !!query && !sectionHasMatch;
    });

    noResults.hidden = !(query && !anyVisible);
    if (query && !anyVisible) noResultsTerm.textContent = '"' + searchInput.value.trim() + '"';
  }

  searchInput.addEventListener("input", runSearch);
  searchClear.addEventListener("click", () => {
    searchInput.value = "";
    runSearch();
    searchInput.focus();
  });
});
