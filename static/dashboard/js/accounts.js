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
        document.getElementById("editConfirmEmail").value = row.dataset.email;
        document.getElementById("editEmailMatchError").hidden = true;
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

    const editEmail = document.getElementById("editEmail");
    const editConfirmEmail = document.getElementById("editConfirmEmail");
    const editEmailMatchError = document.getElementById("editEmailMatchError");
    [editEmail, editConfirmEmail].forEach((f) => {
      f.addEventListener("input", () => { editEmailMatchError.hidden = true; });
    });
    editForm.addEventListener("submit", (event) => {
      if (editEmail.value.trim().toLowerCase() !== editConfirmEmail.value.trim().toLowerCase()) {
        event.preventDefault();
        editEmailMatchError.hidden = false;
        editConfirmEmail.focus();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !editOverlay.hidden) closeEdit();
    });
  }

  // Suspend / ban dialog (templates/dashboards/_suspend_modal.html). While
  // the reason is typed, the server lays out the real letter and reports
  // whether it still fits on one A4 page (admin_dashboard.views.
  // suspension_letter_fit), so the reason can be trimmed before sending.
  const suspendOverlay = document.getElementById("acctSuspendOverlay");
  const suspendForm = document.getElementById("acctSuspendForm");
  if (suspendOverlay && suspendForm) {
    const reason = document.getElementById("suspendReason");
    const count = document.getElementById("suspendCount");
    const fit = document.getElementById("suspendFit");
    const title = document.getElementById("acctSuspendTitle");
    const submit = document.getElementById("suspendSubmit");
    const max = parseInt(reason.getAttribute("maxlength"), 10) || 1500;
    let timer = null;
    let request = 0;

    const setFit = (state, text) => { fit.dataset.state = state; fit.textContent = text; };
    const kind = () => (suspendForm.querySelector('input[name="suspension_kind"]:checked') || {}).value || "suspend";

    function syncKind() {
      const ban = kind() === "ban";
      title.textContent = ban ? "Ban account" : "Suspend account";
      submit.textContent = ban ? "Ban & send letter" : "Suspend & send letter";
      suspendForm.querySelectorAll(".acct-kind-opt").forEach((opt) => {
        opt.classList.toggle("is-checked", opt.querySelector("input").checked);
      });
    }

    function checkFit() {
      clearTimeout(timer);
      const length = reason.value.length;
      count.textContent = `${length} / ${max}`;
      count.classList.toggle("is-near", length > max * 0.9);
      if (!reason.value.trim()) {
        setFit("idle", "Type the reason to check how it fits on the letter.");
        return;
      }
      setFit("busy", "Checking the fit on A4…");
      timer = setTimeout(async () => {
        const mine = ++request;
        try {
          const response = await fetch(suspendForm.dataset.fitUrl, {
            method: "POST", body: new FormData(suspendForm), credentials: "same-origin",
          });
          if (!response.ok) throw new Error(response.status);
          const data = await response.json();
          if (mine !== request) return;
          if (data.pages > 1) {
            setFit("over", `Too long for one page — the letter will run onto page ${data.pages}. Shorten the reason to keep it on one A4 sheet.`);
          } else if (data.scale < 1) {
            setFit("tight", "Fits on one A4 page (the text is set slightly smaller to fit).");
          } else {
            setFit("ok", "Fits on one A4 page.");
          }
        } catch (err) {
          if (mine === request) setFit("idle", "Couldn't check the fit right now — use Preview letter.");
        }
      }, 650);
    }

    const closeSuspend = () => { suspendOverlay.hidden = true; clearTimeout(timer); request++; };

    document.querySelectorAll("[data-acct-suspend]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const row = btn.closest(".acct-row");
        if (!row) return;
        suspendForm.reset();
        document.getElementById("suspendUserId").value = row.dataset.userId;
        document.getElementById("suspendWho").textContent = row.dataset.fullName;
        document.getElementById("suspendEmail").textContent = row.dataset.email;
        syncKind();
        checkFit();
        suspendOverlay.hidden = false;
        reason.focus();
      });
    });

    suspendForm.querySelectorAll('input[name="suspension_kind"]').forEach((radio) => {
      radio.addEventListener("change", () => { syncKind(); checkFit(); });
    });
    reason.addEventListener("input", checkFit);
    suspendForm.addEventListener("submit", (event) => {
      // Preview (formtarget=_blank) doesn't need a reason; the real submit does.
      if (event.submitter === submit && !reason.value.trim()) {
        event.preventDefault();
        reason.focus();
        setFit("over", "A reason is required — it's printed on the letter.");
      }
    });
    document.getElementById("acctSuspendClose").addEventListener("click", closeSuspend);
    document.getElementById("acctSuspendCancel").addEventListener("click", closeSuspend);
    suspendOverlay.addEventListener("click", (event) => {
      if (event.target === suspendOverlay) closeSuspend();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !suspendOverlay.hidden) closeSuspend();
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
