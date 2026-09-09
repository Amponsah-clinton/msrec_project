/* ==========================================================
   MSREC — Verify Approval page logic
   Client-side demo registry lookup + QR scan (camera & upload).
   No backend: swap REGISTRY / findRecord() for a real API call
   when one exists.
========================================================== */
(function () {
  "use strict";

  var REGISTRY = {
    "MSREC/2024/0142": {
      code: "VER-8842-XQ",
      status: "approved",
      title: "Community Perceptions of AI-Assisted Diagnostic Tools in Primary Care",
      pi: "Dr. Ama Serwaa Mensah",
      institution: "University of Ghana, School of Public Health",
      reviewType: "Full Board Review",
      riskLevel: "Minimal Risk",
      approvedOn: "18 Mar 2024",
      expiresOn: "17 Mar 2026"
    },
    "MSREC/2023/0087": {
      code: "VER-5521-TM",
      status: "expired",
      title: "Longitudinal Study of Remote Learning Outcomes in Rural Districts",
      pi: "Dr. Kwame Owusu-Ansah",
      institution: "MetaScholar Institute for Social Research",
      reviewType: "Expedited Review",
      riskLevel: "Minimal Risk",
      approvedOn: "2 May 2023",
      expiresOn: "1 May 2024"
    },
    "MSREC/2024/0210": {
      code: "VER-9034-RP",
      status: "suspended",
      title: "Biomarker Sampling in Adolescent Nutrition Cohort",
      pi: "Dr. Linda Boateng",
      institution: "Accra Clinical Research Centre",
      reviewType: "Full Board Review",
      riskLevel: "Greater Than Minimal Risk",
      approvedOn: "11 Jul 2024",
      expiresOn: "10 Jul 2026",
      note: "Suspended pending review of a reported protocol deviation. Do not rely on this approval until reinstated."
    },
    "MSREC/2025/0015": {
      code: "VER-1187-CD",
      status: "conditional",
      title: "Evaluation of a Chatbot-Delivered Mental Health Screening Tool",
      pi: "Dr. Nana Yaa Asantewaa",
      institution: "MetaScholar Institute for Digital Health",
      reviewType: "Full Board Review",
      riskLevel: "Minimal Risk",
      approvedOn: "9 Feb 2025",
      expiresOn: "Pending amendment",
      note: "Approval is conditional on submission of a revised consent form to the Secretariat."
    }
  };

  var STATUS_META = {
    approved: { label: "Approved & Valid", icon: "bi-patch-check-fill", tone: "approved" },
    conditional: { label: "Conditionally Approved", icon: "bi-exclamation-circle-fill", tone: "conditional" },
    expired: { label: "Approval Expired", icon: "bi-hourglass-bottom", tone: "expired" },
    suspended: { label: "Approval Suspended", icon: "bi-x-octagon-fill", tone: "suspended" },
    notfound: { label: "Not Found", icon: "bi-search", tone: "notfound" }
  };

  var CODE_INDEX = {};
  Object.keys(REGISTRY).forEach(function (num) {
    CODE_INDEX[REGISTRY[num].code.toUpperCase()] = num;
  });

  function normalize(str) {
    return (str || "").trim().toUpperCase();
  }

  function findRecord(raw) {
    var q = normalize(raw);
    if (!q) return null;
    if (REGISTRY[q]) return { number: q, record: REGISTRY[q] };
    // tolerate missing slashes / spaces, e.g. "MSREC 2024 0142" or "MSREC20240142"
    var loose = q.replace(/[\s\-]+/g, "/");
    if (REGISTRY[loose]) return { number: loose, record: REGISTRY[loose] };
    if (CODE_INDEX[q]) return { number: CODE_INDEX[q], record: REGISTRY[CODE_INDEX[q]] };
    return { number: q, record: null };
  }

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

  /* ---------------- Sample fill buttons ---------------- */
  document.querySelectorAll(".verify-sample-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var targetId = btn.getAttribute("data-sample-target");
      var value = btn.getAttribute("data-sample");
      var input = document.getElementById(targetId);
      if (input) input.value = value;
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

  function runVerification(raw) {
    var result = findRecord(raw);
    if (!result) {
      showToast("Enter an approval number or verification code first.");
      return;
    }
    renderResult(result.number, result.record);
  }

  /* ---------------- Result rendering ---------------- */
  var resultSection = document.getElementById("verifyResultSection");
  var resultCard = document.getElementById("verifyResultCard");

  function esc(str) {
    var div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  function renderResult(number, record) {
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
        '<p>No approval matches <strong>' + esc(number) + '</strong> in the MSREC registry. Double-check the number or code, or if this was presented to you as a valid approval, treat it as unverified and contact the Secretariat.</p>' +
        '</div>';
    } else {
      if (status === "suspended") {
        html += '<div class="verify-result-note tone-danger"><i class="bi bi-x-octagon-fill"></i><span>' + esc(record.note) + '</span></div>';
      } else if (status === "conditional") {
        html += '<div class="verify-result-note tone-warn"><i class="bi bi-exclamation-circle-fill"></i><span>' + esc(record.note) + '</span></div>';
      } else if (status === "expired") {
        html += '<div class="verify-result-note tone-muted"><i class="bi bi-hourglass-bottom"></i><span>This approval’s validity period has ended. Any research activity under it should have stopped as of the expiry date.</span></div>';
      }

      html += '<dl class="verify-detail-grid">' +
        detail("Study Title", record.title, true) +
        detail("Principal Investigator", record.pi) +
        detail("Institution", record.institution) +
        detail("Review Type", record.reviewType) +
        detail("Risk Level", record.riskLevel) +
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
    return '<div class="verify-detail' + (span2 ? " span-2" : "") + '"><dt>' + esc(label) + '</dt><dd>' + esc(value) + '</dd></div>';
  }

  function buildVerifyUrl(number) {
    var base = window.location.href.split("#")[0].split("?")[0];
    return base + "?ref=" + encodeURIComponent(number);
  }

  function buildVerifyPayload(number) {
    return number;
  }

  /* ---------------- Auto-verify from ?ref= in URL ---------------- */
  (function autoVerifyFromQuery() {
    var params = new URLSearchParams(window.location.search);
    var ref = params.get("ref");
    if (ref) runVerification(ref);
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

  /* ---------------- QR: sample code render ---------------- */
  var qrSampleHolder = document.getElementById("qrSampleCode");
  var SAMPLE_NUMBER = "MSREC/2024/0142";
  if (qrSampleHolder && window.QRCode) {
    new QRCode(qrSampleHolder, { text: SAMPLE_NUMBER, width: 48, height: 48, correctLevel: QRCode.CorrectLevel.M });
  }

  var qrSampleTrigger = document.getElementById("qrSampleTrigger");
  if (qrSampleTrigger) {
    qrSampleTrigger.addEventListener("click", function () { runVerification(SAMPLE_NUMBER); });
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
        setQrStatus("QR code recognized: " + code.data, "success");
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
        setQrStatus("QR code recognized: " + code.data, "success");
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
