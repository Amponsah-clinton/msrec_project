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
      e.preventDefault();
      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }
      const btn = form.querySelector(".btn-signin");
      const original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Signing in...";
      setTimeout(() => {
        btn.disabled = false;
        btn.textContent = original;
      }, 900);
    });
  }
});
