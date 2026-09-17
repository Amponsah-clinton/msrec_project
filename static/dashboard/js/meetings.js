document.addEventListener("DOMContentLoaded", () => {
  // Generic modal open/close -- same [data-open-modal]/[data-modal-overlay]
  // contract as secretariat-applications.js, repeated here so this page
  // doesn't need that page's script just for its modals.
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

  // Schedule form -- add/remove agenda item rows.
  const agendaBuilder = document.getElementById("agendaBuilder");
  if (agendaBuilder) {
    const addRow = () => {
      const row = document.createElement("div");
      row.className = "agenda-row";
      row.innerHTML = `
        <input class="field-input" name="agenda_title" placeholder="Agenda item title">
        <input class="field-input" name="agenda_presenter" placeholder="Presenter">
        <input class="field-input" name="agenda_duration" type="number" min="1" value="10">
        <button type="button" class="remove-row" aria-label="Remove item">&times;</button>`;
      agendaBuilder.insertBefore(row, agendaBuilder.querySelector(".add-row-btn"));
    };
    document.getElementById("addAgendaRow")?.addEventListener("click", addRow);
    agendaBuilder.addEventListener("click", (event) => {
      if (event.target.classList.contains("remove-row")) {
        event.target.closest(".agenda-row").remove();
      }
    });
  }

  // Participant checklist -- live filter + selected counter.
  const participantSearch = document.getElementById("participantSearch");
  const checklist = document.getElementById("participantChecklist");
  if (participantSearch && checklist) {
    participantSearch.addEventListener("input", () => {
      const term = participantSearch.value.trim().toLowerCase();
      checklist.querySelectorAll(".participant-check-row").forEach((row) => {
        row.style.display = row.dataset.name.includes(term) ? "" : "none";
      });
    });
  }
  const updateSelectedCount = () => {
    const counter = document.getElementById("participantCount");
    if (!counter || !checklist) return;
    counter.textContent = checklist.querySelectorAll("input[type=checkbox]:checked").length;
  };
  checklist?.addEventListener("change", updateSelectedCount);
  updateSelectedCount();

  // Mode toggle on the schedule form -- show/hide location vs link fields.
  const modeSelect = document.getElementById("meetingMode");
  const locationField = document.getElementById("locationField");
  const linkField = document.getElementById("linkField");
  const syncModeFields = () => {
    if (!modeSelect) return;
    const mode = modeSelect.value;
    if (locationField) locationField.style.display = mode === "virtual" ? "none" : "";
    if (linkField) linkField.style.display = mode === "in_person" ? "none" : "";
  };
  modeSelect?.addEventListener("change", syncModeFields);
  syncModeFields();

  // Quorum ring -- animate stroke-dashoffset from data attributes.
  document.querySelectorAll(".quorum-ring .fill").forEach((circle) => {
    const pct = parseFloat(circle.dataset.pct || "0");
    const radius = circle.r.baseVal.value;
    const circumference = 2 * Math.PI * radius;
    circle.style.strokeDasharray = `${circumference}`;
    circle.style.strokeDashoffset = `${circumference}`;
    requestAnimationFrame(() => {
      circle.style.strokeDashoffset = `${circumference * (1 - Math.min(pct, 100) / 100)}`;
    });
  });
});
