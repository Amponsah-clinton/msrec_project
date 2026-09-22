document.addEventListener("DOMContentLoaded", () => {
  // Generic modal open/close for any [data-open-modal="<id>"] trigger and
  // its matching [data-modal-overlay] -- one shared mechanism instead of a
  // bespoke JS file per modal (Request Revisions, Refer to Committee,
  // Reviewer & Stage, ...), so a page with several modals (e.g. one Refer
  // to Committee modal per application card) needs zero extra JS.
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
