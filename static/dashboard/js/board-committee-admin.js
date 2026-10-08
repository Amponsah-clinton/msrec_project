// Wires a <select> (Tag / discipline, or Institution) up to its sibling
// "Please specify" row so picking "Other..." reveals a free-text input
// instead of submitting the literal "__other__" value. Shared by the Add
// and Edit modals.
function bcWireOther(form, selectSel, rowSel) {
  const select = form.querySelector(selectSel);
  const row = form.querySelector(rowSel);
  if (!select || !row) return;
  const sync = () => { row.hidden = select.value !== "__other__"; };
  select.addEventListener("change", sync);
  sync();
}

function bcWireTagOther(form) {
  bcWireOther(form, "[data-bc-tag-select]", "[data-bc-tag-other-row]");
  bcWireOther(form, "[data-bc-inst-select]", "[data-bc-inst-other-row]");
}

// Selects `value` in a dropdown that has an "Other..." escape hatch: an
// exact match is picked directly; anything else selects "Other" and drops
// the value into the companion free-text input, then shows/hides its row.
function bcFillSelectWithOther(select, other, row, value) {
  const v = value || "";
  const known = Array.from(select.options).some((opt) => opt.value === v && opt.value !== "__other__");
  if (v && !known) {
    select.value = "__other__";
    if (other) other.value = v;
  } else {
    select.value = v;
    if (other) other.value = "";
  }
  if (row) row.hidden = select.value !== "__other__";
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

        bcFillSelectWithOther(
          document.getElementById("bcEditInstitution"),
          document.getElementById("bcEditInstitutionOther"),
          document.getElementById("bcEditInstOtherRow"),
          row.dataset.institution,
        );
        bcFillSelectWithOther(
          document.getElementById("bcEditTag"),
          document.getElementById("bcEditTagOther"),
          document.getElementById("bcEditTagOtherRow"),
          row.dataset.tag,
        );

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
      // A reviewer who already has a Board/Committee/Secretariat card only
      // shows under the Reviewers tab, so "All" never lists anyone twice --
      // same rule as the public page, so the tab counts tally.
      const matchesTab = filter === "all"
        ? !row.hasAttribute("data-also-member")
        : row.dataset.filter === filter;
      const matchesSearch = !q || row.dataset.search.includes(q);
      row.hidden = !(matchesTab && matchesSearch);
    });
  }

  searchInput.addEventListener("input", applyFilters);
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });
});
