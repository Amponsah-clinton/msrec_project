document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("financeSearch");
  const list = document.getElementById("financeList");
  const tabs = document.querySelector(".acct-tabs");
  if (!searchInput || !list || !tabs) return;

  const rows = Array.from(list.querySelectorAll("tbody tr[data-filter-item]"));
  if (!rows.length) return;

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
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });
});
