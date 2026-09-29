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

  // Confirm before a mismatched email is silently rejected by the server --
  // client-side check only; the server re-validates regardless.
  const personalInfoForm = document.getElementById("personalInfoForm");
  if (personalInfoForm) {
    const email = personalInfoForm.querySelector("#pfEmail");
    const confirmEmail = personalInfoForm.querySelector("#pfConfirmEmail");
    const emailMatchError = document.getElementById("pfEmailMatchError");
    [email, confirmEmail].forEach((f) => {
      if (f && emailMatchError) f.addEventListener("input", () => { emailMatchError.hidden = true; });
    });

    personalInfoForm.addEventListener("submit", (event) => {
      if (email && confirmEmail && email.value.trim().toLowerCase() !== confirmEmail.value.trim().toLowerCase()) {
        event.preventDefault();
        if (emailMatchError) emailMatchError.hidden = false;
        confirmEmail.focus();
      }
    });
  }

  // Same idea for the password form: catch a mismatched confirmation
  // before it round-trips to the server.
  const passwordForm = document.getElementById("passwordForm");
  if (passwordForm) {
    const next = passwordForm.querySelector("#pfNewPassword");
    const confirm = passwordForm.querySelector("#pfConfirmPassword");
    passwordForm.addEventListener("submit", (event) => {
      if (next.value !== confirm.value) {
        event.preventDefault();
        confirm.setCustomValidity("New password and confirmation don't match.");
        confirm.reportValidity();
        return;
      }
      confirm.setCustomValidity("");
    });
    [next, confirm].forEach((f) => f.addEventListener("input", () => confirm.setCustomValidity("")));
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
