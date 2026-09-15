document.addEventListener("DOMContentLoaded", () => {
  // Three real panels (Assign Reviewer / Pending Assignments / Reviewer
  // Workload), not a filtered list -- script.js's generic filter-tabs
  // handler still toggles `.active` on these buttons (harmless), but
  // showing/hiding the actual panel is this page's own job.
  const tabs = document.querySelectorAll("[data-ra-tab]");
  const panels = document.querySelectorAll("[data-ra-panel]");
  if (tabs.length && panels.length) {
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.raTab;
        panels.forEach((panel) => {
          panel.hidden = panel.dataset.raPanel !== target;
        });
      });
    });
  }

  /* ============================================================
     Choose Reviewer modal -- one shared overlay for every "Assign
     Reviewer" card. Opening it remembers which card's form triggered
     it; picking a reviewer writes into that specific form's hidden
     reviewer_id input and closes the modal, rather than each card
     needing its own copy of the whole reviewer list.
  ============================================================ */
  const overlay = document.getElementById("reviewerModalOverlay");
  const openButtons = document.querySelectorAll("[data-open-reviewer-modal]");
  if (overlay && openButtons.length) {
    const searchInput = document.getElementById("reviewerModalSearch");
    const tabsWrap = document.getElementById("reviewerModalTabs");
    const list = document.getElementById("reviewerModalList");
    const noMatches = document.getElementById("reviewerModalNoMatches");
    const cards = Array.from(list.querySelectorAll(".reviewer-pick-card"));
    const closeBtn = document.getElementById("reviewerModalClose");

    let activeTriggerBtn = null;

    function currentAvailabilityFilter() {
      const active = tabsWrap.querySelector(".filter-tab.active");
      return active ? active.dataset.availability : "all";
    }

    function applyModalFilters() {
      const q = searchInput.value.trim().toLowerCase();
      const availability = currentAvailabilityFilter();
      let anyVisible = false;
      cards.forEach((card) => {
        const matchesAvailability = availability === "all" || card.dataset.availability === availability;
        const matchesSearch = !q || card.dataset.search.includes(q);
        const visible = matchesAvailability && matchesSearch;
        card.hidden = !visible;
        if (visible) anyVisible = true;
      });
      if (noMatches) noMatches.hidden = anyVisible;
    }

    function openModal(triggerBtn) {
      activeTriggerBtn = triggerBtn;
      overlay.hidden = false;
      searchInput.value = "";
      tabsWrap.querySelectorAll(".filter-tab").forEach((t) => t.classList.remove("active"));
      tabsWrap.querySelector('[data-availability="all"]').classList.add("active");
      applyModalFilters();
      searchInput.focus();
    }

    function closeModal() {
      overlay.hidden = true;
      activeTriggerBtn = null;
    }

    openButtons.forEach((btn) => {
      btn.addEventListener("click", () => openModal(btn));
    });

    closeBtn.addEventListener("click", closeModal);
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) closeModal();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !overlay.hidden) closeModal();
    });

    searchInput.addEventListener("input", applyModalFilters);
    tabsWrap.querySelectorAll(".filter-tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        tabsWrap.querySelectorAll(".filter-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        applyModalFilters();
      });
    });

    cards.forEach((card) => {
      card.addEventListener("click", () => {
        if (!activeTriggerBtn) return;
        const form = activeTriggerBtn.closest("[data-assign-form]");
        const hiddenInput = form.querySelector(".reviewer-id-input");
        const textEl = activeTriggerBtn.querySelector(".choose-reviewer-text");
        const avatarEl = activeTriggerBtn.querySelector(".choose-reviewer-avatar");
        const name = card.dataset.reviewerName;

        hiddenInput.value = card.dataset.reviewerId;
        textEl.textContent = name;
        activeTriggerBtn.classList.add("has-value");
        if (avatarEl) {
          avatarEl.hidden = false;
          avatarEl.textContent = name
            .split(" ")
            .filter(Boolean)
            .slice(0, 2)
            .map((part) => part[0])
            .join("")
            .toUpperCase();
        }
        closeModal();
      });
    });

    // A hidden required input isn't reliably validated/focusable across
    // browsers, so the "you must pick someone" check happens here instead.
    document.querySelectorAll("[data-assign-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        const hiddenInput = form.querySelector(".reviewer-id-input");
        if (!hiddenInput.value) {
          event.preventDefault();
          const chooseBtn = form.querySelector("[data-open-reviewer-modal]");
          openModal(chooseBtn);
        }
      });
    });
  }
});
