document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sidebar");
  const overlay = document.getElementById("overlay");
  const menuToggle = document.getElementById("menuToggle");

  function openSidebar() {
    sidebar.classList.add("open");
    overlay.classList.add("show");
  }

  function closeSidebar() {
    sidebar.classList.remove("open");
    overlay.classList.remove("show");
  }

  menuToggle.addEventListener("click", () => {
    sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
  });

  overlay.addEventListener("click", closeSidebar);

  // Close mobile sidebar automatically when a nav link is clicked. Links that
  // point at a real page (anything other than the "#" placeholder used by
  // stubs not yet built) are left alone so they navigate normally — the
  // destination page marks its own sidebar entry "active" in its markup.
  document.querySelectorAll(".nav-item, .nav-sublink").forEach((item) => {
    item.addEventListener("click", (e) => {
      const href = item.getAttribute("href") || "";
      if (href === "#") {
        e.preventDefault();
        document.querySelectorAll(".nav-item, .nav-sublink").forEach((n) => n.classList.remove("active"));
        item.classList.add("active");
      }
      closeSidebar();
    });
  });

  // Expand / collapse sidebar groups that contain subpages
  document.querySelectorAll(".nav-group-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const group = btn.closest(".nav-group");
      const willOpen = !group.classList.contains("open");
      group.classList.toggle("open", willOpen);
      btn.setAttribute("aria-expanded", String(willOpen));
    });
  });

  // Collapse mobile sidebar if window is resized back to desktop width
  window.addEventListener("resize", () => {
    if (window.innerWidth > 900) closeSidebar();
  });

  // ---------------- Filter tabs ----------------
  // Generic: a `.filter-tabs` container with `[data-filters-target]` (a
  // selector for the items container) toggles `.active` among its
  // `.filter-tab[data-filter]` buttons and shows/hides that container's
  // `[data-filter-item]` children whose `data-filter` matches (or every
  // item, for the "all" tab). Opt-in via data attributes, so it only
  // affects pages that actually use it.
  document.querySelectorAll(".filter-tabs[data-filters-target]").forEach((tabs) => {
    const target = document.querySelector(tabs.dataset.filtersTarget);
    if (!target) return;
    const items = Array.from(target.querySelectorAll("[data-filter-item]"));

    tabs.querySelectorAll(".filter-tab[data-filter]").forEach((tab) => {
      tab.addEventListener("click", () => {
        tabs.querySelectorAll(".filter-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");

        const filter = tab.dataset.filter;
        items.forEach((item) => {
          const matches = filter === "all" || item.dataset.filter === filter;
          item.hidden = !matches;
        });

        // A .doc-group with every one of its rows hidden shouldn't leave
        // an empty header floating around.
        target.querySelectorAll(".doc-group").forEach((group) => {
          const rows = group.querySelectorAll("[data-filter-item]");
          group.hidden = rows.length > 0 && Array.from(rows).every((r) => r.hidden);
        });
      });
    });
  });

  // Quick action buttons — only swallow the click for still-unwired demo
  // links (href="#"); anything pointing at a real URL should navigate.
  document.querySelectorAll(".qa-btn, .btn-danger, .action-btn, .stat-link, .panel-link").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (el.tagName === "A" && el.getAttribute("href") === "#") e.preventDefault();
    });
  });

  // ---------------- Dropdowns (notifications + profile) ----------------
  // Not every dashboard page carries both (e.g. the admin Accounts page has
  // no bell dropdown in its topbar) -- filter out whichever ids aren't
  // present rather than assuming all three elements of a pair exist.
  const dropdowns = [
    { wrap: document.getElementById("bellDropdown"), btn: document.getElementById("bellBtn"), menu: document.getElementById("bellMenu") },
    { wrap: document.getElementById("profileDropdown"), btn: document.getElementById("profileBtn"), menu: document.getElementById("profileMenu") },
  ].filter(({ wrap, btn, menu }) => wrap && btn && menu);

  function closeAllDropdowns(except) {
    dropdowns.forEach(({ wrap, btn, menu }) => {
      // On small screens the bell dropdown lives inside the profile dropdown
      // (see the "compact topbar" block below) — closing every *other*
      // dropdown would otherwise immediately hide the ancestor profile menu
      // (opacity/visibility collapse to 0) the instant its nested
      // notifications panel opens. Skip anything that is an ancestor of the
      // dropdown being opened; a plain sibling relationship (the desktop
      // layout) is unaffected since neither contains the other there.
      if (wrap === except || wrap.contains(except)) return;
      wrap.classList.remove("open");
      menu.classList.remove("open");
      btn.classList.remove("open");
      btn.setAttribute("aria-expanded", "false");
    });
  }

  dropdowns.forEach(({ wrap, btn, menu }) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = !menu.classList.contains("open");
      closeAllDropdowns(willOpen ? wrap : null);
      wrap.classList.toggle("open", willOpen);
      menu.classList.toggle("open", willOpen);
      btn.classList.toggle("open", willOpen);
      btn.setAttribute("aria-expanded", String(willOpen));
    });
  });

  document.addEventListener("click", () => closeAllDropdowns());

  document.querySelectorAll(".dropdown-menu").forEach((menu) => {
    menu.addEventListener("click", (e) => e.stopPropagation());
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAllDropdowns();
  });

  // Mark all as read: clear unread dots + badge count
  const markReadBtn = document.querySelector(".mark-read");
  const bellBadge = document.querySelector(".bell-btn .badge");
  if (markReadBtn) {
    markReadBtn.addEventListener("click", () => {
      document.querySelectorAll(".bell-list li.unread").forEach((li) => li.classList.remove("unread"));
      if (bellBadge) bellBadge.remove();
    });
  }

  // ---------------- Compact topbar (small screens) ----------------
  // Three separate round icon buttons (theme toggle, bell, avatar) fighting
  // for the same narrow topbar row is what actually looks "spoilt" on
  // phones. Below the breakpoint, move the theme toggle and the whole
  // notifications dropdown to live inside the profile dropdown instead, so
  // the topbar itself only ever shows the single avatar trigger. The nodes
  // are *moved*, not cloned, so there is exactly one themeToggle/bellMenu in
  // the page at all times — no duplicate ids, no desynced state. CSS (see
  // style.css) restyles them as plain rows once they're descendants of
  // .profile-menu.
  const themeToggleEl = document.getElementById("themeToggle");
  const bellDropdownEl = document.getElementById("bellDropdown");
  const profileDropdownEl = document.getElementById("profileDropdown");
  const profileMenuEl = document.getElementById("profileMenu");
  const profileMenuHeadEl = profileMenuEl ? profileMenuEl.querySelector(".profile-menu-head") : null;
  const topbarActionsEl = document.querySelector(".topbar-actions");

  if (themeToggleEl && bellDropdownEl && profileDropdownEl && profileMenuEl && profileMenuHeadEl && topbarActionsEl) {
    const compactQuery = window.matchMedia("(max-width: 600px)");

    const layoutTopbarActions = (isCompact) => {
      if (isCompact) {
        // Land both rows right after the profile card, in their usual
        // left-to-right order (theme, then notifications), ahead of the
        // "My Profile" / "Account Settings" links.
        profileMenuHeadEl.insertAdjacentElement("afterend", bellDropdownEl);
        profileMenuHeadEl.insertAdjacentElement("afterend", themeToggleEl);
      } else {
        topbarActionsEl.insertBefore(themeToggleEl, profileDropdownEl);
        topbarActionsEl.insertBefore(bellDropdownEl, profileDropdownEl);
      }
    };

    layoutTopbarActions(compactQuery.matches);
    compactQuery.addEventListener("change", (e) => layoutTopbarActions(e.matches));
  }

  // ---------------- Light / dark theme toggle ----------------
  const root = document.documentElement;
  const themeToggle = document.getElementById("themeToggle");
  const themeColorMeta = document.getElementById("themeColorMeta");
  const THEME_COLORS = { light: "#f4f6f9", dark: "#0e1015" };

  function currentTheme() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function setThemeUI(theme) {
    root.setAttribute("data-theme", theme);
    if (themeColorMeta) themeColorMeta.setAttribute("content", THEME_COLORS[theme]);
    if (themeToggle) themeToggle.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
  }

  function applyTheme(theme) {
    setThemeUI(theme);
    try {
      localStorage.setItem("msrec-theme", theme);
    } catch (e) {
      /* localStorage unavailable — theme still applies for this session */
    }
  }

  // Sync toggle state with whatever the inline head script already set,
  // so no flash / mismatch happens on first paint. Does not touch storage,
  // so the "follow OS theme" listener below keeps working until the user
  // makes an explicit choice.
  setThemeUI(currentTheme());

  if (themeToggle) {
    themeToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      applyTheme(currentTheme() === "dark" ? "light" : "dark");
    });
  }

  // Follow the OS theme live, but only until the user picks one explicitly.
  if (window.matchMedia) {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", (e) => {
      let hasStoredChoice = false;
      try {
        hasStoredChoice = localStorage.getItem("msrec-theme") !== null;
      } catch (err) {
        hasStoredChoice = false;
      }
      if (!hasStoredChoice) applyTheme(e.matches ? "dark" : "light");
    });
  }

  // ---------------- Message threads (Messages page) ----------------
  // Clicking a conversation in the list shows its thread panel and hides
  // the others. On small screens (see the max-width: 900px rule in
  // style.css) the thread panel becomes a full-screen overlay instead of a
  // second column, so opening one also flags the shell with .thread-open
  // and reveals the back button; closing it just removes that flag.
  const messageRows = document.querySelectorAll(".message-row[data-thread]");
  if (messageRows.length) {
    const shell = document.querySelector(".messages-shell");
    const threads = document.querySelectorAll(".thread-panel[data-thread]");
    const backBtn = document.querySelector(".thread-back-btn");

    messageRows.forEach((row) => {
      row.addEventListener("click", () => {
        messageRows.forEach((r) => r.classList.remove("active"));
        row.classList.add("active");
        row.classList.remove("unread");
        threads.forEach((t) => t.classList.toggle("is-active", t.dataset.thread === row.dataset.thread));
        if (shell) shell.classList.add("thread-open");
      });
    });

    if (backBtn && shell) {
      backBtn.addEventListener("click", () => shell.classList.remove("thread-open"));
    }

    // Reply composer: no backend, so sending just echoes the message into
    // the open thread as a locally-sent bubble -- enough to feel real
    // without pretending to persist anywhere.
    document.querySelectorAll(".thread-composer").forEach((form) => {
      const textarea = form.querySelector("textarea");
      const scroll = form.closest(".thread-panel")?.querySelector(".thread-scroll");
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const text = (textarea.value || "").trim();
        if (!text || !scroll) return;
        const bubble = document.createElement("div");
        bubble.className = "msg-bubble out";
        const p = document.createElement("p");
        p.textContent = text;
        const time = document.createElement("span");
        time.className = "msg-time";
        time.textContent = "Just now";
        bubble.appendChild(p);
        bubble.appendChild(time);
        scroll.appendChild(bubble);
        scroll.scrollTop = scroll.scrollHeight;
        textarea.value = "";
      });
      // Enter sends, Shift+Enter inserts a newline.
      textarea?.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          form.requestSubmit();
        }
      });
    });
  }
});

