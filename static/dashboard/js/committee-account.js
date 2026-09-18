document.addEventListener("DOMContentLoaded", () => {
  // ---------------- Notifications: "Unread only" + filter tabs ----------------
  // The generic filter tabs (script.js) and this toggle both hide rows, so
  // one function decides visibility from both, then hides any day group
  // whose rows are all hidden and shows a note when nothing is left.
  const feed = document.getElementById("cmFeed");
  const unreadToggle = document.querySelector("[data-cm-unread-toggle]");
  if (feed && unreadToggle) {
    const rows = Array.from(feed.querySelectorAll(".notif-row[data-filter-item]"));
    const noMatch = document.getElementById("cmFeedNoMatch");

    const apply = () => {
      const tab = document.querySelector(".filter-tab.active");
      const filter = tab ? tab.dataset.filter : "all";
      let visible = 0;
      rows.forEach((row) => {
        const show = (filter === "all" || row.dataset.filter === filter)
          && (!unreadToggle.checked || row.classList.contains("unread"));
        row.hidden = !show;
        if (show) visible++;
      });
      feed.querySelectorAll(".doc-group").forEach((group) => {
        const groupRows = group.querySelectorAll(".notif-row");
        group.hidden = groupRows.length > 0 && Array.from(groupRows).every((r) => r.hidden);
      });
      if (noMatch) noMatch.hidden = visible > 0 || rows.length === 0;
    };

    unreadToggle.addEventListener("change", apply);
    document.querySelectorAll(".filter-tab[data-filter]").forEach((tab) => {
      tab.addEventListener("click", () => setTimeout(apply, 0));
    });
  }

  // ---------------- Profile: change photo -> upload immediately ----------------
  const changeBtn = document.getElementById("changePhotoBtn");
  const avatarInput = document.getElementById("avatarInput");
  const avatarForm = document.getElementById("avatarUploadForm");
  if (changeBtn && avatarInput && avatarForm) {
    changeBtn.addEventListener("click", () => avatarInput.click());
    avatarInput.addEventListener("change", () => {
      if (avatarInput.files && avatarInput.files.length) {
        changeBtn.disabled = true;
        changeBtn.textContent = "Uploading...";
        avatarForm.submit();
      }
    });
  }

  // ---------------- Security: show / hide password ----------------
  document.querySelectorAll("[data-cm-pw-toggle]").forEach((btn) => {
    const input = document.getElementById(btn.dataset.cmPwToggle);
    if (!input) return;
    btn.addEventListener("click", () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.setAttribute("aria-pressed", show ? "true" : "false");
      btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
  });
});
