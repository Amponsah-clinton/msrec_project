/**
 * Auto-dismisses the flash-message alerts on the Login, Sign Up and
 * Forgot Password pages (.login-message / .signup-message, rendered
 * from Django's messages framework) 4 seconds after the page loads --
 * long enough to read, short enough not to sit there stale once
 * acknowledged.
 */
document.addEventListener("DOMContentLoaded", () => {
  const alerts = document.querySelectorAll(".login-message, .signup-message");
  alerts.forEach((el) => {
    setTimeout(() => {
      el.classList.add("is-dismissing");
      el.addEventListener("transitionend", () => el.remove(), { once: true });
    }, 4000);
  });
});
