/* PSA create / edit form (templates/psa/admin_form.html).
 *
 *  - Deliverables: there is always one empty line at the end; typing in it
 *    opens the next. Enter moves down, Backspace on an empty line moves up,
 *    and x removes a line. Blank lines are not posted.
 *  - Balance due = fee - deposit, worked out as you type.
 *  - "Other" payment basis asks what it is.
 *  - "Sign & send" checks everything the client will be asked to accept;
 *    "Save draft" only needs the client's name. The server re-checks both
 *    (psa/forms.py).
 */
(function () {
  var form = document.getElementById("psaForm");
  if (!form) return;

  var MAX_DELIVERABLES = 30;
  function $(id) { return document.getElementById(id); }

  // ---------------------------------------------------------------- deliverables
  var list = $("psaDeliverableList");
  var tpl = $("psaDeliverableTpl");
  var addBtn = $("psaAddDeliverable");
  var countOut = $("psaDelivCount");
  var uid = list.children.length;

  function rows() { return Array.prototype.slice.call(list.querySelectorAll(".psa-deliv-row")); }
  function input(row) { return row.querySelector("input"); }
  function blank(row) { return !input(row).value.trim(); }
  function filled() { return rows().filter(function (r) { return !blank(r); }); }

  function newRow() {
    var row = tpl.content.firstElementChild.cloneNode(true);
    uid += 1;
    input(row).id = "psaDeliverable" + uid;   // unique for the life of the page
    list.appendChild(row);
    return row;
  }

  function renumber() {
    var all = rows();
    all.forEach(function (row, i) {
      var n = i + 1, last = i === all.length - 1;
      row.querySelector(".psa-deliv-n").textContent = n + ".";
      input(row).setAttribute("aria-label", "Deliverable " + n);
      var rm = row.querySelector("[data-remove]");
      rm.setAttribute("aria-label", "Remove deliverable " + n);
      // The empty line at the end is where the next item goes.
      rm.hidden = last && blank(row);
    });
    var n = filled().length;
    countOut.textContent = n ? n + " deliverable" + (n === 1 ? "" : "s") : "";
    addBtn.disabled = n >= MAX_DELIVERABLES;
  }

  // Exactly one empty line at the end.
  function ensureTrailingBlank() {
    var all = rows();
    var last = all[all.length - 1];
    if (!last || !blank(last)) {
      if (filled().length < MAX_DELIVERABLES) newRow();
    } else {
      for (var i = all.length - 2; i >= 0 && blank(all[i]); i--) {
        if (document.activeElement === input(all[i])) break;
        all[i].remove();
      }
    }
    renumber();
  }

  list.addEventListener("input", function (e) {
    if (e.target.name === "deliverables") ensureTrailingBlank();
  });

  list.addEventListener("keydown", function (e) {
    if (e.target.name !== "deliverables") return;
    var all = rows();
    var row = e.target.closest(".psa-deliv-row");
    var i = all.indexOf(row);
    if (e.key === "Enter") {
      e.preventDefault();               // never submits the form from here
      if (!e.target.value.trim()) return;
      var next = all[i + 1] || newRow();
      renumber();
      input(next).focus();
    } else if (e.key === "Backspace" && !e.target.value && i > 0) {
      e.preventDefault();
      var prev = input(all[i - 1]);
      if (i < all.length - 1) row.remove();
      ensureTrailingBlank();
      prev.focus();
      prev.setSelectionRange(prev.value.length, prev.value.length);
    } else if (e.key === "ArrowDown" && all[i + 1]) {
      e.preventDefault(); input(all[i + 1]).focus();
    } else if (e.key === "ArrowUp" && all[i - 1]) {
      e.preventDefault(); input(all[i - 1]).focus();
    }
  });

  list.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-remove]");
    if (!btn) return;
    var all = rows();
    var row = btn.closest(".psa-deliv-row");
    var i = all.indexOf(row);
    var focusTo = all[i + 1] || all[i - 1];
    row.remove();
    ensureTrailingBlank();
    if (focusTo && focusTo.isConnected) input(focusTo).focus();
  });

  // Once the person moves on, drop lines they emptied (keeping the last).
  list.addEventListener("focusout", function () {
    setTimeout(function () {
      if (list.contains(document.activeElement)) return;
      rows().slice(0, -1).forEach(function (r) { if (blank(r)) r.remove(); });
      ensureTrailingBlank();
    }, 0);
  });

  addBtn.addEventListener("click", function () {
    var all = rows();
    var last = all[all.length - 1];
    var target = last && blank(last) ? last : newRow();
    renumber();
    input(target).focus();
  });

  ensureTrailingBlank();

  // ---------------------------------------------------------------- money
  var fee = $("psaFeeIn"), deposit = $("psaDepositIn"), currency = $("psaCurrencyIn");
  var balance = $("psaBalanceOut");

  function num(v) {
    v = (v || "").replace(/,/g, "").trim();
    if (!v) return null;
    var n = Number(v);
    return isFinite(n) && n >= 0 ? n : NaN;
  }
  function fmt(n) { return n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  function updateBalance() {
    var f = num(fee.value), d = num(deposit.value) || 0;
    if (f === null || isNaN(f) || isNaN(d)) balance.value = "";
    else if (d > f) balance.value = "Deposit is more than the fee";
    else balance.value = currency.value + " " + fmt(f - d);
  }
  [fee, deposit].forEach(function (el) {
    el.addEventListener("input", updateBalance);
    el.addEventListener("blur", function () {
      var n = num(el.value);
      if (n !== null && !isNaN(n)) el.value = n.toFixed(2);
      updateBalance();
    });
  });
  currency.addEventListener("change", updateBalance);
  updateBalance();

  // ---------------------------------------------------------------- basis
  var otherWrap = $("psaBasisOtherWrap"), otherIn = $("psaBasisOtherIn");
  form.querySelectorAll('input[name="payment_basis"]').forEach(function (r) {
    r.addEventListener("change", function () {
      var other = r.value === "other" && r.checked;
      otherWrap.hidden = !other;
      if (other) otherIn.focus();
    });
  });

  // ---------------------------------------------------------------- dates
  var start = $("psaStartDateIn"), end = $("psaCompletionDateIn"), termOut = $("psaTermLength");
  function updateTerm() {
    end.min = start.value || "";
    termOut.textContent = "";
    if (start.value && end.value && end.value >= start.value) {
      var days = Math.round((new Date(end.value) - new Date(start.value)) / 86400000);
      termOut.textContent = days === 0 ? "Same day" : days + " day" + (days === 1 ? "" : "s");
    }
  }
  start.addEventListener("change", updateTerm);
  end.addEventListener("change", updateTerm);
  updateTerm();

  // ---------------------------------------------------------------- re-sign
  var resign = $("psaResignBtn");
  if (resign) resign.addEventListener("click", function () {
    var wrap = $("psaResignWrap");
    wrap.hidden = !wrap.hidden;
    resign.setAttribute("aria-expanded", wrap.hidden ? "false" : "true");
    resign.textContent = wrap.hidden ? "Replace signature" : "Keep current signature";
    window.dispatchEvent(new Event("resize"));   // the pad measures itself once visible
  });

  // ---------------------------------------------------------------- submit
  var pad = $("companySigpad");
  var hasSignature = form.dataset.hasSignature === "1";
  var summary = $("psaFormSummary");

  function val(id) { return $(id).value.trim(); }
  function basis() { var r = form.querySelector('input[name="payment_basis"]:checked'); return r ? r.value : ""; }
  function digits(s) { return (s.match(/\d/g) || []).length; }
  function emailOk(s) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s); }

  function validate(sending) {
    var first = null;
    function check(id, msg, errId) {
      var el = $(id);
      el.setAttribute("aria-invalid", msg ? "true" : "false");
      $(errId || id + "Err").textContent = msg || "";
      if (msg) first = first || el;
    }
    form.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], textarea').forEach(function (i) {
      if (i.name !== "deliverables" && !i.readOnly) i.value = i.value.trim();
    });

    var email = val("psaClientEmailIn"), phone = val("psaClientPhoneIn");
    var f = num(fee.value), d = num(deposit.value);

    check("psaClientNameIn", val("psaClientNameIn") ? "" : "Enter the client's full name.");
    check("psaClientEmailIn", email ? (emailOk(email) ? "" : "Enter a valid email address.")
      : (sending ? "The client's email is needed to send the agreement." : ""));
    check("psaClientPhoneIn", phone && (digits(phone) < 7 || digits(phone) > 15) ? "Enter a valid phone number." : "");
    check("psaFeeIn", isNaN(f) ? "Enter the fee as a number, e.g. 2500.00." : (sending && !f ? "Enter the agreed fee." : ""));
    check("psaDepositIn", isNaN(d) ? "Enter the deposit as a number, or leave it blank."
      : (f && d && d > f ? "The deposit can't be more than the agreed fee." : ""));
    check("psaCompletionDateIn", start.value && end.value && end.value < start.value
      ? "The completion date can't be before the start date."
      : (sending && !end.value ? "Enter the expected completion date." : ""));
    check("psaBasisOtherIn", basis() === "other" && !val("psaBasisOtherIn") ? "Say how the fee is charged." : "");
    check("psaAgreementDateIn", sending && !val("psaAgreementDateIn") ? "Enter the agreement date." : "");
    check("psaStartDateIn", sending && !start.value ? "Enter the start date." : "");
    check("psaServiceTitleIn", sending && !val("psaServiceTitleIn") ? "Give the service or project a title." : "");
    check("psaScheduleIn", sending && !val("psaScheduleIn") ? "Give the payment due date or schedule." : "");

    var delivErr = sending && !filled().length ? "List at least one deliverable." : "";
    $("psaDeliverablesErr").textContent = delivErr;
    if (delivErr) first = first || input(rows()[0]);

    var basisErr = sending && !basis() ? "Choose how the fee is charged." : "";
    $("psaBasisErr").textContent = basisErr;
    if (basisErr) first = first || $("psaBasisPick").querySelector("input");

    // Replacing a signature already on file is optional.
    var sigMissing = sending && !hasSignature && pad.sigpad.isEmpty();
    pad.classList.toggle("has-error", sigMissing);
    $("companySigError").textContent = sigMissing ? "Sign for Metascholar Limited before sending." : "";
    if (sigMissing) first = first || pad;
    return first;
  }

  form.addEventListener("submit", function (e) {
    var submitter = e.submitter || document.activeElement;
    var sending = submitter && submitter.value === "send";
    var first = validate(sending);
    if (first) {
      e.preventDefault();
      summary.textContent = sending
        ? "Some details are still needed before this can be sent. They're marked below."
        : "Please fix the fields marked below.";
      first.scrollIntoView({ block: "center", behavior: "smooth" });
      if (first.focus) first.focus({ preventScroll: true });
      return;
    }
    if (sending && !window.confirm("Send this agreement to " + val("psaClientEmailIn") + "?\n\nThey'll get an email with a link to review and sign it.")) {
      e.preventDefault();
      return;
    }
    // Don't post the empty last line.
    rows().forEach(function (r) { if (blank(r)) input(r).disabled = true; });
    form.querySelectorAll('button[type="submit"]').forEach(function (b) { b.disabled = true; });
    // Disabled buttons aren't posted, so carry the chosen action.
    var keep = document.createElement("input");
    keep.type = "hidden"; keep.name = "action"; keep.value = sending ? "send" : "draft";
    form.appendChild(keep);
    submitter.textContent = sending ? "Sending…" : "Saving…";
  });
})();
