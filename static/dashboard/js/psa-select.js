/* Selecting rows on the PSA list, for archiving and restoring.
 *
 * The checkboxes live in the table and point at the bulk form with
 * form="psaBulkForm", so the markup stays a plain table and the page
 * still works with JavaScript off -- without this file you tick rows and
 * press Archive, and only the "select all matching" shortcut is missing.
 *
 * What this adds:
 *   - a header box that selects the page, and shows a dash when only
 *     some of the page is picked;
 *   - shift-click to take a run of rows, the way a file list does;
 *   - once the whole page is picked, the offer to take every row the
 *     current filters match, not just the twenty on screen;
 *   - a bar that appears only when something is selected, so it never
 *     sits there taking up room on a list nobody is selecting from.
 */
(function () {
  var form = document.getElementById("psaBulkForm");
  var table = document.getElementById("psaTable");
  if (!form || !table) return;

  var boxes = Array.prototype.slice.call(table.querySelectorAll(".psa-pick"));
  if (!boxes.length) return;

  var all = document.getElementById("psaPickAll");
  var count = document.getElementById("psaPickCount");
  var clear = document.getElementById("psaPickClear");
  var every = document.getElementById("psaPickEvery");
  var everyNote = document.getElementById("psaPickEveryNote");
  var everyFlag = document.getElementById("psaPickAllMatching");
  var anchor = null;          // last box clicked, for shift-click runs

  function picked() {
    return boxes.filter(function (b) { return b.checked; });
  }

  /* Taking everything matching is a claim about the filters, not about
     the rows on screen, so any change to the selection drops it. */
  function forgetEveryMatching() {
    if (everyFlag) everyFlag.value = "";
    if (every) every.hidden = picked().length !== boxes.length;
    if (everyNote) everyNote.hidden = true;
  }

  function sync() {
    var n = picked().length;
    var takingAll = everyFlag && everyFlag.value === "1";

    form.hidden = n === 0;
    if (all) {
      all.checked = n === boxes.length && n > 0;
      all.indeterminate = n > 0 && n < boxes.length;
    }
    if (count) {
      count.textContent = takingAll
        ? "Every matching agreement selected"
        : n + " selected";
    }
    boxes.forEach(function (b) {
      b.closest("tr").classList.toggle("is-picked", b.checked);
    });
    if (every && !takingAll) every.hidden = n !== boxes.length;
  }

  boxes.forEach(function (box, i) {
    box.addEventListener("click", function (event) {
      if (event.shiftKey && anchor !== null) {
        var from = Math.min(anchor, i), to = Math.max(anchor, i);
        for (var j = from; j <= to; j++) boxes[j].checked = box.checked;
      }
      anchor = i;
      forgetEveryMatching();
      sync();
    });
  });

  if (all) {
    all.addEventListener("change", function () {
      boxes.forEach(function (b) { b.checked = all.checked; });
      anchor = null;
      forgetEveryMatching();
      sync();
    });
  }

  if (clear) {
    clear.addEventListener("click", function () {
      boxes.forEach(function (b) { b.checked = false; });
      anchor = null;
      forgetEveryMatching();
      sync();
    });
  }

  if (every && everyFlag) {
    every.addEventListener("click", function () {
      everyFlag.value = "1";
      every.hidden = true;
      if (everyNote) everyNote.hidden = false;
      sync();
    });
  }

  /* Say how many are going, and name the one when it is only one --
     "Archive 1 agreement?" tells you less than the reference does. */
  form.addEventListener("submit", function (event) {
    var button = event.submitter;
    if (!button || !button.name) return;
    var verb = button.value === "archive" ? "Archive" : "Restore";
    var taking = everyFlag && everyFlag.value === "1";
    var chosen = picked();
    var what;
    if (taking) {
      what = "every agreement matching the current filters";
    } else if (chosen.length === 1) {
      what = chosen[0].dataset.ref || "this agreement";
    } else {
      what = chosen.length + " agreements";
    }
    var tail = button.value === "archive"
      ? " They stay exactly as they are - archiving only takes them off the list."
      : " They go back on the list.";
    if (!window.confirm(verb + " " + what + "?" + tail)) event.preventDefault();
  });

  sync();
})();
