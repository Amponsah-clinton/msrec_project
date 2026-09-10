document.addEventListener("DOMContentLoaded", () => {
  /* ---------------- Review Types tabs ---------------- */
  const rtTabs = document.querySelectorAll(".rt-tab");
  const rtPanels = document.querySelectorAll(".rt-panel");

  rtTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.rtTab;

      rtTabs.forEach((t) => {
        t.classList.toggle("active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      rtPanels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.rtPanel === target);
      });
    });
  });

  /* ---------------- FAQ accordion ---------------- */
  document.querySelectorAll(".ap-faq-question").forEach((btn) => {
    btn.addEventListener("click", () => {
      const item = btn.closest(".ap-faq-item");
      const wasActive = item.classList.contains("ap-faq-active");
      item.parentElement.querySelectorAll(".ap-faq-item").forEach((el) => el.classList.remove("ap-faq-active"));
      if (!wasActive) item.classList.add("ap-faq-active");
    });
  });
});
