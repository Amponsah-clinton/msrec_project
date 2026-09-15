document.addEventListener("DOMContentLoaded", () => {
  const openBtn = document.getElementById("requestRevisionsOpen");
  const overlay = document.getElementById("requestRevisionsOverlay");
  if (!openBtn || !overlay) return;

  const closeBtn = document.getElementById("requestRevisionsClose");
  const cancelBtn = document.getElementById("requestRevisionsCancel");
  const textarea = overlay.querySelector("textarea");

  function open() {
    overlay.hidden = false;
    if (textarea) textarea.focus();
  }
  function close() {
    overlay.hidden = true;
  }

  openBtn.addEventListener("click", open);
  closeBtn.addEventListener("click", close);
  cancelBtn.addEventListener("click", close);
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) close();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !overlay.hidden) close();
  });
});
