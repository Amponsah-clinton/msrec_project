document.addEventListener("DOMContentLoaded", () => {
  // Tabs, search, date range and pagination are all server-side (see
  // admin_dashboard.views.finance) -- the table only ever holds one page
  // of rows, so filtering it in the browser would search 20 rows, not the
  // full ledger. The topbar search box therefore just submits the GET
  // filter form (which also drops any ?page= so results start at page 1).
  const searchInput = document.getElementById("financeSearch");
  const filterForm = document.getElementById("financeFilterForm");
  const filterQ = document.getElementById("financeFilterQ");
  if (!searchInput || !filterForm || !filterQ) return;

  const submitSearch = () => {
    filterQ.value = searchInput.value.trim();
    filterForm.requestSubmit ? filterForm.requestSubmit() : filterForm.submit();
  };

  // Keep the hidden q in sync so Apply / Export CSV honour what's typed.
  searchInput.addEventListener("input", () => { filterQ.value = searchInput.value.trim(); });
  filterForm.addEventListener("submit", () => { filterQ.value = searchInput.value.trim(); });

  let timer = null;
  searchInput.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (searchInput.value.trim() !== (filterQ.dataset.applied || "")) submitSearch();
    }, 500);
  });
  searchInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); clearTimeout(timer); submitSearch(); }
  });
  filterQ.dataset.applied = filterQ.value;
});
