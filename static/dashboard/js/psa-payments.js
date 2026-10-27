// Recording a payment from the PSA list (templates/psa/_payment_dialog.html).
//
// One dialog serves every row: the button carries the agreement, this fills
// the dialog in and points the form at that agreement's URL. Everything is
// checked again on the server (psa/forms.py parse_payment) -- what's here is
// to make the common case quick and the irreversible case obvious.
(function () {
  "use strict";

  var dialog = document.getElementById("psaPayDialog");
  var form = document.getElementById("psaPayForm");
  if (!dialog || !form || typeof dialog.showModal !== "function") return;

  var template = form.dataset.actionTemplate;   // .../psa/0/payments/add/
  var ref = document.getElementById("psaPayRef");
  var client = document.getElementById("psaPayClient");
  var owing = document.getElementById("psaPayOwing");
  var currency = document.getElementById("psaPayCurrency");
  var amount = document.getElementById("psaPayAmount");
  var amountHint = document.getElementById("psaPayAmountHint");
  var noteOpt = document.getElementById("psaPayNoteOpt");
  var noteHint = document.getElementById("psaPayNoteHint");
  var submit = document.getElementById("psaPaySubmit");
  var kinds = form.querySelectorAll("[data-psa-kind]");
  var row = null;                               // the agreement being paid

  function money(value) {
    var n = parseFloat(value);
    if (isNaN(n)) return "";
    return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  // A refund is capped at what has come in, and needs a reason; a payment
  // is pre-filled with what's still owing, which is usually the amount.
  function applyKind() {
    var refund = form.querySelector("[data-psa-kind]:checked").value === "refund";
    var paid = row ? parseFloat(row.paid || "0") : 0;
    form.classList.toggle("is-refund", refund);
    noteOpt.hidden = refund;
    if (refund) {
      amountHint.textContent = paid > 0
        ? "At most " + (row.currency || "") + " " + money(paid) + " has been received."
        : "Nothing has been received on this agreement yet.";
      noteHint.textContent = "Say what the refund or correction is for.";
      submit.textContent = "Save refund";
    } else {
      amountHint.textContent = row && row.owing
        ? (row.currency || "") + " " + money(row.owing) + " is still owing."
        : "";
      noteHint.textContent = "Whatever would let someone find this payment again.";
      submit.textContent = "Save entry";
    }
  }

  function open(button) {
    row = button.dataset;
    form.action = template.replace(/\/0\/payments\/add\/$/, "/" + row.pk + "/payments/add/");
    ref.textContent = row.ref || "";
    client.textContent = row.client || "";
    owing.textContent = row.owingText || "";
    currency.textContent = row.currency || "";
    form.querySelector('[data-psa-kind][value="received"]').checked = true;
    amount.value = row.owing || "";
    form.querySelector("#psaPayNote").value = "";
    submit.disabled = false;
    applyKind();
    dialog.showModal();
    // The amount is the one field that is usually changed.
    amount.focus();
    amount.select();
  }

  document.querySelectorAll("[data-psa-pay]").forEach(function (button) {
    button.addEventListener("click", function () { open(button); });
  });
  kinds.forEach(function (input) { input.addEventListener("change", applyKind); });
  form.querySelectorAll("[data-psa-pay-close]").forEach(function (button) {
    button.addEventListener("click", function () { dialog.close(); });
  });

  // A second click would be a second payment that can't be taken back.
  form.addEventListener("submit", function () {
    submit.disabled = true;
    submit.textContent = "Saving…";
  });

  // Clicking the backdrop closes it, the way the other dialogs behave.
  dialog.addEventListener("click", function (event) {
    if (event.target === dialog) dialog.close();
  });
})();
