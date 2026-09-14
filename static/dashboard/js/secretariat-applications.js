document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("secAppsSearch");
  const list = document.getElementById("secAppsList");
  const tabs = document.querySelector(".acct-tabs");
  if (!searchInput || !list || !tabs) return;

  const rows = Array.from(list.querySelectorAll("[data-filter-item]"));

  // The server only renders "No applications yet" when there are zero
  // applications at all (Django's {% empty %} on the full list) -- without
  // this, picking a tab/search that happens to match none of the rows
  // that DO exist would just show a blank list with no explanation.
  let noMatchesEl = null;
  if (rows.length) {
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
    rows.forEach((row) => {
      const matchesTab = filter === "all" || row.dataset.filter === filter;
      const matchesSearch = !q || row.dataset.search.includes(q);
      const visible = matchesTab && matchesSearch;
      row.hidden = !visible;
      if (visible) anyVisible = true;
    });
    if (noMatchesEl) noMatchesEl.hidden = anyVisible;
  }

  searchInput.addEventListener("input", applyFilters);
  // The dashboard-wide filter-tabs handler (dashboard/js/script.js) already
  // toggles each row's `hidden` by tab on click, registered before this
  // file loads. Re-applying the search filter right after lets the two
  // compose instead of the tab click wiping out whatever was typed.
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });
});
