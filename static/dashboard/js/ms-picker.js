/* Searchable multi-select ("ms-picker") -- progressively enhances a plain
   chip-checkbox grid (real `<input type="checkbox" name="...">` elements,
   see the "Committee members" picker in the Refer to Committee modal) into
   a compact dropdown: a control showing the current picks as removable
   chips, and a panel with a search box + scrollable checkbox list.

   The real checkbox <label> elements are MOVED (not cloned) into the new
   list, so they keep posting under their original `name=` in the
   surrounding <form> exactly as before -- this is UI only, no change to
   what the server receives. If JS never runs, the picker's `data-ms-source`
   grid is simply left visible as an ordinary chip-checkbox grid, so the
   form still works without JS.
*/
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-ms-picker]").forEach((picker) => {
    const source = picker.querySelector("[data-ms-source]");
    if (!source) return;

    const optionLabels = Array.from(source.querySelectorAll(".chip-checkbox"));
    if (!optionLabels.length) return; // nothing to pick -- leave the (empty-state) source as-is

    const placeholder = picker.dataset.msPlaceholder || "Select...";
    const searchPlaceholder = picker.dataset.msSearchPlaceholder || "Search...";

    optionLabels.forEach((label) => {
      const span = label.querySelector("span");
      label.dataset.msSearch = (span ? span.textContent : label.textContent).trim().toLowerCase();
    });

    const control = document.createElement("button");
    control.type = "button";
    control.className = "ms-picker-control";

    const chipsHost = document.createElement("div");
    chipsHost.className = "ms-picker-chips";
    control.appendChild(chipsHost);

    const caret = document.createElement("span");
    caret.className = "ms-picker-caret";
    caret.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"/></svg>';
    control.appendChild(caret);

    const panel = document.createElement("div");
    panel.className = "ms-picker-panel";
    panel.hidden = true;

    const searchRow = document.createElement("div");
    searchRow.className = "ms-picker-search";
    searchRow.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>';
    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = searchPlaceholder;
    searchInput.setAttribute("aria-label", searchPlaceholder);
    searchRow.appendChild(searchInput);
    panel.appendChild(searchRow);

    const list = document.createElement("div");
    // Keeps "chip-checkbox-grid" so the moved <label class="chip-checkbox">
    // elements still match its `.chip-checkbox-grid .chip-checkbox` CSS
    // (borders, spacing, the custom checkbox appearance) -- that styling
    // requires a .chip-checkbox-grid ancestor, which moving them out of
    // the original (now-hidden) source grid would otherwise strip.
    list.className = "ms-picker-list chip-checkbox-grid";
    optionLabels.forEach((label) => list.appendChild(label)); // moved, not cloned
    panel.appendChild(list);

    const emptyState = document.createElement("p");
    emptyState.className = "ms-picker-empty";
    emptyState.textContent = "No matches.";
    emptyState.hidden = true;
    panel.appendChild(emptyState);

    picker.appendChild(control);
    picker.appendChild(panel);
    source.hidden = true;

    function renderChips() {
      chipsHost.innerHTML = "";
      const checked = optionLabels.filter((label) => label.querySelector("input").checked);
      if (!checked.length) {
        const ph = document.createElement("span");
        ph.className = "ms-picker-placeholder";
        ph.textContent = placeholder;
        chipsHost.appendChild(ph);
        return;
      }
      checked.forEach((label) => {
        const input = label.querySelector("input");
        const span = label.querySelector("span");
        const name = span ? span.textContent.trim() : "";
        const chip = document.createElement("span");
        chip.className = "ms-picker-chip";
        const nameEl = document.createElement("span");
        nameEl.textContent = name;
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.setAttribute("aria-label", `Remove ${name}`);
        removeBtn.textContent = "×";
        removeBtn.addEventListener("click", (event) => {
          event.stopPropagation();
          input.checked = false;
          renderChips();
        });
        chip.appendChild(nameEl);
        chip.appendChild(removeBtn);
        chipsHost.appendChild(chip);
      });
    }

    function applySearch() {
      const q = searchInput.value.trim().toLowerCase();
      let anyVisible = false;
      optionLabels.forEach((label) => {
        const visible = !q || label.dataset.msSearch.includes(q);
        label.hidden = !visible;
        if (visible) anyVisible = true;
      });
      emptyState.hidden = anyVisible;
    }

    function openPanel() {
      panel.hidden = false;
      picker.classList.add("is-open");
      searchInput.value = "";
      applySearch();
      searchInput.focus();
    }
    function closePanel() {
      panel.hidden = true;
      picker.classList.remove("is-open");
    }
    function togglePanel() {
      if (panel.hidden) openPanel(); else closePanel();
    }

    control.addEventListener("click", (event) => {
      event.stopPropagation();
      togglePanel();
    });
    searchInput.addEventListener("input", applySearch);
    searchInput.addEventListener("click", (event) => event.stopPropagation());
    list.addEventListener("change", renderChips);
    document.addEventListener("click", (event) => {
      if (!panel.hidden && !picker.contains(event.target)) closePanel();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !panel.hidden) closePanel();
    });

    renderChips();
  });
});
