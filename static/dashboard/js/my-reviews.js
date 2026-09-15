document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("myReviewsSearch");
  const list = document.getElementById("myReviewsList");
  const tabs = document.querySelector(".acct-tabs");
  if (!searchInput || !list || !tabs) return;

  const cards = Array.from(list.querySelectorAll("[data-filter-item]"));

  let noMatchesEl = null;
  if (cards.length) {
    noMatchesEl = document.createElement("div");
    noMatchesEl.className = "empty-state";
    noMatchesEl.hidden = true;
    noMatchesEl.innerHTML = `
      <span class="empty-icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg></span>
      <h3>No matches</h3>
      <p>Nothing in this view matches the current tab/search. Try "All" or clear the search box.</p>
    `;
    list.appendChild(noMatchesEl);
  }

  function currentFilter() {
    const active = tabs.querySelector(".filter-tab.active");
    return active ? active.dataset.filter : "all";
  }

  function applyFilters() {
    const q = searchInput.value.trim().toLowerCase();
    const filter = currentFilter();
    let anyVisible = false;
    cards.forEach((card) => {
      const matchesTab = filter === "all" || card.dataset.filter === filter;
      const matchesSearch = !q || card.dataset.search.includes(q);
      const visible = matchesTab && matchesSearch;
      card.hidden = !visible;
      if (visible) anyVisible = true;
    });
    if (noMatchesEl) noMatchesEl.hidden = anyVisible;
  }

  searchInput.addEventListener("input", applyFilters);
  // The dashboard-wide filter-tabs handler (dashboard/js/script.js) already
  // toggles each card's `hidden` by tab on click, registered before this
  // file loads. Re-applying the search filter right after lets the two
  // compose instead of the tab click wiping out whatever was typed.
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });
});
