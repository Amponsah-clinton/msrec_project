document.addEventListener("DOMContentLoaded", () => {

  // ---------------- Lightweight "Saved" toast ----------------
  // These reviewer settings pages are demo shells (no backend wired yet),
  // so intercept their forms instead of letting them POST to a TemplateView
  // that would 405. Gives real save feedback without pretending to persist.
  let toast = document.querySelector(".rv-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.className = "rv-toast";
    toast.innerHTML = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="m9 12 2 2 4-4"/></svg><span>Changes saved</span>`;
    document.body.appendChild(toast);
  }
  let toastTimer;
  function showToast(message) {
    toast.querySelector("span").textContent = message || "Changes saved";
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 2400);
  }

  document.querySelectorAll("form[data-rv-demo-save]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      showToast(form.dataset.rvDemoSave === "true" ? "Changes saved" : form.dataset.rvDemoSave);
    });
  });

  // Any switch/checkbox marked data-rv-autosave saves itself immediately
  // (notification + 2FA toggles) rather than needing a separate submit.
  document.querySelectorAll("[data-rv-autosave]").forEach((input) => {
    input.addEventListener("change", () => showToast(input.checked ? "Enabled" : "Disabled"));
  });

  // ---------------- Expertise chip picker ----------------
  const chipField = document.querySelector("[data-rv-chip-field]");
  if (chipField) {
    const chosenWrap = chipField.querySelector("[data-rv-chosen]");
    const suggestWrap = chipField.querySelector("[data-rv-suggestions]");
    const hiddenInput = chipField.querySelector("[data-rv-chip-value]");
    const addInput = chipField.querySelector("[data-rv-chip-input]");
    const addBtn = chipField.querySelector("[data-rv-chip-add-btn]");

    function syncHiddenInput() {
      if (!hiddenInput) return;
      const names = Array.from(chosenWrap.querySelectorAll(".rv-chip")).map((c) => c.dataset.value);
      hiddenInput.value = names.join(", ");
    }

    function addChip(label) {
      const value = label.trim();
      if (!value) return;
      const exists = Array.from(chosenWrap.querySelectorAll(".rv-chip")).some(
        (c) => c.dataset.value.toLowerCase() === value.toLowerCase()
      );
      if (exists) return;

      const chip = document.createElement("span");
      chip.className = "rv-chip";
      chip.dataset.value = value;
      chip.innerHTML = `${value} <button type="button" aria-label="Remove ${value}"><svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg></button>`;
      chip.querySelector("button").addEventListener("click", () => {
        chip.remove();
        const match = suggestWrap && suggestWrap.querySelector(`[data-value="${CSS.escape(value)}"]`);
        if (match) match.hidden = false;
        syncHiddenInput();
      });
      chosenWrap.appendChild(chip);
      syncHiddenInput();
    }

    if (suggestWrap) {
      suggestWrap.querySelectorAll("[data-value]").forEach((btn) => {
        btn.addEventListener("click", () => {
          addChip(btn.dataset.value);
          btn.hidden = true;
        });
      });
    }

    if (addBtn && addInput) {
      const commit = () => {
        addChip(addInput.value);
        addInput.value = "";
        addInput.focus();
      };
      addBtn.addEventListener("click", commit);
      addInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
      });
    }

    syncHiddenInput();
  }

  // ---------------- Steppers (max concurrent reviews, etc.) ----------------
  document.querySelectorAll("[data-rv-stepper]").forEach((stepper) => {
    const output = stepper.querySelector("output");
    const hiddenInput = stepper.parentElement.querySelector("[data-rv-stepper-value]");
    const min = Number(stepper.dataset.min || 0);
    const max = Number(stepper.dataset.max || 99);
    let value = Number(output.textContent);

    stepper.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const delta = btn.dataset.dir === "down" ? -1 : 1;
        value = Math.min(max, Math.max(min, value + delta));
        output.textContent = String(value);
        if (hiddenInput) hiddenInput.value = String(value);
      });
    });
  });

  // ---------------- Password strength meter + live requirement checklist ----------------
  const pwInput = document.querySelector("[data-rv-strength-input]");
  const strengthEl = document.querySelector("[data-rv-strength]");
  if (pwInput && strengthEl) {
    const pill = strengthEl.querySelector("[data-rv-strength-pill]");
    const requirements = strengthEl.querySelectorAll("[data-rv-req]");
    const labels = ["Too short", "Weak", "Fair", "Good", "Strong"];

    const checks = {
      length: (val) => val.length >= 8,
      case: (val) => /[a-z]/.test(val) && /[A-Z]/.test(val),
      number: (val) => /\d/.test(val),
      symbol: (val) => /[^A-Za-z0-9]/.test(val),
    };

    function updateStrength() {
      const val = pwInput.value;
      let score = 0;
      requirements.forEach((item) => {
        const met = checks[item.dataset.rvReq](val);
        item.classList.toggle("met", met);
        if (met) score++;
      });
      if (!val) score = 0;

      strengthEl.dataset.score = String(score);
      if (pill) pill.textContent = val ? labels[score] : "Enter a new password";
    }

    pwInput.addEventListener("input", updateStrength);
    updateStrength();
  }

  // ---------------- Confirm-password live match indicator ----------------
  const confirmInput = document.querySelector("[data-rv-confirm-input]");
  const matchEl = document.querySelector("[data-rv-match]");
  if (pwInput && confirmInput && matchEl) {
    const matchLabel = matchEl.querySelector("span");

    function updateMatch() {
      if (!confirmInput.value) {
        matchEl.hidden = true;
        matchEl.removeAttribute("data-match");
        return;
      }
      const matches = confirmInput.value === pwInput.value;
      matchEl.hidden = false;
      matchEl.dataset.match = matches ? "yes" : "no";
      matchLabel.textContent = matches ? "Passwords match" : "Passwords don't match";
    }

    pwInput.addEventListener("input", updateMatch);
    confirmInput.addEventListener("input", updateMatch);
  }

  // Cancel (type=reset) clears the fields natively -- but the strength
  // meter/checklist/match hint only listen for "input", so reset them
  // explicitly once the native reset has run (next tick).
  const pwForm = pwInput && pwInput.closest("form");
  if (pwForm) {
    pwForm.addEventListener("reset", () => {
      setTimeout(() => {
        pwInput.dispatchEvent(new Event("input"));
        if (confirmInput) confirmInput.dispatchEvent(new Event("input"));
      }, 0);
    });
  }

  // ---------------- 2FA method "Set Up" demo toggle ----------------
  document.querySelectorAll("[data-rv-demo-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const card = btn.closest(".rv-2fa-card");
      if (!card) return;
      card.classList.add("is-on");
      const status = card.querySelector(".rv-2fa-status");
      if (status) {
        status.textContent = "Enabled";
        status.classList.remove("off");
        status.classList.add("on");
      }
      btn.textContent = "Manage";
      btn.removeAttribute("data-rv-demo-toggle");
      showToast(card.querySelector("h4")?.textContent + " enabled");
    });
  });

  // ---------------- Unread-only filter (Notifications page) ----------------
  const unreadToggle = document.querySelector("[data-rv-unread-toggle]");
  if (unreadToggle) {
    unreadToggle.addEventListener("change", () => {
      document.querySelectorAll(".notif-row[data-filter-item]").forEach((row) => {
        if (unreadToggle.checked) {
          row.hidden = !row.classList.contains("unread");
        } else {
          const activeTab = document.querySelector(".filter-tab.active");
          const filter = activeTab ? activeTab.dataset.filter : "all";
          row.hidden = !(filter === "all" || row.dataset.filter === filter);
        }
      });
    });
  }
});
