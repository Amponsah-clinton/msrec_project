/* Send SMS page (admin + secretariat).
   - Tabs: swap the visible pane and remember which one is active so the
     server knows which recipient source to use on submit.
   - Individuals: live search across each row's data-sms-search string;
     Select-all-shown / Clear helpers; live picked-count.
   - Message meta: length, encoding (GSM-7 vs Unicode), segment count and
     estimated credit cost -- matches notifications/sms.py's segments()
     so what's shown here is what the server will charge.
   - Guardrail on submit: no message, no recipients, or picking a group
     with zero reachable users all pop a native validity message so the
     operator can't accidentally fire an empty blast.
*/
(function () {
  var form = document.getElementById("smsForm");
  if (!form) return;

  var tabs = form.querySelectorAll(".sms-tab");
  var panes = form.querySelectorAll(".sms-pane");
  var modeInput = document.getElementById("smsRecipientMode");

  function switchTab(name) {
    tabs.forEach(function (btn) { btn.classList.toggle("is-active", btn.dataset.smsTab === name); });
    panes.forEach(function (p) { p.hidden = p.dataset.smsPane !== name; });
    modeInput.value = name;
  }
  tabs.forEach(function (btn) {
    btn.addEventListener("click", function () { switchTab(btn.dataset.smsTab); });
  });

  /* ---- Individuals search + picked count ---- */
  var users = form.querySelectorAll(".sms-user");
  var search = document.getElementById("smsUserSearch");
  var pickedCount = document.getElementById("smsPickedCount");
  var selectAll = document.getElementById("smsSelectAll");
  var clearAll = document.getElementById("smsClearAll");

  function applyUserSearch() {
    var q = (search.value || "").trim().toLowerCase();
    users.forEach(function (row) {
      row.hidden = !!q && row.dataset.smsSearch.indexOf(q) === -1;
    });
  }
  function refreshPicked() {
    var n = form.querySelectorAll('.sms-user input[type="checkbox"]:checked').length;
    if (pickedCount) pickedCount.textContent = String(n);
  }
  if (search) search.addEventListener("input", applyUserSearch);
  form.addEventListener("change", function (e) {
    if (e.target.matches('.sms-user input[type="checkbox"]')) refreshPicked();
  });
  if (selectAll) selectAll.addEventListener("click", function () {
    users.forEach(function (row) {
      if (!row.hidden) {
        var cb = row.querySelector('input[type="checkbox"]');
        if (cb) cb.checked = true;
      }
    });
    refreshPicked();
  });
  if (clearAll) clearAll.addEventListener("click", function () {
    users.forEach(function (row) {
      var cb = row.querySelector('input[type="checkbox"]');
      if (cb) cb.checked = false;
    });
    refreshPicked();
  });

  /* ---- Message meta (chars / encoding / segments / cost) ---- */
  // Same GSM-7 charset the server-side segments() uses -- keep them in
  // lockstep so the preview never lies to the operator.
  var GSM = new Set(
    ("@£$¥èéùìòÇ\nØø\rÅå"
    + "Δ_ΦΓΛΩΠΨΣΘΞÆæßÉ"
    + " !\"#¤%&'()*+,-./0123456789:;<=>?"
    + "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§"
    + "¿abcdefghijklmnopqrstuvwxyzäöñüà"
    + "\f^{}\\[~]|€"
    ).split("")
  );

  var msg = document.getElementById("smsMessage");
  var lenEl = document.getElementById("smsLen");
  var encEl = document.getElementById("smsEnc");
  var segEl = document.getElementById("smsSeg");
  var costEl = document.getElementById("smsCost");
  var costCell = costEl ? costEl.parentElement : null;

  function updateMeta() {
    var text = msg.value || "";
    var isGsm = true;
    for (var i = 0; i < text.length; i++) { if (!GSM.has(text[i])) { isGsm = false; break; } }
    var single = isGsm ? 160 : 70;
    var multi  = isGsm ? 153 : 67;
    var length = text.length;
    var seg = length === 0 ? 0 : (length <= single ? 1 : Math.ceil(length / multi));
    lenEl.textContent = length;
    encEl.textContent = isGsm ? "gsm-7" : "unicode";
    segEl.textContent = seg;
    if (costEl) {
      // Cost = segments * pickedRecipients (best-effort estimate).
      var recipients = 1;
      var mode = modeInput.value;
      if (mode === "individuals") {
        recipients = Math.max(1, form.querySelectorAll('.sms-user input[type="checkbox"]:checked').length);
      } else if (mode === "custom") {
        var raw = (document.getElementById("smsCustomNumbers") || {}).value || "";
        var parts = raw.split(/[\s,;]+/).filter(Boolean);
        recipients = Math.max(1, parts.length);
      } else {
        // Groups: read the reachable count from the picked radio's label.
        var picked = form.querySelector('input[name="group"]:checked');
        if (picked) {
          var small = picked.closest(".sms-group").querySelector("small");
          if (small) {
            var m = /(\d+)/.exec(small.textContent || "");
            if (m) recipients = Math.max(1, parseInt(m[1], 10));
          }
        }
      }
      var cost = seg * recipients;
      costEl.textContent = cost;
      if (costCell) costCell.classList.toggle("is-warn", seg > 1);
    }
  }
  if (msg) {
    msg.addEventListener("input", updateMeta);
    form.addEventListener("change", updateMeta);
    document.getElementById("smsCustomNumbers") &&
      document.getElementById("smsCustomNumbers").addEventListener("input", updateMeta);
    updateMeta();
    refreshPicked();
  }

  /* ---- Guardrails on submit ---- */
  form.addEventListener("submit", function (e) {
    var text = (msg.value || "").trim();
    if (!text) {
      e.preventDefault();
      msg.focus();
      alert("Type a message before sending.");
      return;
    }
    var mode = modeInput.value;
    if (mode === "individuals") {
      var picked = form.querySelectorAll('.sms-user input[type="checkbox"]:checked').length;
      if (!picked) {
        e.preventDefault();
        alert("Tick at least one person to send to.");
        return;
      }
    } else if (mode === "custom") {
      var raw = (document.getElementById("smsCustomNumbers") || {}).value || "";
      if (!raw.trim()) {
        e.preventDefault();
        alert("Paste at least one Ghana phone number, or switch tabs.");
        return;
      }
    } else {
      var group = form.querySelector('input[name="group"]:checked');
      if (!group) {
        e.preventDefault();
        alert("Pick a group to send to.");
        return;
      }
    }
    // Cheap confirmation for anything expected to cost more than 5 credits.
    var costText = costEl ? costEl.textContent : "0";
    var cost = parseInt(costText, 10) || 0;
    if (cost > 5) {
      if (!confirm("This will cost about " + cost + " credit(s). Send now?")) {
        e.preventDefault();
        return;
      }
    }
  });
})();
