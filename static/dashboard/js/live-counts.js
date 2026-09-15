/* ==========================================================
   Generic live-count poller. Any element carrying
   [data-counts-url="..."] is polled on an interval; every
   [data-count-key="..."] inside it gets its text updated from the
   matching key in that endpoint's JSON response, with a little pulse
   whenever a number actually changes. Opt-in via data attributes, so
   it's a no-op on pages that don't use it.
========================================================== */
(function () {
  const POLL_MS = 15000;
  const pollers = [];

  document.querySelectorAll("[data-counts-url]").forEach((root) => {
    const endpoint = root.dataset.countsUrl;
    const countEls = root.querySelectorAll("[data-count-key]");
    if (!endpoint || !countEls.length) return;

    const previous = {};

    async function poll() {
      try {
        const res = await fetch(endpoint, { headers: { "X-Requested-With": "XMLHttpRequest" } });
        if (!res.ok) return;
        const counts = await res.json();

        countEls.forEach((el) => {
          const key = el.dataset.countKey;
          if (!(key in counts)) return;
          const value = Number(counts[key] || 0);
          const changed = previous[key] !== undefined && previous[key] !== value;
          previous[key] = value;

          el.textContent = value > 999 ? "999+" : String(value);

          if (changed) {
            el.classList.remove("count-pulse");
            void el.offsetWidth; // restart the animation on back-to-back changes
            el.classList.add("count-pulse");
          }
        });
      } catch (e) {
        // Offline or a transient hiccup — the next tick will retry.
      }
    }

    poll();
    setInterval(poll, POLL_MS);
    pollers.push(poll);
  });

  if (pollers.length) {
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") pollers.forEach((poll) => poll());
    });
  }
})();
