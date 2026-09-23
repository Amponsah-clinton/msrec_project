// Request Revisions composer (secretariat application detail). Each required
// change is its own `revision_item` textarea; the server numbers them into
// the letter the applicant receives (secretariat_dashboard.views.
// _compose_revision_comment), so this only manages the list itself.
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("rrForm");
  if (!form) return;

  const list = document.getElementById("rrItems");
  const count = document.getElementById("rrCount");
  const error = document.getElementById("rrError");
  const note = document.getElementById("rrNote");
  const template = list.querySelector(".rr-item").cloneNode(true);
  template.querySelector("textarea").value = "";
  template.querySelector("textarea").removeAttribute("id");

  function items() {
    return Array.from(list.querySelectorAll(".rr-item"));
  }

  function refresh() {
    const rows = items();
    rows.forEach((row, i) => {
      row.querySelector(".rr-num").textContent = i + 1;
      row.querySelector(".rr-remove").hidden = rows.length === 1;
    });
    count.textContent = `${rows.length} item${rows.length === 1 ? "" : "s"}`;
  }

  function autosize(textarea) {
    textarea.style.height = "auto";
    textarea.style.height = `${textarea.scrollHeight + 2}px`;
  }

  function addItem(text = "", focus = true) {
    const empty = items().find((row) => !row.querySelector("textarea").value.trim());
    const row = empty || template.cloneNode(true);
    const textarea = row.querySelector("textarea");
    textarea.value = text;
    if (!empty) list.appendChild(row);
    refresh();
    autosize(textarea);
    if (focus) textarea.focus();
    return row;
  }

  document.getElementById("rrAdd").addEventListener("click", () => {
    const row = template.cloneNode(true);
    list.appendChild(row);
    refresh();
    row.querySelector("textarea").focus();
  });

  list.addEventListener("click", (event) => {
    const remove = event.target.closest(".rr-remove");
    if (!remove || items().length === 1) return;
    remove.closest(".rr-item").remove();
    refresh();
  });

  list.addEventListener("input", (event) => {
    if (event.target.matches("textarea")) {
      autosize(event.target);
      error.hidden = true;
    }
  });

  // A reviewer's "key concerns" are usually a list of their own -- one line
  // (or bullet / numbered point) per concern -- so each becomes its own item.
  document.querySelectorAll(".rr-use").forEach((button) => {
    button.addEventListener("click", () => {
      const lines = button.dataset.text
        .split(/\r?\n/)
        .map((line) => line.replace(/^\s*(?:[-*•]|\d+[.)])\s*/, "").trim())
        .filter(Boolean);
      lines.forEach((line, i) => addItem(line, i === lines.length - 1));
      button.disabled = true;
      button.textContent = "Added";
    });
  });

  form.addEventListener("submit", (event) => {
    const hasItem = items().some((row) => row.querySelector("textarea").value.trim());
    if (!hasItem && !note.value.trim()) {
      event.preventDefault();
      error.hidden = false;
      items()[0].querySelector("textarea").focus();
    }
  });

  refresh();
});
