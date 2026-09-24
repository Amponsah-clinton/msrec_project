/* ==========================================================
   MSREC — Verify Approval page logic
   Looks approvals up against the real registry via the server
   (GET /verify/lookup/?q=…) and reads QR codes (camera & upload).
========================================================== */
(function () {
  "use strict";

  var pageEl = document.querySelector("main.verify-main");
  var LOOKUP_URL = (pageEl && pageEl.getAttribute("data-lookup-url")) || "/verify/lookup/";

  var STATUS_META = {
    approved: { label: "Approved & Valid", icon: "bi-patch-check-fill", tone: "approved" },
    conditional: { label: "Conditionally Approved", icon: "bi-exclamation-circle-fill", tone: "conditional" },
    expired: { label: "Approval Expired", icon: "bi-hourglass-bottom", tone: "expired" },
    suspended: { label: "Approval Suspended", icon: "bi-x-octagon-fill", tone: "suspended" },
    notfound: { label: "Not Found", icon: "bi-search", tone: "notfound" }
  };

  /* ---------------- Tabs ---------------- */
  var tabs = document.querySelectorAll(".verify-tab");
  var panels = document.querySelectorAll(".verify-panel");

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      tabs.forEach(function (t) { t.classList.remove("active"); t.setAttribute("aria-selected", "false"); });
      panels.forEach(function (p) { p.classList.remove("active"); });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      var mode = tab.getAttribute("data-mode");
      var panel = document.querySelector('.verify-panel[data-panel="' + mode + '"]');
      if (panel) panel.classList.add("active");
      if (mode !== "qr") stopCamera();
    });
  });

  /* ---------------- Number / code lookup ---------------- */
  document.querySelectorAll(".verify-btn[data-by]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var by = btn.getAttribute("data-by");
      var input = by === "number" ? document.getElementById("approvalNumber") : document.getElementById("verificationCode");
      runVerification(input.value);
    });
  });

  ["approvalNumber", "verificationCode"].forEach(function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("keydown", function (e) {
      if (e.key === "Enter") runVerification(el.value);
    });
  });

  var lookupSeq = 0;

  function setBusy(busy) {
    document.querySelectorAll(".verify-btn[data-by]").forEach(function (btn) {
      btn.disabled = busy;
      btn.classList.toggle("is-loading", busy);
    });
  }

  function runVerification(raw) {
    var query = (raw || "").trim();
    if (!query) {
      showToast("Enter an approval number or verification code first.");
      return;
    }
    var seq = ++lookupSeq;
    setBusy(true);

    fetch(LOOKUP_URL + "?q=" + encodeURIComponent(query), { headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) { return { status: res.status, data: data }; });
      })
      .then(function (out) {
        if (seq !== lookupSeq) return;
        if (out.status === 429 || out.status === 400) {
          showToast((out.data && out.data.error) || "That lookup couldn’t be completed.");
        } else if (out.status >= 500 || !out.data || out.data.ok !== true) {
          showToast("The registry couldn’t be reached right now. Please try again in a moment.");
        } else {
          renderResult(out.data);
        }
      })
      .catch(function () {
        if (seq === lookupSeq) showToast("Couldn’t reach the registry. Check your connection and try again.");
      })
      .then(function () {
        if (seq === lookupSeq) setBusy(false);
      });
  }

  /* ---------------- Result rendering ---------------- */
  var resultSection = document.getElementById("verifyResultSection");
  var resultCard = document.getElementById("verifyResultCard");

  function esc(str) {
    var div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  function renderResult(data) {
    var record = data.found ? data : null;
    var number = record ? record.number : data.query;
    var status = record ? record.status : "notfound";
    var meta = STATUS_META[status] || STATUS_META.notfound;

    var html = '<div class="verify-result-head status-' + meta.tone + '">' +
      '<span class="verify-status-icon"><i class="bi ' + meta.icon + '"></i></span>' +
      '<div><h3>' + esc(meta.label) + '</h3><p>' + esc(number) + '</p></div>' +
      '</div>';

    html += '<div class="verify-result-body">';

    if (!record) {
      html += '<div class="verify-not-found">' +
        '<i class="bi bi-file-earmark-x"></i>' +
        '<p>No approval matches <strong>' + esc(number) + '</strong> in the MSREC registry of approved studies. Double-check the number or code, or if this was presented to you as a valid approval, treat it as unverified and contact the Secretariat.</p>' +
        '</div>';
    } else {
      if (status === "suspended") {
        html += '<div class="verify-result-note tone-danger"><i class="bi bi-x-octagon-fill"></i><span>' + esc(record.note || "") + '</span></div>';
      } else if (status === "conditional") {
        html += '<div class="verify-result-note tone-warn"><i class="bi bi-exclamation-circle-fill"></i><span>' + esc(record.note || "") + '</span></div>';
      } else if (status === "expired") {
        html += '<div class="verify-result-note tone-muted"><i class="bi bi-hourglass-bottom"></i><span>This approval’s validity period has ended. Any research activity under it should have stopped as of the expiry date.</span></div>';
      }

      html += '<dl class="verify-detail-grid">' +
        detail("Study Title", record.title, true) +
        detail("Principal Investigator", record.pi) +
        detail("Institution", record.institution) +
        detail("Review Type", record.reviewType) +
        detail("Approved On", record.approvedOn) +
        detail("Valid Until", record.expiresOn) +
        detail("Verification Code", record.code) +
        '</dl>';

      html += '<div class="verify-result-footer">' +
        '<div class="verify-result-qr">' +
        '<div class="verify-result-qr-box" id="resultQrBox"></div>' +
        '<div class="verify-result-qr-text"><strong>' + esc(record.code) + '</strong>Scan to re-verify</div>' +
        '</div>' +
        '<div class="verify-result-actions">' +
        '<button type="button" class="verify-btn verify-btn-ghost" id="copyLinkBtn"><i class="bi bi-link-45deg"></i> Copy link</button>' +
        '<button type="button" class="verify-btn" id="printResultBtn"><i class="bi bi-printer-fill"></i> Print / Save</button>' +
        '</div>' +
        '</div>';
    }

    html += '</div>';

    resultCard.innerHTML = html;
    resultSection.hidden = false;
    resultSection.scrollIntoView({ behavior: "smooth", block: "start" });

    if (record) {
      var qrBox = document.getElementById("resultQrBox");
      if (qrBox && window.QRCode) {
        new QRCode(qrBox, { text: buildVerifyPayload(number), width: 128, height: 128, correctLevel: QRCode.CorrectLevel.M });
      }
      var copyBtn = document.getElementById("copyLinkBtn");
      if (copyBtn) copyBtn.addEventListener("click", function () { copyToClipboard(buildVerifyUrl(number)); });
      var printBtn = document.getElementById("printResultBtn");
      if (printBtn) printBtn.addEventListener("click", function () { window.print(); });
    }
  }

  function detail(label, value, span2) {
    if (value == null || String(value).trim() === "") return "";
    return '<div class="verify-detail' + (span2 ? " span-2" : "") + '"><dt>' + esc(label) + '</dt><dd>' + esc(value) + '</dd></div>';
  }

  function buildVerifyUrl(number) {
    var base = window.location.href.split("#")[0].split("?")[0];
    return base + "?ref=" + encodeURIComponent(number);
  }

  // What the QR encodes: the verify link itself, so a phone's built-in camera
  // opens the page and verifies straight away (this page reads it back too).
  function buildVerifyPayload(number) {
    return buildVerifyUrl(number);
  }

  /* ---------------- Auto-verify from ?ref= in URL ---------------- */
  (function autoVerifyFromQuery() {
    var params = new URLSearchParams(window.location.search);
    var ref = params.get("ref") || params.get("code");
    if (ref) {
      var isCode = /^VER/i.test(ref.trim());
      var tab = document.querySelector('.verify-tab[data-mode="' + (isCode ? "code" : "number") + '"]');
      if (tab) tab.click();
      var input = document.getElementById(isCode ? "verificationCode" : "approvalNumber");
      if (input) input.value = ref;
      runVerification(ref);
    }
  })();

  /* ---------------- Toast ---------------- */
  var toastTimer = null;
  function showToast(message) {
    var toast = document.querySelector(".verify-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "verify-toast";
      document.body.appendChild(toast);
    }
    toast.innerHTML = '<i class="bi bi-info-circle"></i> ' + esc(message);
    toast.classList.add("is-visible");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("is-visible"); }, 2600);
  }

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { showToast("Verification link copied."); }).catch(function () { fallbackCopy(text); });
    } else {
      fallbackCopy(text);
    }
  }

  function fallbackCopy(text) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); showToast("Verification link copied."); } catch (e) { showToast("Copy failed — select and copy manually."); }
    document.body.removeChild(ta);
  }

  /* ---------------- QR: file upload / drag-drop decode ---------------- */
  var qrFileInput = document.getElementById("qrFileInput");
  var qrDrop = document.querySelector(".verify-qr-drop");
  var qrCanvas = document.getElementById("qrCanvas");
  var qrStatus = document.getElementById("qrStatus");

  function decodeImageFile(file) {
    if (!file || !window.jsQR) return;
    var img = new Image();
    img.onload = function () {
      var ctx = qrCanvas.getContext("2d");
      qrCanvas.width = img.width;
      qrCanvas.height = img.height;
      ctx.drawImage(img, 0, 0);
      var imageData = ctx.getImageData(0, 0, qrCanvas.width, qrCanvas.height);
      var code = window.jsQR(imageData.data, imageData.width, imageData.height);
      if (code && code.data) {
        setQrStatus("QR code recognized. Checking the registry…", "success");
        runVerification(code.data);
      } else {
        setQrStatus("Could not read a QR code in that image. Try a clearer photo.", "error");
      }
      URL.revokeObjectURL(img.src);
    };
    img.onerror = function () { setQrStatus("That file couldn’t be opened as an image.", "error"); };
    img.src = URL.createObjectURL(file);
  }

  function setQrStatus(message, tone) {
    if (!qrStatus) return;
    qrStatus.textContent = message;
    qrStatus.classList.remove("is-error", "is-success");
    if (tone === "error") qrStatus.classList.add("is-error");
    if (tone === "success") qrStatus.classList.add("is-success");
  }

  if (qrFileInput) {
    qrFileInput.addEventListener("change", function () {
      if (qrFileInput.files && qrFileInput.files[0]) decodeImageFile(qrFileInput.files[0]);
    });
  }

  if (qrDrop) {
    ["dragenter", "dragover"].forEach(function (evt) {
      qrDrop.addEventListener(evt, function (e) { e.preventDefault(); qrDrop.classList.add("is-dragover"); });
    });
    ["dragleave", "drop"].forEach(function (evt) {
      qrDrop.addEventListener(evt, function (e) { e.preventDefault(); qrDrop.classList.remove("is-dragover"); });
    });
    qrDrop.addEventListener("drop", function (e) {
      var file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) decodeImageFile(file);
    });
  }

  /* ---------------- QR: live camera scan ---------------- */
  var qrVideo = document.getElementById("qrVideo");
  var qrFrame = document.getElementById("qrFrame");
  var qrStartBtn = document.getElementById("qrStartBtn");
  var qrStopBtn = document.getElementById("qrStopBtn");
  var cameraStream = null;
  var scanRafId = null;
  var scanCanvas = document.createElement("canvas");
  var scanCtx = scanCanvas.getContext("2d", { willReadFrequently: true });

  function startCamera() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setQrStatus("Camera access isn’t supported in this browser. Use upload instead.", "error");
      return;
    }
    if (!window.jsQR) {
      setQrStatus("QR scanning library failed to load. Use upload instead.", "error");
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
      .then(function (stream) {
        cameraStream = stream;
        qrVideo.srcObject = stream;
        qrVideo.setAttribute("playsinline", true);
        qrVideo.play();
        qrFrame.classList.add("is-live");
        qrStartBtn.hidden = true;
        qrStopBtn.hidden = false;
        setQrStatus("Point the camera at the QR code on the certificate.");
        scanRafId = requestAnimationFrame(scanFrame);
      })
      .catch(function () {
        setQrStatus("Camera access was blocked or unavailable. Use upload instead.", "error");
      });
  }

  function scanFrame() {
    if (!cameraStream) return;
    if (qrVideo.readyState === qrVideo.HAVE_ENOUGH_DATA) {
      scanCanvas.width = qrVideo.videoWidth;
      scanCanvas.height = qrVideo.videoHeight;
      scanCtx.drawImage(qrVideo, 0, 0, scanCanvas.width, scanCanvas.height);
      var imageData = scanCtx.getImageData(0, 0, scanCanvas.width, scanCanvas.height);
      var code = window.jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: "dontInvert" });
      if (code && code.data) {
        setQrStatus("QR code recognized. Checking the registry…", "success");
        stopCamera();
        runVerification(code.data);
        return;
      }
    }
    scanRafId = requestAnimationFrame(scanFrame);
  }

  function stopCamera() {
    if (scanRafId) cancelAnimationFrame(scanRafId);
    scanRafId = null;
    if (cameraStream) {
      cameraStream.getTracks().forEach(function (t) { t.stop(); });
      cameraStream = null;
    }
    if (qrFrame) qrFrame.classList.remove("is-live");
    if (qrStartBtn) qrStartBtn.hidden = false;
    if (qrStopBtn) qrStopBtn.hidden = true;
  }

  if (qrStartBtn) qrStartBtn.addEventListener("click", startCamera);
  if (qrStopBtn) qrStopBtn.addEventListener("click", function () { stopCamera(); setQrStatus("Camera stopped."); });
  window.addEventListener("beforeunload", stopCamera);

})();
