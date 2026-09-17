document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("financeSearch");
  const list = document.getElementById("financeList");
  const tabs = document.querySelector(".acct-tabs");

  // The date-range "Apply"/"Export CSV" form is a real GET submit (dates
  // and CSV export can't be done client-side against rows already in the
  // DOM) -- keep its hidden q/tab fields in sync with the live search box
  // and the (purely client-side, see script.js) active tab, so submitting
  // it or exporting still honours whatever's currently selected/typed.
  const filterForm = document.getElementById("financeFilterForm");
  const filterQ = document.getElementById("financeFilterQ");
  const filterTab = filterForm ? filterForm.querySelector('input[name="tab"]') : null;
  if (searchInput && filterForm && filterQ) {
    const syncQ = () => { filterQ.value = searchInput.value.trim(); };
    searchInput.addEventListener("input", syncQ);
    filterForm.addEventListener("submit", syncQ);
    syncQ();
  }
  if (filterTab && tabs) {
    tabs.querySelectorAll(".filter-tab[data-filter]").forEach((tab) => {
      tab.addEventListener("click", () => { filterTab.value = tab.dataset.filter; });
    });
  }

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
