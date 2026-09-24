/* Settings -> Certificates: the Chair's name, title and signature.

   The signature is either drawn on the pad or uploaded as an image. The
   server does the real work on save (pages/signature.py removes the paper
   background and crops to the ink). This script mirrors that in the
   browser only for the live preview, so what the admin sees in the preview
   block is what will be printed on the certificate. */
(function () {
  var form = document.getElementById("certSignatoryForm");
  if (!form) return;

  var $ = function (id) { return document.getElementById(id); };
  var canvas = $("sigPad");
  var ctx = canvas.getContext("2d");
  var dataInput = $("sigData");
  var modeInput = $("sigMode");
  var fileInput = $("sigFile");
  var drawPane = $("sigDrawPane");
  var uploadPane = $("sigUploadPane");
  var padHint = $("sigPadHint");
  var undoBtn = $("sigUndo");
  var clearBtn = $("sigClear");
  var drop = $("sigDrop");
  var dropTitle = $("sigDropTitle");
  var nameInput = $("chairName");
  var titleInput = $("chairTitle");
  var prevSig = $("csPrevSig");
  var prevSigEmpty = $("csPrevSigEmpty");
  var prevName = $("csPrevName");
  var prevTitle = $("csPrevTitle");
  var status = $("csStatus");
  var modeBtns = form.querySelectorAll("[data-sig-mode]");

  var savedSrc = prevSig.getAttribute("src") || "";
  var hasSaved = !!savedSrc;

  // ------------------------------------------------------------- preview
  function setStatus(kind, text) {
    status.innerHTML = '<i class="dot ' + kind + '"></i> ' + text;
  }

  function showPreview(src) {
    if (src) {
      prevSig.src = src;
      prevSig.hidden = false;
      prevSigEmpty.hidden = true;
    } else {
      prevSig.removeAttribute("src");
      prevSig.hidden = true;
      prevSigEmpty.hidden = false;
    }
  }

  function restoreSaved() {
    showPreview(savedSrc);
    if (hasSaved) setStatus("ok", "Saved signature in use");
    else setStatus("", "No signature saved &mdash; certificates show a blank line to sign by hand");
  }

  function syncText() {
    prevName.textContent = nameInput.value.trim() || prevName.getAttribute("data-placeholder");
    prevName.classList.toggle("is-placeholder", !nameInput.value.trim());
    prevTitle.textContent = titleInput.value.trim() || "Chair of the Committee";
  }
  nameInput.addEventListener("input", function () { syncText(); nameInput.classList.remove("is-invalid"); });
  titleInput.addEventListener("input", syncText);
  syncText();

  // Crop a canvas to the bounding box of its visible pixels (+ margin).
  function trimmed(source) {
    var w = source.width, h = source.height;
    var px = source.getContext("2d").getImageData(0, 0, w, h).data;
    var minX = w, minY = h, maxX = -1, maxY = -1;
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        if (px[(y * w + x) * 4 + 3] > 24) {
          if (x < minX) minX = x;
          if (x > maxX) maxX = x;
          if (y < minY) minY = y;
          if (y > maxY) maxY = y;
        }
      }
    }
    if (maxX < 0) return null;
    var padX = Math.round((maxX - minX) * 0.04) + 2, padY = Math.round((maxY - minY) * 0.04) + 2;
    minX = Math.max(0, minX - padX); minY = Math.max(0, minY - padY);
    maxX = Math.min(w - 1, maxX + padX); maxY = Math.min(h - 1, maxY + padY);
    var out = document.createElement("canvas");
    out.width = maxX - minX + 1;
    out.height = maxY - minY + 1;
    out.getContext("2d").drawImage(source, minX, minY, out.width, out.height, 0, 0, out.width, out.height);
    return out;
  }

  // ------------------------------------------------------------- the pad
  // A pen, not a marker: every point carries a width worked out from how
  // fast the pen was moving (slow = more ink, fast = a finer line) and,
  // with a stylus, how hard it was pressed. Strokes taper in and out like
  // a nib touching down and lifting off, and finished ink gets a faint
  // soft edge, as ink bleeds very slightly into paper.
  var INKS = { blue: "#1d3b8f", black: "#16181f" };
  var ink = INKS.blue;
  var strokes = [];   // each stroke: array of {x, y, t, p} (x/y as fractions of the pad)
  var current = null;
  var ratio = 2;
  var inkLayer = document.createElement("canvas");
  var inkCtx = inkLayer.getContext("2d");

  function sizeCanvas() {
    ratio = Math.max(window.devicePixelRatio || 1, 2);
    var cssWidth = canvas.clientWidth || 600;
    var cssHeight = Math.round(cssWidth / 3.2);
    canvas.style.height = cssHeight + "px";
    canvas.width = inkLayer.width = Math.round(cssWidth * ratio);
    canvas.height = inkLayer.height = Math.round(cssHeight * ratio);
    renderInk();
    paint();
  }

  // One "unit" = 1px on a 600px-wide pad, so the pen feels the same at any size.
  function unit() { return canvas.width / 600; }

  function widths(points, finished) {
    var MAX = 3.6, MIN = 0.9;
    var out = [], vel = 0, w = MAX * 0.7;
    var aspect = canvas.height / canvas.width;
    for (var i = 0; i < points.length; i++) {
      var raw;
      if (i === 0) {
        raw = MAX * 0.75;
      } else {
        var a = points[i - 1], b = points[i];
        var dist = Math.hypot((b.x - a.x) * 600, (b.y - a.y) * 600 * aspect);
        var dt = Math.max(1, b.t - a.t);
        vel = 0.55 * (dist / dt) + 0.45 * vel;
        raw = Math.max(MIN, MAX / (1 + vel * 1.25));
      }
      if (points[i].p > 0 && points[i].p < 1) raw *= 0.5 + points[i].p;  // stylus pressure
      w = i === 0 ? raw : 0.7 * w + 0.3 * raw;
      out.push(w);
    }
    // Nib touching down / lifting off.
    var TAPER = Math.min(7, Math.floor(points.length / 3));
    for (var j = 0; j < TAPER; j++) {
      var f = 0.3 + 0.7 * (j / TAPER);
      out[j] *= f;
      if (finished) out[out.length - 1 - j] *= f;
    }
    return out;
  }

  function renderStroke(c, points, finished) {
    var u = unit(), W = canvas.width, H = canvas.height;
    c.fillStyle = ink;
    if (points.length < 3) {
      c.beginPath();
      c.arc(points[0].x * W, points[0].y * H, 2.3 * u, 0, Math.PI * 2);
      c.fill();
      return;
    }
    var ws = widths(points, finished);
    var P = function (i) { return { x: points[i].x * W, y: points[i].y * H }; };
    var mid = function (i) {  // midpoint between point i and i+1
      var a = P(i), b = P(i + 1);
      return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    };
    c.beginPath();
    var start = P(0), startW = ws[0];
    for (var i = 1; i < points.length - 1; i++) {
      var ctrl = P(i), end = mid(i);
      var endW = (ws[i] + ws[i + 1]) / 2;
      var len = Math.hypot(ctrl.x - start.x, ctrl.y - start.y) + Math.hypot(end.x - ctrl.x, end.y - ctrl.y);
      var steps = Math.max(2, Math.ceil(len / (0.35 * u)));
      for (var s = 0; s <= steps; s++) {
        var t = s / steps, mt = 1 - t;
        var x = mt * mt * start.x + 2 * mt * t * ctrl.x + t * t * end.x;
        var y = mt * mt * start.y + 2 * mt * t * ctrl.y + t * t * end.y;
        var r = (startW + (endW - startW) * t) * u / 2;
        c.moveTo(x + r, y);
        c.arc(x, y, r, 0, Math.PI * 2);
      }
      start = end;
      startW = endW;
    }
    c.fill();
  }

  // Finished strokes live on their own layer; the live stroke is drawn on
  // top of it each frame, so a long signature never re-renders everything.
  function renderInk() {
    inkCtx.clearRect(0, 0, inkLayer.width, inkLayer.height);
    strokes.forEach(function (s) { renderStroke(inkCtx, s, true); });
  }

  function paint() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.save();
    ctx.shadowColor = ink === INKS.blue ? "rgba(29, 59, 143, .45)" : "rgba(22, 24, 31, .4)";
    ctx.shadowBlur = 0.9 * unit();
    ctx.drawImage(inkLayer, 0, 0);
    ctx.restore();
    if (current) renderStroke(ctx, current, false);
  }

  function padChanged() {
    var inked = strokes.length > 0;
    padHint.hidden = inked;
    undoBtn.disabled = !inked;
    clearBtn.disabled = !inked;
    if (modeInput.value !== "draw") return;
    if (!inked) { restoreSaved(); return; }
    var t = trimmed(canvas);
    showPreview(t ? t.toDataURL("image/png") : "");
    setStatus("pending", "New signature &mdash; not saved yet");
  }

  // Points are stored as fractions of the pad, so a resize never distorts them.
  function point(evt) {
    var rect = canvas.getBoundingClientRect();
    return {
      x: (evt.clientX - rect.left) / rect.width,
      y: (evt.clientY - rect.top) / rect.height,
      t: evt.timeStamp || Date.now(),
      p: evt.pointerType === "pen" ? evt.pressure : 0
    };
  }

  canvas.addEventListener("pointerdown", function (evt) {
    evt.preventDefault();
    canvas.setPointerCapture(evt.pointerId);
    current = [point(evt)];
    padHint.hidden = true;
    paint();
  });
  canvas.addEventListener("pointermove", function (evt) {
    if (!current) return;
    evt.preventDefault();
    var events = evt.getCoalescedEvents ? evt.getCoalescedEvents() : [evt];
    events.forEach(function (e) {
      var pt = point(e), last = current[current.length - 1];
      // skip jitter-sized moves; they only add wobble
      if (Math.hypot((pt.x - last.x) * canvas.width, (pt.y - last.y) * canvas.height) >= 0.6 * unit()) current.push(pt);
    });
    paint();
  });
  function endStroke() {
    if (!current) return;
    strokes.push(current);
    current = null;
    renderInk();
    paint();
    padChanged();
  }
  canvas.addEventListener("pointerup", endStroke);
  canvas.addEventListener("pointercancel", endStroke);

  undoBtn.addEventListener("click", function () { strokes.pop(); renderInk(); paint(); padChanged(); });
  clearBtn.addEventListener("click", function () { strokes = []; renderInk(); paint(); padChanged(); });

  form.querySelectorAll("[data-ink]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      ink = INKS[btn.getAttribute("data-ink")] || INKS.blue;
      form.querySelectorAll("[data-ink]").forEach(function (b) {
        var on = b === btn;
        b.classList.toggle("active", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      renderInk();
      paint();
      if (strokes.length) padChanged();
    });
  });

  // ------------------------------------------------------------- upload
  var uploadPreview = "";

  // Browser-side twin of pages/signature.py's _remove_paper(): estimate the
  // paper tone, make it transparent, re-ink the strokes in the pen colour.
  function removePaper(img) {
    var scale = Math.min(1, 1400 / Math.max(img.naturalWidth, img.naturalHeight));
    var c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(img.naturalWidth * scale));
    c.height = Math.max(1, Math.round(img.naturalHeight * scale));
    var cx = c.getContext("2d");
    cx.drawImage(img, 0, 0, c.width, c.height);
    var imgData = cx.getImageData(0, 0, c.width, c.height);
    var d = imgData.data, n = c.width * c.height, i;

    var hasAlpha = false;
    for (i = 3; i < d.length; i += 4) { if (d[i] < 250) { hasAlpha = true; break; } }
    if (hasAlpha) return trimmed(c);

    var hist = new Array(256).fill(0), lum = new Uint8ClampedArray(n);
    for (i = 0; i < n; i++) {
      var l = Math.round(0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2]);
      lum[i] = l; hist[l]++;
    }
    function pct(p) {
      var target = n * p, run = 0;
      for (var v = 0; v < 256; v++) { run += hist[v]; if (run >= target) return v; }
      return 255;
    }
    var paper = pct(0.8), pen = pct(0.01), span = Math.max(40, paper - pen);
    var floor = paper - span * 0.18, ceil = paper - span * 0.72;
    if (ceil >= floor) ceil = floor - 1;

    var sr = 0, sg = 0, sb = 0, cnt = 0, alpha = new Uint8ClampedArray(n);
    for (i = 0; i < n; i++) {
      var a = (floor - lum[i]) * 255 / (floor - ceil);
      alpha[i] = a;
      if (alpha[i] > 200) { sr += d[i * 4]; sg += d[i * 4 + 1]; sb += d[i * 4 + 2]; cnt++; }
    }
    var r = cnt ? sr / cnt * 0.85 : 20, g = cnt ? sg / cnt * 0.85 : 35, b = cnt ? sb / cnt * 0.85 : 63;
    for (i = 0; i < n; i++) {
      d[i * 4] = r; d[i * 4 + 1] = g; d[i * 4 + 2] = b; d[i * 4 + 3] = alpha[i];
    }
    cx.putImageData(imgData, 0, 0);
    return trimmed(c);
  }

  function useFile(file) {
    if (!file) return;
    if (!/^image\//.test(file.type)) {
      setStatus("err", "That file isn't an image &mdash; use a PNG, JPG or WEBP.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setStatus("err", "That image is larger than 8 MB.");
      fileInput.value = "";
      return;
    }
    dropTitle.textContent = file.name;
    drop.classList.add("has-file");
    var img = new Image();
    img.onload = function () {
      var result = removePaper(img);
      URL.revokeObjectURL(img.src);
      if (!result) {
        uploadPreview = "";
        showPreview("");
        setStatus("err", "No signature found in that image &mdash; use dark ink on plain light paper.");
        return;
      }
      uploadPreview = result.toDataURL("image/png");
      showPreview(uploadPreview);
      setStatus("pending", "New signature &mdash; background removed, not saved yet");
    };
    img.onerror = function () { setStatus("err", "That image couldn't be read."); };
    img.src = URL.createObjectURL(file);
  }

  fileInput.addEventListener("change", function () { useFile(fileInput.files && fileInput.files[0]); });

  ["dragenter", "dragover"].forEach(function (type) {
    drop.addEventListener(type, function (evt) { evt.preventDefault(); drop.classList.add("is-over"); });
  });
  ["dragleave", "drop"].forEach(function (type) {
    drop.addEventListener(type, function (evt) { evt.preventDefault(); drop.classList.remove("is-over"); });
  });
  drop.addEventListener("drop", function (evt) {
    var file = evt.dataTransfer && evt.dataTransfer.files && evt.dataTransfer.files[0];
    if (!file) return;
    try {
      var dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
    } catch (e) { /* very old browsers: the preview still shows, browse to submit */ }
    useFile(file);
  });

  // ------------------------------------------------------------- modes
  function setMode(mode) {
    modeInput.value = mode;
    drawPane.hidden = mode !== "draw";
    uploadPane.hidden = mode !== "upload";
    modeBtns.forEach(function (btn) {
      var active = btn.getAttribute("data-sig-mode") === mode;
      btn.classList.toggle("active", active);
      btn.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (mode === "draw") {
      sizeCanvas();
      padChanged();
    } else if (uploadPreview) {
      showPreview(uploadPreview);
      setStatus("pending", "New signature &mdash; background removed, not saved yet");
    } else {
      restoreSaved();
    }
  }
  modeBtns.forEach(function (btn) {
    btn.addEventListener("click", function () { setMode(btn.getAttribute("data-sig-mode")); });
  });

  // ------------------------------------------------------------- submit
  form.addEventListener("submit", function (evt) {
    var submitter = evt.submitter;
    dataInput.value = "";

    if (submitter && submitter.name === "remove_signature") {
      if (!window.confirm("Remove the saved signature? Certificates will show a blank line to sign by hand.")) {
        evt.preventDefault();
        return;
      }
      fileInput.value = "";
      if (!nameInput.value.trim()) nameInput.value = nameInput.defaultValue;
      return;
    }

    if (!nameInput.value.trim()) {
      evt.preventDefault();
      nameInput.classList.add("is-invalid");
      nameInput.focus();
      return;
    }

    if (modeInput.value === "draw") {
      fileInput.value = "";
      if (strokes.length) {
        var t = trimmed(canvas);
        if (t) dataInput.value = t.toDataURL("image/png");
      }
    }
  });

  // ------------------------------------------------------------- layout
  // The canvas can only be measured once its tab is visible.
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { if (!drawPane.hidden) sizeCanvas(); }, 120);
  });
  document.addEventListener("click", function (evt) {
    if (evt.target.closest && evt.target.closest('.settings-tab[data-target="certificates"]')) {
      setTimeout(function () { if (!drawPane.hidden) sizeCanvas(); }, 0);
    }
  });
  if (window.ResizeObserver) {
    new ResizeObserver(function () { if (!drawPane.hidden && canvas.clientWidth) sizeCanvas(); }).observe(canvas);
  }

  setMode("draw");
})();
