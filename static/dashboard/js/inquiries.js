document.addEventListener("DOMContentLoaded", () => {
  const shell = document.getElementById("inqShell");
  if (!shell) return;

  const list = document.getElementById("inqList");
  const rows = Array.from(list.querySelectorAll(".message-row"));
  const panels = Array.from(shell.querySelectorAll(".thread-panel[data-thread]"));
  const searchInput = document.getElementById("inquirySearch");
  const tabs = shell.querySelector(".inq-tabs");

  // Confirmation before deleting an inquiry is handled by the generic
  // data-confirm modal in script.js.

  // `openOnMobile` only matters below the two-pane breakpoint (see
  // .messages-shell.thread-open in style.css) -- on desktop both panes are
  // always visible, so highlighting a row and swapping the active panel is
  // enough either way.
  function selectThread(id, { openOnMobile = false } = {}) {
    if (!id) return;
    rows.forEach((row) => row.classList.toggle("active", row.dataset.thread === id));
    panels.forEach((panel) => panel.classList.toggle("is-active", panel.dataset.thread === id));
    if (openOnMobile) shell.classList.add("thread-open");
  }

  rows.forEach((row) => {
    row.addEventListener("click", () => selectThread(row.dataset.thread, { openOnMobile: true }));
  });

  panels.forEach((panel) => {
    const backBtn = panel.querySelector(".thread-back-btn");
    if (backBtn) backBtn.addEventListener("click", () => shell.classList.remove("thread-open"));
  });

  function selectFirstVisible() {
    const first = rows.find((row) => !row.hidden);
    if (first) selectThread(first.dataset.thread);
  }

  // Land on whichever inquiry a redirect after reply/resolve/reopen/delete
  // asked for (?selected=<id>, set by the forms in each thread panel) --
  // reopened on mobile too, since the admin was just acting on it. With no
  // such hint, keep whatever the server already marked is-active (the most
  // recent inquiry) and just sync the list row's highlight to match.
  const params = new URLSearchParams(window.location.search);
  const requested = params.get("selected");
  if (requested && rows.some((row) => row.dataset.thread === requested)) {
    selectThread(requested, { openOnMobile: true });
  } else {
    const activePanel = panels.find((panel) => panel.classList.contains("is-active"));
    if (activePanel) selectThread(activePanel.dataset.thread);
    else selectFirstVisible();
  }

  if (!searchInput || !tabs) return;

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
    // If the currently-open thread just got filtered out, fall back to the
    // first row that's still visible instead of showing an orphaned thread.
    const activeRow = rows.find((row) => row.classList.contains("active"));
    if (!activeRow || activeRow.hidden) selectFirstVisible();
  }

  searchInput.addEventListener("input", applyFilters);
  // The generic filter-tabs handler (dashboard/js/script.js) already toggles
  // each row's `hidden` by tab on click, registered before this file loads.
  // Re-applying the search filter right after lets the two compose instead
  // of the tab click wiping out whatever was typed in the box.
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });
});
