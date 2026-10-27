/* PSA create / edit form (templates/psa/admin_form.html).
 *
 *  - Deliverables: there is always one empty row at the end. Typing in it
 *    adds the next one, Enter moves down, Backspace on an empty row goes
 *    back up, and the x removes a row. Blank rows are ignored on save.
 *  - Balance = fee - deposit, live; the deposit can't exceed the fee.
 *  - "Other" payment basis asks what it is.
 *  - The progress list ticks off each section as it's completed.
 *  - "Sign & send" checks everything the client will be asked to accept
 *    before posting; "Save draft" only needs the client's name. The server
 *    re-checks both (psa/forms.py).
 */
(function () {
  var form = document.getElementById("psaForm");
  if (!form) return;

  var MAX_DELIVERABLES = 30;
  var list = document.getElementById("psaDeliverableList");
  var tpl = document.getElementById("psaDeliverableTpl");
  var addBtn = document.getElementById("psaAddDeliverable");
  var countOut = document.getElementById("psaDelivCount");
  var uid = list.children.length;

  function $(id) { return document.getElementById(id); }
  function rows() { return Array.prototype.slice.call(list.querySelectorAll(".psa-deliv-row")); }
  function filled() { return rows().filter(function (r) { return r.querySelector("input").value.trim(); }); }

  // ---------------------------------------------------------------- deliverables
  function newRow(value) {
    var row = tpl.content.firstElementChild.cloneNode(true);
    var input = row.querySelector("input");
    uid += 1;
    input.id = "psaDeliverable" + uid;   // unique for the life of the page
    input.value = value || "";
    list.appendChild(row);
    return row;
  }

  function renumber() {
    var all = rows();
    all.forEach(function (row, i) {
      var n = i + 1;
      var input = row.querySelector("input");
      var blank = !input.value.trim();
      row.querySelector(".num").textContent = n;
      input.setAttribute("aria-label", "Deliverable " + n);
      input.placeholder = n === 1 ? "e.g. Literature search across 4 databases" : (blank && i === all.length - 1 ? "Add another deliverable…" : "");
      var rm = row.querySelector("[data-remove]");
      rm.setAttribute("aria-label", "Remove deliverable " + n);
      // The trailing empty row is where the next item goes, so it can't be removed.
      rm.hidden = blank && i === all.length - 1;
      row.classList.toggle("is-blank", blank && i === all.length - 1 && all.length > 1);
    });
    var n = filled().length;
    countOut.textContent = n ? n + " deliverable" + (n === 1 ? "" : "s") + (n >= MAX_DELIVERABLES ? " (maximum reached)" : "") : "No deliverables yet";
    addBtn.disabled = n >= MAX_DELIVERABLES;
    $("psaMiniDeliv").textContent = n;
    updateProgress();
  }

  // Exactly one empty row at the end -- the "auto addition".
  function ensureTrailingBlank() {
    var all = rows();
    var last = all[all.length - 1];
    if (!last || last.querySelector("input").value.trim()) {
      if (filled().length < MAX_DELIVERABLES) newRow("");
    } else {
      // Collapse extra empty rows at the end down to one.
      for (var i = all.length - 2; i >= 0 && !all[i].querySelector("input").value.trim() && all.length > 1; i--) {
        if (document.activeElement === all[i].querySelector("input")) break;
        all[i].remove();
        all.splice(i, 1);
      }
    }
    renumber();
  }

  list.addEventListener("input", function (e) {
    if (e.target.name === "deliverables") ensureTrailingBlank();
  });

  list.addEventListener("keydown", function (e) {
    if (e.target.name !== "deliverables") return;
    var row = e.target.closest(".psa-deliv-row");
    var all = rows();
    var i = all.indexOf(row);
    if (e.key === "Enter") {
      e.preventDefault();               // never submits the form from here
      if (!e.target.value.trim()) return;
      var next = all[i + 1] || newRow("");
      renumber();
      next.querySelector("input").focus();
    } else if (e.key === "Backspace" && !e.target.value && i > 0) {
      e.preventDefault();
      var prev = all[i - 1].querySelector("input");
      if (i < all.length - 1) row.remove();
      ensureTrailingBlank();
      prev.focus();
      prev.setSelectionRange(prev.value.length, prev.value.length);
    } else if (e.key === "ArrowDown" && all[i + 1]) {
      e.preventDefault(); all[i + 1].querySelector("input").focus();
    } else if (e.key === "ArrowUp" && all[i - 1]) {
      e.preventDefault(); all[i - 1].querySelector("input").focus();
    }
  });

  list.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-remove]");
    if (!btn) return;
    var row = btn.closest(".psa-deliv-row");
    var all = rows();
    var focusTo = all[all.indexOf(row) + 1] || all[all.indexOf(row) - 1];
    row.remove();
    ensureTrailingBlank();
    if (focusTo && focusTo.isConnected) focusTo.querySelector("input").focus();
  });

  list.addEventListener("focusout", function () {
    // Once the person moves on, tidy away lines they emptied, keeping the
    // one blank line at the end.
    setTimeout(function () {
      if (list.contains(document.activeElement)) return;
      var all = rows();
      all.slice(0, -1).forEach(function (r) { if (!r.querySelector("input").value.trim()) r.remove(); });
      ensureTrailingBlank();
    }, 0);
  });

  addBtn.addEventListener("click", function () {
    var all = rows();
    var last = all[all.length - 1];
    var target = last && !last.querySelector("input").value.trim() ? last : newRow("");
    renumber();
    target.querySelector("input").focus();
  });

  ensureTrailingBlank();

  // ---------------------------------------------------------------- money
  var fee = $("psaFeeIn"), deposit = $("psaDepositIn"), currency = $("psaCurrencyIn");
  var balanceOut = $("psaBalanceOut");

  function num(v) {
    v = (v || "").replace(/,/g, "").trim();
    if (!v) return null;
    var n = Number(v);
    return isFinite(n) && n >= 0 ? n : NaN;
  }
  function fmt(n) { return n.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

  function updateMoney() {
    var cur = currency.value;
    document.querySelectorAll("[data-currency-label]").forEach(function (el) { el.textContent = cur; });
    var f = num(fee.value), d = num(deposit.value);
    var b = balanceOut.querySelector("b");
    balanceOut.classList.remove("bad");
    if (f === null || isNaN(f)) {
      b.textContent = "—";
    } else if (isNaN(d)) {
      b.textContent = "—";
    } else if ((d || 0) > f) {
      balanceOut.classList.add("bad");
      b.textContent = "Deposit is more than the fee";
    } else {
      b.textContent = cur + " " + fmt(f - (d || 0));
    }
    $("psaMiniFee").textContent = f === null || isNaN(f) ? "—" : cur + " " + fmt(f);
    $("psaMiniDeposit").textContent = d === null || isNaN(d) ? "—" : cur + " " + fmt(d);
  }
  [fee, deposit].forEach(function (el) {
    el.addEventListener("input", updateMoney);
    // Tidy to two decimals once they leave the field.
    el.addEventListener("blur", function () {
      var n = num(el.value);
      if (n !== null && !isNaN(n)) el.value = n.toFixed(2);
      updateMoney();
    });
  });
  currency.addEventListener("change", updateMoney);
  updateMoney();

  // ---------------------------------------------------------------- basis
  var otherWrap = $("psaBasisOtherWrap"), otherIn = $("psaBasisOtherIn");
  document.querySelectorAll('input[name="payment_basis"]').forEach(function (r) {
    r.addEventListener("change", function () {
      var other = r.value === "other" && r.checked;
      otherWrap.hidden = !other;
      if (other) otherIn.focus();
      updateProgress();
    });
  });

  // ---------------------------------------------------------------- dates
  var start = $("psaStartDateIn"), end = $("psaCompletionDateIn"), termOut = $("psaTermLength");
  function updateTerm() {
    end.min = start.value || "";
    termOut.textContent = "";
    if (start.value && end.value) {
      var days = Math.round((new Date(end.value) - new Date(start.value)) / 86400000);
      termOut.textContent = days < 0 ? "" : (days === 0 ? "Same day" : days + " day" + (days === 1 ? "" : "s") + " (about " + Math.max(1, Math.round(days / 7)) + " week" + (Math.round(days / 7) === 1 ? "" : "s") + ")");
    }
  }
  start.addEventListener("change", updateTerm);
  end.addEventListener("change", updateTerm);
  updateTerm();

  // ---------------------------------------------------------------- mirror + progress
  document.querySelectorAll("[data-mirror]").forEach(function (out) {
    var src = $(out.dataset.mirror);
    function sync() { out.textContent = src.value.trim() || "—"; }
    src.addEventListener("input", sync);
    sync();
  });

  var pad = $("companySigpad");
  var hasSignature = form.dataset.hasSignature === "1";
  function val(id) { var el = $(id); return el ? el.value.trim() : ""; }
  function basis() { var r = form.querySelector('input[name="payment_basis"]:checked'); return r ? r.value : ""; }

  function stepDone(n) {
    switch (n) {
      case 1: return !!(val("psaAgreementDateIn") && val("psaClientNameIn") && val("psaClientEmailIn"));
      case 2: return !!(val("psaStartDateIn") && val("psaCompletionDateIn"));
      case 3: return !!(val("psaServiceTitleIn") && filled().length);
      case 4: return !!(num(fee.value) && basis() && (basis() !== "other" || val("psaBasisOtherIn")) && val("psaScheduleIn"));
      case 5: return hasSignature || (pad && !pad.sigpad.isEmpty());
    }
    return false;
  }
  function updateProgress() {
    document.querySelectorAll("#psaProgress li").forEach(function (li) {
      li.classList.toggle("done", stepDone(Number(li.dataset.for)));
    });
  }
  form.addEventListener("input", updateProgress);
  form.addEventListener("change", updateProgress);
  form.addEventListener("sigpad:change", updateProgress);
  updateProgress();

  // ---------------------------------------------------------------- re-sign
  var resign = $("psaResignBtn");
  if (resign) resign.addEventListener("click", function () {
    var wrap = $("psaResignWrap");
    wrap.hidden = !wrap.hidden;
    resign.setAttribute("aria-expanded", wrap.hidden ? "false" : "true");
    resign.textContent = wrap.hidden ? "Sign again" : "Keep current signature";
    // The pad measures its canvas when it becomes visible.
    window.dispatchEvent(new Event("resize"));
  });

  // ---------------------------------------------------------------- submit
  var summary = $("psaFormSummary");

  function setErr(input, errId, msg) {
    var err = $(errId);
    if (input) input.setAttribute("aria-invalid", msg ? "true" : "false");
    if (err) err.textContent = msg || "";
    return !msg;
  }
  function digits(s) { return (s.match(/\d/g) || []).length; }
  function emailOk(s) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(s); }

  function validate(sending) {
    var first = null;
    function check(id, errId, msg) {
      var input = $(id);
      if (!setErr(input, errId, msg)) first = first || input;
    }
    form.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], textarea').forEach(function (i) {
      if (i.name !== "deliverables") i.value = i.value.trim();
    });

    var email = val("psaClientEmailIn"), phone = val("psaClientPhoneIn");
    var f = num(fee.value), d = num(deposit.value);

    check("psaClientNameIn", "psaClientNameInErr", val("psaClientNameIn") ? "" : "Enter the client's full name.");
    check("psaClientEmailIn", "psaClientEmailInErr",
      email ? (emailOk(email) ? "" : "Enter a valid email address.") : (sending ? "The client's email is needed to send the agreement." : ""));
    check("psaClientPhoneIn", "psaClientPhoneInErr",
      phone && (digits(phone) < 7 || digits(phone) > 15) ? "Enter a valid phone number (7–15 digits)." : "");
    check("psaFeeIn", "psaFeeInErr",
      isNaN(f) ? "Enter the fee as a number, e.g. 2500.00." : (sending && !f ? "Enter the agreed fee." : ""));
    check("psaDepositIn", "psaDepositInErr",
      isNaN(d) ? "Enter the deposit as a number, or leave it blank." : (f && d && d > f ? "The deposit can't be more than the agreed fee." : ""));
    check("psaCompletionDateIn", "psaCompletionDateInErr",
      start.value && end.value && end.value < start.value ? "The completion date can't be before the start date." :
      (sending && !end.value ? "Enter the expected completion date." : ""));
    if (basis() === "other") check("psaBasisOtherIn", "psaBasisOtherInErr", val("psaBasisOtherIn") ? "" : "Say how the fee is charged.");

    if (sending) {
      check("psaAgreementDateIn", "psaAgreementDateInErr", val("psaAgreementDateIn") ? "" : "Enter the agreement date.");
      check("psaStartDateIn", "psaStartDateInErr", start.value ? "" : "Enter the start date.");
      check("psaServiceTitleIn", "psaServiceTitleInErr", val("psaServiceTitleIn") ? "" : "Give the service or project a title.");
      check("psaScheduleIn", "psaScheduleInErr", val("psaScheduleIn") ? "" : "Give the payment due date or schedule.");

      var delivErr = filled().length ? "" : "List at least one deliverable.";
      $("psaDeliverablesErr").textContent = delivErr;
      if (delivErr) first = first || rows()[0].querySelector("input");

      var basisErr = basis() ? "" : "Choose how the fee is charged.";
      $("psaBasisErr").textContent = basisErr;
      if (basisErr) first = first || $("psaBasisPick").querySelector("input");

      // Re-signing is optional when a signature is already on file.
      var sigEmpty = !hasSignature && pad.sigpad.isEmpty();
      pad.classList.toggle("has-error", sigEmpty);
      $("companySigError").textContent = sigEmpty ? "Sign for Metascholar Limited before sending — draw your signature or type your name." : "";
      if (sigEmpty) first = first || pad;
    } else {
      ["psaAgreementDateIn", "psaStartDateIn", "psaServiceTitleIn", "psaScheduleIn"].forEach(function (id) { setErr($(id), id + "Err", ""); });
      $("psaDeliverablesErr").textContent = "";
      $("psaBasisErr").textContent = "";
      $("companySigError").textContent = "";
      pad.classList.remove("has-error");
    }
    return first;
  }

  form.addEventListener("submit", function (e) {
    var submitter = e.submitter || document.activeElement;
    var sending = submitter && submitter.value === "send";
    var first = validate(sending);
    if (first) {
      e.preventDefault();
      summary.textContent = sending
        ? "Some details are still needed before this can be sent — they're highlighted below."
        : "Please fix the highlighted fields.";
      first.scrollIntoView({ block: "center", behavior: "smooth" });
      if (first.focus) first.focus({ preventScroll: true });
      updateProgress();
      document.querySelectorAll("#psaProgress li").forEach(function (li) {
        li.classList.toggle("bad", sending && !stepDone(Number(li.dataset.for)));
      });
      return;
    }
    if (sending && !window.confirm("Send this agreement to " + val("psaClientEmailIn") + "?\n\nThey'll get an email with a link to review and sign it.")) {
      e.preventDefault();
      return;
    }
    // Don't post the trailing blank line(s).
    rows().forEach(function (r) { if (!r.querySelector("input").value.trim()) r.querySelector("input").disabled = true; });
    form.querySelectorAll('button[type="submit"]').forEach(function (b) { b.disabled = true; });
    // Keep the chosen action: disabled buttons aren't posted.
    var keep = document.createElement("input");
    keep.type = "hidden"; keep.name = "action"; keep.value = sending ? "send" : "draft";
    form.appendChild(keep);
    submitter.innerHTML = sending ? "Sending…" : "Saving…";
  });
})();
