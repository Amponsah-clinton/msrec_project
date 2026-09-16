document.addEventListener("DOMContentLoaded", () => {
  // ---------------- Generic modal open/close -- same [data-open-modal]/
  // [data-modal-overlay]/[data-modal-close] contract as
  // secretariat-applications.js / meetings.js, repeated here so this
  // page doesn't need to load either of those scripts just for its
  // modals. ----------------
  document.querySelectorAll("[data-open-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const overlay = document.getElementById(btn.dataset.openModal);
      if (overlay) overlay.hidden = false;
    });
  });
  document.querySelectorAll("[data-modal-overlay]").forEach((overlay) => {
    const close = () => { overlay.hidden = true; };
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close();
    });
    overlay.querySelectorAll("[data-modal-close]").forEach((btn) => btn.addEventListener("click", close));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("[data-modal-overlay]:not([hidden])").forEach((overlay) => { overlay.hidden = true; });
  });

  // ---------------- Membership / Appointments -- populate the Edit
  // modal from the row's data-* attributes. ----------------
  document.querySelectorAll("[data-apt-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".acct-row");
      if (!row) return;
      document.getElementById("aptEditAppointmentId").value = row.dataset.appointmentId;
      document.getElementById("aptEditMemberId").value = row.dataset.memberId;
      document.getElementById("aptEditSeatTitle").value = row.dataset.seatTitle;
      document.getElementById("aptEditAppointedBy").value = row.dataset.appointedBy;
      document.getElementById("aptEditStartDate").value = row.dataset.startDate;
      document.getElementById("aptEditEndDate").value = row.dataset.endDate;
      document.getElementById("aptEditStatus").value = row.dataset.status;
      document.getElementById("aptEditNotes").value = row.dataset.notes;
      const currentLetter = document.getElementById("aptEditCurrentLetter");
      if (currentLetter) currentLetter.hidden = row.dataset.letterUrl !== "1";
    });
  });

  // ---------------- Terms & Expiry -- same CommitteeAppointment fields,
  // its own edit modal (member reassignment is dropped -- this page is
  // about renewing/closing an existing term, not moving it to someone
  // else). ----------------
  document.querySelectorAll("[data-exp-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".acct-row");
      if (!row) return;
      document.getElementById("expEditAppointmentId").value = row.dataset.appointmentId;
      document.getElementById("expEditEndDate").value = row.dataset.endDate;
      document.getElementById("expEditStatus").value = row.dataset.status;
      document.getElementById("expEditNotes").value = row.dataset.notes;
    });
  });

  // ---------------- Training -- Edit modal. ----------------
  document.querySelectorAll("[data-trn-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".acct-row");
      if (!row) return;
      document.getElementById("trnEditRecordId").value = row.dataset.recordId;
      document.getElementById("trnEditMemberId").value = row.dataset.memberId;
      document.getElementById("trnEditCourseTitle").value = row.dataset.courseTitle;
      document.getElementById("trnEditProvider").value = row.dataset.provider;
      document.getElementById("trnEditCompletedDate").value = row.dataset.completedDate;
      document.getElementById("trnEditExpiryDate").value = row.dataset.expiryDate;
      document.getElementById("trnEditNotes").value = row.dataset.notes;
    });
  });

  // ---------------- Conflict Records -- Edit modal. ----------------
  document.querySelectorAll("[data-cnf-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const row = btn.closest(".acct-row");
      if (!row) return;
      document.getElementById("cnfEditRecordId").value = row.dataset.recordId;
      document.getElementById("cnfEditRelatedTo").value = row.dataset.relatedTo;
      document.getElementById("cnfEditDateDeclared").value = row.dataset.dateDeclared;
      document.getElementById("cnfEditDescription").value = row.dataset.description;
      document.getElementById("cnfEditStatus").value = row.dataset.status;
      document.getElementById("cnfEditResolutionNotes").value = row.dataset.resolutionNotes;
    });
  });

  // ---------------- Search + filter tabs (same generic
  // [data-filters-target]/[data-filter-item] contract as script.js's
  // filter-tabs handler, layered with a text search the same way
  // board-committee-admin.js does it). ----------------
  document.querySelectorAll("[data-cmt-search]").forEach((searchInput) => {
    const list = document.querySelector(searchInput.dataset.cmtSearch);
    if (!list) return;
    const tabs = list.closest(".panel")?.querySelector(".filter-tabs");
    const rows = Array.from(list.querySelectorAll("[data-filter-item]"));

    function currentFilter() {
      const active = tabs?.querySelector(".filter-tab.active");
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
    tabs?.querySelectorAll(".filter-tab").forEach((tab) => tab.addEventListener("click", applyFilters));
  });
});
