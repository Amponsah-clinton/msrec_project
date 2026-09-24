/* ==========================================================
   Topbar notification bell — polls this dashboard's notification
   feed endpoint and re-renders the badge count + dropdown list
   without a page reload. A no-op wherever the bell dropdown has no
   [data-notif-feed-url] (i.e. every non-dashboard page).
========================================================== */
(function () {
  const dropdown = document.getElementById("bellDropdown");
  if (!dropdown) return;

  const endpoint = dropdown.dataset.notifFeedUrl;
  if (!endpoint) return;

  const badge = dropdown.querySelector(".bell-btn .badge");
  const list = dropdown.querySelector(".bell-list[data-feed-list]") || dropdown.querySelector(".bell-list");
  // Items the server counted into the badge that aren't feed rows (the
  // admin bell's "Needs attention" backlog) -- kept in the badge on refresh.
  const extraCount = parseInt(dropdown.dataset.extraCount || "0", 10) || 0;
  const markReadForm = dropdown.querySelector(".dropdown-head form");
  const POLL_MS = 20000;
  let previousCount = null;

  const ICONS = {
    success: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m9 12 2 2 4-4"/></svg>',
    warn: '<svg viewBox="0 0 24 24"><path d="M12 9v4"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 17h.01"/></svg>',
    pay: '<svg viewBox="0 0 24 24"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>',
    info: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8h.01M11 12h1v4h1"/></svg>',
  };

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text == null ? "" : String(text);
    return div.innerHTML;
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleString(undefined, {
        day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit",
      });
    } catch (e) {
      return "";
    }
  }

  function applyBadge(count) {
    if (!badge) return;
    const changed = previousCount !== null && previousCount !== count;
    previousCount = count;

    const total = count + extraCount;
    badge.textContent = total > 99 ? "99+" : String(total);
    badge.hidden = total === 0;

    if (changed && count > 0) {
      badge.classList.remove("nav-badge-pulse");
      void badge.offsetWidth;
      badge.classList.add("nav-badge-pulse");
    }
    if (markReadForm) markReadForm.hidden = count === 0;
  }

  function renderList(items) {
    if (!list) return;
    if (!items.length) {
      list.innerHTML = '<li class="notice-empty"><div class="notice-body"><p>No notifications yet.</p></div></li>';
      return;
    }
    list.innerHTML = items.map((item) => `
      <li class="${item.is_read ? "" : "unread"}">
        <span class="notice-icon ${escapeHtml(item.icon)}">${ICONS[item.icon] || ICONS.info}</span>
        <div class="notice-body">
          <p><a href="${escapeHtml(item.url)}">${escapeHtml(item.message)}</a></p>
          <span class="notice-date">${formatDate(item.created_at)}</span>
        </div>
      </li>
    `).join("");
  }

  async function poll() {
    try {
      const res = await fetch(endpoint, { headers: { "X-Requested-With": "XMLHttpRequest" } });
      if (!res.ok) return;
      const data = await res.json();
      applyBadge(Number(data.count || 0));
      renderList(Array.isArray(data.items) ? data.items : []);
    } catch (e) {
      // Offline or a transient network hiccup — just try again next tick.
    }
  }

  poll();
  setInterval(poll, POLL_MS);

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") poll();
  });
})();
