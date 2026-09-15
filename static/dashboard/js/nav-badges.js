/* ==========================================================
   Sidebar "Applications" badges — polls applicant_dashboard's
   nav-counts endpoint and keeps the six status badges current
   without a page reload. A no-op on every other dashboard (no
   [data-nav-badge] elements there, so the very first check bails).
========================================================== */
(function () {
  const badges = document.querySelectorAll("[data-nav-badge]");
  if (!badges.length) return;

  const endpoint = document.body.dataset.navCountsUrl;
  if (!endpoint) return;

  const POLL_MS = 15000;
  const previous = {};

  function applyCounts(counts) {
    badges.forEach((badge) => {
      const key = badge.dataset.navBadge;
      const value = Number(counts[key] || 0);
      const changed = previous[key] !== undefined && previous[key] !== value;
      previous[key] = value;

      badge.textContent = value > 99 ? "99+" : String(value);
      badge.hidden = value === 0;

      if (changed) {
        badge.classList.remove("nav-badge-pulse");
        // Force reflow so the animation replays on back-to-back changes.
        void badge.offsetWidth;
        badge.classList.add("nav-badge-pulse");
      }
    });
  }

  async function poll() {
    try {
      const res = await fetch(endpoint, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!res.ok) return;
      applyCounts(await res.json());
    } catch (e) {
      // Offline or a transient network hiccup — just try again next tick.
    }
  }

  poll();
  setInterval(poll, POLL_MS);

  // Catch up immediately when the applicant returns to this tab (e.g.
  // after acting on something from a status email in another tab).
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll();
  });
})();
