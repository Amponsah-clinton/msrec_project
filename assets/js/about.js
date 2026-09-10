document.addEventListener("DOMContentLoaded", () => {
  const tabs = document.querySelectorAll(".ab-tab");
  const panels = document.querySelectorAll(".ab-tab-panel");
  if (!tabs.length) return;

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.tab;

      tabs.forEach((t) => {
        t.classList.toggle("active", t === tab);
        t.setAttribute("aria-selected", t === tab ? "true" : "false");
      });
      panels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.panel === target);
      });
    });
  });
});
