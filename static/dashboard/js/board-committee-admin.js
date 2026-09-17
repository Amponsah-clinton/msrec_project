// Wires a Tag / discipline <select data-bc-tag-select> up to its sibling
// "Please specify" row (data-bc-tag-other-row / data-bc-tag-other) --
// shared by both the Add and Edit modals so picking "Other..." reveals a
// free-text input instead of submitting the literal "__other__" value.
function bcWireTagOther(form) {
  const select = form.querySelector("[data-bc-tag-select]");
  const row = form.querySelector("[data-bc-tag-other-row]");
  const other = form.querySelector("[data-bc-tag-other]");
  if (!select || !row || !other) return;
  const sync = () => { row.hidden = select.value !== "__other__"; };
  select.addEventListener("change", sync);
  sync();
}

document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("bcAdminSearch");
  const list = document.getElementById("bcAdminList");
  const tabs = document.querySelector(".acct-tabs");

  document.getElementById("bcAddForm") && bcWireTagOther(document.getElementById("bcAddForm"));
  document.getElementById("bcEditForm") && bcWireTagOther(document.getElementById("bcEditForm"));

  // ---------------- Add Member modal ----------------
  const addOverlay = document.getElementById("bcAddOverlay");
  const addOpen = document.getElementById("bcAddOpen");
  if (addOverlay && addOpen) {
    const closeAdd = () => { addOverlay.hidden = true; };
    addOpen.addEventListener("click", () => { addOverlay.hidden = false; });
    document.getElementById("bcAddClose").addEventListener("click", closeAdd);
    document.getElementById("bcAddCancel").addEventListener("click", closeAdd);
    addOverlay.addEventListener("click", (event) => {
      if (event.target === addOverlay) closeAdd();
    });
  }

  // ---------------- Edit Member modal ----------------
  const editOverlay = document.getElementById("bcEditOverlay");
  const editForm = document.getElementById("bcEditForm");
  if (editOverlay && editForm) {
    const closeEdit = () => { editOverlay.hidden = true; };
    const currentPhotoWrap = document.getElementById("bcEditCurrentPhoto");
    const currentPhotoImg = document.getElementById("bcEditCurrentPhotoImg");

    document.querySelectorAll("[data-bc-edit]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const row = btn.closest(".acct-row");
        if (!row) return;
        document.getElementById("bcEditMemberId").value = row.dataset.memberId;
        document.getElementById("bcEditFullName").value = row.dataset.fullName;
        document.getElementById("bcEditTitle").value = row.dataset.title || "";
        document.getElementById("bcEditRoleTitle").value = row.dataset.roleTitle;
        document.getElementById("bcEditGroup").value = row.dataset.group;
        document.getElementById("bcEditDisplayOrder").value = row.dataset.displayOrder;
        document.getElementById("bcEditIsActive").checked = row.dataset.isActive === "1";

        const tagSelect = document.getElementById("bcEditTag");
        const tagOther = document.getElementById("bcEditTagOther");
        const tagValue = row.dataset.tag || "";
        const knownTag = Array.from(tagSelect.options).some((opt) => opt.value === tagValue);
        if (tagValue && !knownTag) {
          tagSelect.value = "__other__";
          tagOther.value = tagValue;
        } else {
          tagSelect.value = tagValue;
          tagOther.value = "";
        }
        document.getElementById("bcEditTagOtherRow").hidden = tagSelect.value !== "__other__";

        if (row.dataset.photoUrl) {
          currentPhotoImg.src = row.dataset.photoUrl;
          currentPhotoWrap.hidden = false;
        } else {
          currentPhotoWrap.hidden = true;
        }

        editOverlay.hidden = false;
      });
    });

    document.getElementById("bcEditClose").addEventListener("click", closeEdit);
    document.getElementById("bcEditCancel").addEventListener("click", closeEdit);
    editOverlay.addEventListener("click", (event) => {
      if (event.target === editOverlay) closeEdit();
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (addOverlay && !addOverlay.hidden) addOverlay.hidden = true;
    if (editOverlay && !editOverlay.hidden) editOverlay.hidden = true;
  });

  // ---------------- Search (composes with the dashboard-wide filter-tabs
  // handler in script.js, same pattern as accounts.js) ----------------
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
