document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("resAdminSearch");
  const list = document.getElementById("resAdminList");
  const tabs = document.querySelector(".acct-tabs");

  // ---------------- Add Resource modal ----------------
  const addOverlay = document.getElementById("resAddOverlay");
  const addOpen = document.getElementById("resAddOpen");
  if (addOverlay && addOpen) {
    const closeAdd = () => { addOverlay.hidden = true; };
    addOpen.addEventListener("click", () => { addOverlay.hidden = false; });
    document.getElementById("resAddClose").addEventListener("click", closeAdd);
    document.getElementById("resAddCancel").addEventListener("click", closeAdd);
    addOverlay.addEventListener("click", (event) => {
      if (event.target === addOverlay) closeAdd();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !addOverlay.hidden) closeAdd();
    });
  }

  // ---------------- Search (composes with the dashboard-wide filter-tabs
  // handler in script.js, same pattern as board-committee-admin.js) ----------------
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
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });
});
