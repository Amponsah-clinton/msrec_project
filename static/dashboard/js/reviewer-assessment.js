// MSREC Reviewer — Ethical Review Assessment Form
// Two small pieces of polish that don't need a server round trip:
// showing/hiding the "describe the conflict" textarea, and a live
// "answered X of 10" progress readout on the checklist.
(function () {
  var form = document.getElementById("assessmentForm");
  if (!form) return;

  var coiDetailsWrap = document.getElementById("coiDetailsWrap");
  var coiRadios = form.querySelectorAll('input[name="coi_choice"]');
  function syncCoiDetails() {
    var conflict = form.querySelector('input[name="coi_choice"]:checked');
    var show = !!conflict && conflict.value === "conflict";
    if (coiDetailsWrap) coiDetailsWrap.hidden = !show;
  }
  coiRadios.forEach(function (radio) { radio.addEventListener("change", syncCoiDetails); });
  syncCoiDetails();

  var checklistInputs = form.querySelectorAll('input[name^="checklist_"]');
  var checklistTotal = new Set(Array.prototype.map.call(checklistInputs, function (i) { return i.name; })).size;
  var progressFill = document.getElementById("assessProgressFill");
  var progressCount = document.getElementById("assessProgressCount");
  function syncProgress() {
    var answered = new Set();
    checklistInputs.forEach(function (input) {
      if (input.checked) answered.add(input.name);
    });
    if (progressFill) progressFill.style.width = (checklistTotal ? (answered.size / checklistTotal) * 100 : 0) + "%";
    if (progressCount) progressCount.textContent = answered.size + " of " + checklistTotal + " answered";
  }
  checklistInputs.forEach(function (input) { input.addEventListener("change", syncProgress); });
  syncProgress();

  // Submit confirmation is handled by the shared confirm-modal in
  // script.js via this form's data-confirm attribute -- no native
  // window.confirm() here.
})();
