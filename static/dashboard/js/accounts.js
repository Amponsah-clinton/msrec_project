document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("accountsSearch");
  const list = document.getElementById("acctList");
  const tabs = document.querySelector(".acct-tabs");
  if (!searchInput || !list || !tabs) return;

  const rows = Array.from(list.querySelectorAll(".acct-row"));

  function currentFilter() {
    const active = tabs.querySelector(".filter-tab.active");
    return active ? active.dataset.filter : "all";
  }

  function applyFilters() {
    const q = searchInput.value.trim().toLowerCase();
    const filter = currentFilter();
    rows.forEach((row) => {
      const matchesTab = filter === "all" || row.dataset.filter === filter;
      const matchesSearch = !q || row.dataset.search.includes(q);
      row.hidden = !(matchesTab && matchesSearch);
    });
  }

  searchInput.addEventListener("input", applyFilters);

  // The dashboard-wide filter-tabs handler (dashboard/js/script.js) already
  // toggles each row's `hidden` by tab on click, registered before this file
  // loads. Re-applying the search filter right after lets the two compose
  // instead of the tab click wiping out whatever was typed in the box.
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });
});