// ---------------------------------------------------------------------
// Generic confirm modal — any `<form data-confirm="...">` on any dashboard
// page gets its submit intercepted and re-asked through this modal instead
// of the browser's native window.confirm(). Add data-confirm-variant="danger"
// on a form for the red/destructive styling (delete); anything else gets the
// neutral orange styling (suspend, reopen, etc). Registered as its own
// top-level listener (not inside the block above) so it still wires up even
// on pages that don't load the rest of that block's markup.
document.addEventListener("DOMContentLoaded", () => {
  const forms = Array.from(document.querySelectorAll("form[data-confirm]"));
  if (!forms.length) return;

  const overlay = document.createElement("div");
  overlay.className = "confirm-modal-overlay";
  overlay.hidden = true;
  overlay.innerHTML = `
    <div class="confirm-modal" role="alertdialog" aria-modal="true" aria-labelledby="confirmModalMsg">
      <div class="confirm-modal-icon">
        <svg viewBox="0 0 24 24"><path d="M12 9v4"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/><path d="M12 17h.01"/></svg>
      </div>
      <p id="confirmModalMsg"></p>
      <div class="confirm-modal-actions">
        <button type="button" class="confirm-modal-cancel">Cancel</button>
        <button type="button" class="confirm-modal-ok">Confirm</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const msgEl = overlay.querySelector("#confirmModalMsg");
  const okBtn = overlay.querySelector(".confirm-modal-ok");
  const cancelBtn = overlay.querySelector(".confirm-modal-cancel");
  let pendingForm = null;

  function close() {
    overlay.hidden = true;
    overlay.classList.remove("is-danger");
    pendingForm = null;
  }

  forms.forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      pendingForm = form;
      msgEl.textContent = form.dataset.confirm;
      okBtn.textContent = form.dataset.confirmLabel || "Confirm";
      overlay.classList.toggle("is-danger", form.dataset.confirmVariant === "danger");
      overlay.hidden = false;
      okBtn.focus();
    });
  });

  okBtn.addEventListener("click", () => {
    if (!pendingForm) return;
    const form = pendingForm;
    close();
    form.submit();
  });
  cancelBtn.addEventListener("click", close);
  overlay.addEventListener("click", (event) => { if (event.target === overlay) close(); });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlay.hidden) close();
  });
});

// ---------------------------------------------------------------------
// Flash messages (django.contrib.messages, rendered once in base.html so
// every dashboard page gets it) -- auto-dismiss each alert 5s after the
// page loads instead of leaving success/error banners on screen forever.
// Timer starts at page load, not per-message stagger, so several messages
// from the same request all disappear together.
document.addEventListener("DOMContentLoaded", () => {
  const FLASH_AUTO_DISMISS_MS = 5000;

  document.querySelectorAll(".flash-messages .flash-message").forEach((el) => {
    setTimeout(() => {
      el.classList.add("is-dismissing");
      // Transition end removes it cleanly; the fallback timeout covers
      // reduced-motion / no-transition environments where that event
      // never fires, so the (by-then invisible) element doesn't linger.
      el.addEventListener("transitionend", () => el.remove(), { once: true });
      setTimeout(() => el.remove(), 500);
    }, FLASH_AUTO_DISMISS_MS);
  });
});
