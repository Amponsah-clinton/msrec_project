document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("accountsSearch");
  const list = document.getElementById("acctList");
  const tabs = document.querySelector(".acct-tabs");

  // Confirmation before suspend/reactivate/delete is handled by the
  // generic data-confirm modal in script.js (any form on the page with a
  // data-confirm attribute gets intercepted there) -- nothing to wire up
  // here.

  const editOverlay = document.getElementById("acctEditOverlay");
  const editForm = document.getElementById("acctEditForm");
  if (editOverlay && editForm) {
    const closeEdit = () => { editOverlay.hidden = true; };

    document.querySelectorAll("[data-acct-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const row = btn.closest(".acct-row");
        if (!row) return;
        document.getElementById("editUserId").value = row.dataset.userId;
        document.getElementById("editFirstName").value = row.dataset.firstName;
        document.getElementById("editMiddleName").value = row.dataset.middleName;
        document.getElementById("editLastName").value = row.dataset.lastName;
        document.getElementById("editEmail").value = row.dataset.email;
        document.getElementById("editPhone").value = row.dataset.phone;
        document.getElementById("editInstitution").value = row.dataset.institution;
        document.getElementById("editDepartment").value = row.dataset.department;
        document.getElementById("editPosition").value = row.dataset.position;
        const roleField = document.getElementById("editRole");
        roleField.value = row.dataset.role;
        roleField.disabled = row.dataset.isSuperuser === "1";
        editOverlay.hidden = false;
      });
    });

    document.getElementById("acctEditClose").addEventListener("click", closeEdit);
    document.getElementById("acctEditCancel").addEventListener("click", closeEdit);
    editOverlay.addEventListener("click", (event) => {
      if (event.target === editOverlay) closeEdit();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !editOverlay.hidden) closeEdit();
    });
  }

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
