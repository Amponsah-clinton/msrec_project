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

  // Quick action buttons — simple visual feedback
  document.querySelectorAll(".qa-btn, .btn-danger, .action-btn, .stat-link, .panel-link").forEach((el) => {
    el.addEventListener("click", (e) => {
      if (el.tagName === "A") e.preventDefault();
    });
  });

  // ---------------- Dropdowns (notifications + profile) ----------------
  const dropdowns = [
    { wrap: document.getElementById("bellDropdown"), btn: document.getElementById("bellBtn"), menu: document.getElementById("bellMenu") },
    { wrap: document.getElementById("profileDropdown"), btn: document.getElementById("profileBtn"), menu: document.getElementById("profileMenu") },
  ];

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
});
