document.addEventListener("DOMContentLoaded", () => {
  const toggleBtn = document.getElementById("togglePassword");
  const passwordInput = document.getElementById("password");
  const toggleIcon = document.getElementById("toggleIcon");

  if (toggleBtn && passwordInput) {
    toggleBtn.addEventListener("click", () => {
      const isHidden = passwordInput.type === "password";
      passwordInput.type = isHidden ? "text" : "password";
      toggleIcon.classList.toggle("bi-eye", !isHidden);
      toggleIcon.classList.toggle("bi-eye-slash", isHidden);
      toggleBtn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
    });
  }

  const form = document.getElementById("loginForm");
  if (form) {
    form.addEventListener("submit", (e) => {
      if (!form.checkValidity()) {
        e.preventDefault();
        form.reportValidity();
        return;
      }
      // Valid: let the real POST to the server go through. Just show a
      // busy state on the button while the page navigates away.
      const btn = form.querySelector(".btn-signin");
      btn.disabled = true;
      btn.textContent = "Signing in...";
    });
  }
});
