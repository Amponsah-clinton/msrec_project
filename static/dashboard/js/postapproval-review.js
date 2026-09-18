document.addEventListener("DOMContentLoaded", () => {
  // ---------------- Generic modal open/close -- same [data-open-modal]/
  // [data-modal-overlay]/[data-modal-close] contract as
  // secretariat-applications.js / committee.js / meetings.js, repeated
  // here so these two pages don't need to load any of those just for
  // their own Review/Reply modals. ----------------
  document.querySelectorAll("[data-open-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const overlay = document.getElementById(btn.dataset.openModal);
      if (overlay) overlay.hidden = false;
    });
  });
  document.querySelectorAll("[data-modal-overlay]").forEach((overlay) => {
    const close = () => { overlay.hidden = true; };
    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) close();
    });
    overlay.querySelectorAll("[data-modal-close]").forEach((btn) => btn.addEventListener("click", close));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll("[data-modal-overlay]:not([hidden])").forEach((overlay) => { overlay.hidden = true; });
  });
});
