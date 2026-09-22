document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("secAppsSearch");
  const list = document.getElementById("secAppsList");
  const tabs = document.querySelector(".acct-tabs");
  if (!searchInput || !list || !tabs) return;

  const rows = Array.from(list.querySelectorAll("[data-filter-item]"));

  // The server only renders "No applications yet" when there are zero
  // applications at all (Django's {% empty %} on the full list) -- without
  // this, picking a tab/search that happens to match none of the rows
  // that DO exist would just show a blank list with no explanation.
  let noMatchesEl = null;
  if (rows.length) {
    noMatchesEl = document.createElement("div");
    noMatchesEl.className = "empty-state";
    noMatchesEl.hidden = true;
    noMatchesEl.innerHTML = `
      <span class="empty-icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg></span>
      <h3>No matches</h3>
      <p>Nothing in this view matches the current tab/search. Try "All" or clear the search box.</p>
    `;
    list.appendChild(noMatchesEl);
  }

  function currentFilter() {
    const active = tabs.querySelector(".filter-tab.active");
    return active ? active.dataset.filter : "all";
  }

  function applyFilters() {
    const q = searchInput.value.trim().toLowerCase();
    const filter = currentFilter();
    let anyVisible = false;
    rows.forEach((row) => {
      // A card's data-filter can hold several space-separated tags (its
      // current-status tab, plus "revised" if it's ever been resubmitted)
      // -- see script.js's generic filter-tabs handler for why an exact
      // match here would silently hide every resubmitted card whose
      // status tab isn't literally "revised".
      const tags = (row.dataset.filter || "").split(" ");
      const matchesTab = filter === "all" || tags.includes(filter);
      const matchesSearch = !q || row.dataset.search.includes(q);
      const visible = matchesTab && matchesSearch;
      row.hidden = !visible;
      if (visible) anyVisible = true;
    });
    if (noMatchesEl) noMatchesEl.hidden = anyVisible;
  }

  // A term handed over from another page's search box (the Dashboard's
  // topbar posts here as ?q=) lands in the box and is applied on load, so
  // arriving from that search shows the filtered list with the term still
  // visible and editable rather than the unfiltered one.
  const handedOver = new URLSearchParams(window.location.search).get("q");
  if (handedOver) {
    searchInput.value = handedOver;
    applyFilters();
  }

  searchInput.addEventListener("input", applyFilters);
  // The dashboard-wide filter-tabs handler (dashboard/js/script.js) already
  // toggles each row's `hidden` by tab on click, registered before this
  // file loads. Re-applying the search filter right after lets the two
  // compose instead of the tab click wiping out whatever was typed.
  tabs.querySelectorAll(".filter-tab").forEach((tab) => {
    tab.addEventListener("click", applyFilters);
  });

  // Cards are plain <div>s (not <a>s) now -- a real "View Application"
  // link and a "Reviewer & Stage" button both live inside one, and a
  // <button> can't nest inside an <a>. Clicking anywhere else on the
  // card still navigates, same feel as before; clicking the button (or
  // anything inside its modal, which sits *outside* the card in the DOM
  // specifically so it can never bubble into this handler) does not.
  rows.forEach((card) => {
    const href = card.dataset.cardHref;
    if (!href) return;
    card.addEventListener("click", (event) => {
      if (event.target.closest("a, button")) return;
      window.location.href = href;
    });
  });

  // Generic modal open/close for every [data-modal-overlay] on this page
  // (one per application, for the Reviewer & Stage button) -- opt-in via
  // data attributes so it only wires up modals that exist.
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
});
