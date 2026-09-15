document.addEventListener("DOMContentLoaded", () => {
  // "Change Photo" opens the native file picker; picking a file submits
  // the (separate, single-purpose) avatar form immediately -- no extra
  // "Upload" click needed. Session-revoke confirmation is handled by the
  // generic data-confirm modal in dashboard/js/script.js.
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

  // Confirm before a password change is silently discarded by mismatched
  // fields -- client-side check only; the server re-validates regardless.
  const settingsForm = document.getElementById("profileSettingsForm");
  if (settingsForm) {
    const email = settingsForm.querySelector("#pfEmail");
    const confirmEmail = settingsForm.querySelector("#pfConfirmEmail");
    const emailMatchError = document.getElementById("pfEmailMatchError");
    [email, confirmEmail].forEach((f) => {
      if (f && emailMatchError) f.addEventListener("input", () => { emailMatchError.hidden = true; });
    });

    settingsForm.addEventListener("submit", (event) => {
      if (email && confirmEmail && email.value.trim().toLowerCase() !== confirmEmail.value.trim().toLowerCase()) {
        event.preventDefault();
        if (emailMatchError) emailMatchError.hidden = false;
        confirmEmail.focus();
        return;
      }

      const current = settingsForm.querySelector("#pfCurrentPassword");
      const next = settingsForm.querySelector("#pfNewPassword");
      const confirm = settingsForm.querySelector("#pfConfirmPassword");
      const anyPasswordField = [current, next, confirm].some((f) => f && f.value.trim());
      if (anyPasswordField && next.value !== confirm.value) {
        event.preventDefault();
        confirm.setCustomValidity("New password and confirmation don't match.");
        confirm.reportValidity();
        return;
      }
      if (confirm) confirm.setCustomValidity("");
    });
  }

  // Show/hide toggle on every password field (fa-eye <-> fa-eye-slash).
  document.querySelectorAll("[data-password-toggle]").forEach((btn) => {
    const input = document.getElementById(btn.dataset.passwordToggle);
    const icon = btn.querySelector("i");
    if (!input || !icon) return;
    btn.addEventListener("click", () => {
      const nowVisible = input.type === "password";
      input.type = nowVisible ? "text" : "password";
      icon.classList.toggle("fa-eye", !nowVisible);
      icon.classList.toggle("fa-eye-slash", nowVisible);
      btn.setAttribute("aria-pressed", String(nowVisible));
      btn.setAttribute("aria-label", (nowVisible ? "Hide" : "Show") + " password");
    });
  });
});
