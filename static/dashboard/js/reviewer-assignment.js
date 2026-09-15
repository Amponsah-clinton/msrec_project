document.addEventListener("DOMContentLoaded", () => {
  // Three real panels (Assign Reviewer / Pending Assignments / Reviewer
  // Workload), not a filtered list -- script.js's generic filter-tabs
  // handler still toggles `.active` on these buttons (harmless), but
  // showing/hiding the actual panel is this page's own job.
  const tabs = document.querySelectorAll("[data-ra-tab]");
  const panels = document.querySelectorAll("[data-ra-panel]");
  if (!tabs.length || !panels.length) return;

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const target = tab.dataset.raTab;
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.raPanel !== target;
      });
    });
  });
});
