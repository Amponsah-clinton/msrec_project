// Notifications list page: row checkboxes drive the bulk buttons.
// Bulk forms are ordinary <form method="post"> elements; this only keeps their
// hidden `ids` inputs in step with the ticked rows, so the site-wide confirm
// dialog (form[data-confirm] in script.js) can submit them unchanged.
document.addEventListener("DOMContentLoaded", () => {
  const root = document.getElementById("npRoot");
  if (!root) return;

  const checks = Array.from(root.querySelectorAll(".np-check"));
  const selectAll = document.getElementById("npSelectAll");
  const bulk = document.getElementById("npBulk");
  const selected = document.getElementById("npSelected");
  const countEl = document.getElementById("npSelectedCount");
  const deleteForm = document.getElementById("npDeleteSelected");
  const bulkForms = Array.from(root.querySelectorAll("form[data-np-bulk]"));

  function sync() {
    const ticked = checks.filter((c) => c.checked);
    if (countEl) countEl.textContent = String(ticked.length);
    if (bulk) bulk.hidden = ticked.length === 0;
    if (selected) selected.hidden = ticked.length === 0;
    if (selectAll) {
      selectAll.checked = ticked.length > 0 && ticked.length === checks.length;
      selectAll.indeterminate = ticked.length > 0 && ticked.length < checks.length;
    }
    checks.forEach((c) => c.closest("[data-np-row]").classList.toggle("is-selected", c.checked));
    if (deleteForm) {
      deleteForm.dataset.confirm = "Delete " + ticked.length + " selected notification" + (ticked.length === 1 ? "" : "s") + "? This cannot be undone.";
    }
    bulkForms.forEach((form) => {
      form.querySelectorAll('input[name="ids"]').forEach((input) => input.remove());
      ticked.forEach((c) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = "ids";
        input.value = c.value;
        form.appendChild(input);
      });
    });
  }

  checks.forEach((c) => c.addEventListener("change", sync));
  if (selectAll) {
    selectAll.addEventListener("change", () => {
      checks.forEach((c) => { c.checked = selectAll.checked; });
      sync();
    });
  }
  sync();
});
