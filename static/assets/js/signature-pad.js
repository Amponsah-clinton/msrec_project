/* Signature pad: sign by drawing (mouse, finger or stylus) or by typing a
 * name, which is shown in a handwriting face.
 *
 * Markup: templates/psa/_signature.html. On submit it fills
 *   <prefix>_signature_kind   "drawn" | "typed"
 *   <prefix>_signature_drawn  PNG data: URL (drawn only)
 *   <prefix>_signature_typed  the typed name (a visible input)
 * and the server (psa/forms.py parse_signature) reads only the chosen kind.
 *
 * Each pad element gets a `sigpad` property: { isEmpty(), mode() }.
 */
(function () {
  var INK = "#1b2a5c";

  function setup(root) {
    var kindInput = root.querySelector('[data-sig="kind"]');
    var drawnInput = root.querySelector('[data-sig="drawn"]');
    var typedInput = root.querySelector('[data-sig="typed"]');
    var preview = root.querySelector("[data-typed-preview]");
    var canvas = root.querySelector("canvas");
    var hint = root.querySelector(".sigpad-hint");
    var tabs = root.querySelectorAll("[data-mode]");
    var panels = root.querySelectorAll("[data-panel]");
    var ctx = canvas.getContext("2d");
    var strokes = [];      // [[{x,y}...]...] in CSS pixels of the canvas box
    var current = null;
    var size = { w: 0, h: 0 };

    function mode() { return kindInput.value; }

    function show(m) {
      kindInput.value = m;
      tabs.forEach(function (t) {
        var on = t.dataset.mode === m;
        t.classList.toggle("is-on", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
      });
      panels.forEach(function (p) { p.hidden = p.dataset.panel !== m; });
      if (m === "drawn") resize();
      root.dispatchEvent(new CustomEvent("sigpad:change", { bubbles: true }));
    }

    tabs.forEach(function (t) {
      t.addEventListener("click", function () { show(t.dataset.mode); });
      t.addEventListener("keydown", function (e) {
        if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
        var other = Array.prototype.find.call(tabs, function (x) { return x !== t; });
        if (other) { other.click(); other.focus(); }
      });
    });

    // ---- typed --------------------------------------------------------
    function syncTyped() {
      var name = typedInput.value.trim();
      preview.textContent = name || preview.dataset.placeholder || "";
      preview.classList.toggle("is-placeholder", !name);
      root.dispatchEvent(new CustomEvent("sigpad:change", { bubbles: true }));
    }
    typedInput.addEventListener("input", syncTyped);
    var fill = root.querySelector("[data-fill-name]");
    if (fill) fill.addEventListener("click", function () {
      var src = fill.dataset.fillFrom ? document.querySelector(fill.dataset.fillFrom) : null;
      typedInput.value = (src && src.value.trim()) || fill.dataset.fillName || "";
      syncTyped();
      typedInput.focus();
    });

    // ---- drawn --------------------------------------------------------
    function redraw() {
      var dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size.w, size.h);
      paint(ctx, strokes, 1);
      hint.hidden = strokes.length > 0;
    }

    function resize() {
      var box = canvas.getBoundingClientRect();
      if (!box.width) return;
      var dpr = window.devicePixelRatio || 1;
      // Keep the drawing when the box changes size (rotation, resize).
      if (size.w && (size.w !== box.width || size.h !== box.height)) {
        var sx = box.width / size.w, sy = box.height / size.h;
        strokes = strokes.map(function (s) { return s.map(function (p) { return { x: p.x * sx, y: p.y * sy }; }); });
      }
      size = { w: box.width, h: box.height };
      canvas.width = Math.round(box.width * dpr);
      canvas.height = Math.round(box.height * dpr);
      redraw();
    }

    function point(e) {
      var box = canvas.getBoundingClientRect();
      return { x: e.clientX - box.left, y: e.clientY - box.top };
    }

    canvas.addEventListener("pointerdown", function (e) {
      if (e.button !== undefined && e.button > 0) return;
      e.preventDefault();
      canvas.setPointerCapture(e.pointerId);
      current = [point(e)];
      strokes.push(current);
      redraw();
    });
    canvas.addEventListener("pointermove", function (e) {
      if (!current) return;
      e.preventDefault();
      var events = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
      events.forEach(function (ev) { current.push(point(ev)); });
      redraw();
    });
    function end() {
      if (!current) return;
      current = null;
      root.dispatchEvent(new CustomEvent("sigpad:change", { bubbles: true }));
    }
    canvas.addEventListener("pointerup", end);
    canvas.addEventListener("pointercancel", end);
    canvas.addEventListener("lostpointercapture", end);

    root.querySelector("[data-clear]").addEventListener("click", function () {
      strokes = [];
      redraw();
      root.dispatchEvent(new CustomEvent("sigpad:change", { bubbles: true }));
    });
    var undo = root.querySelector("[data-undo]");
    if (undo) undo.addEventListener("click", function () {
      strokes.pop();
      redraw();
      root.dispatchEvent(new CustomEvent("sigpad:change", { bubbles: true }));
    });

    window.addEventListener("resize", function () { if (mode() === "drawn") resize(); });

    function isEmpty() {
      if (mode() === "typed") return typedInput.value.trim().length < 2;
      return !strokes.some(function (s) { return s.length > 1; }) && strokes.length < 3;
    }

    // Export at twice the on-screen size for a crisp PNG; the server crops
    // it to the ink.
    function exportPng() {
      var scale = 2;
      var out = document.createElement("canvas");
      out.width = Math.round(size.w * scale);
      out.height = Math.round(size.h * scale);
      var octx = out.getContext("2d");
      octx.setTransform(scale, 0, 0, scale, 0, 0);
      paint(octx, strokes, 1);
      return out.toDataURL("image/png");
    }

    var form = root.closest("form");
    if (form) form.addEventListener("submit", function () {
      if (mode() === "drawn") {
        drawnInput.value = strokes.length ? exportPng() : "";
      } else {
        drawnInput.value = "";
      }
    });

    root.sigpad = { isEmpty: isEmpty, mode: mode };
    show(kindInput.value || "drawn");
    syncTyped();
  }

  function paint(c, strokes, width) {
    c.strokeStyle = INK;
    c.fillStyle = INK;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.lineWidth = 2.4 * width;
    strokes.forEach(function (s) {
      if (s.length === 1) {
        c.beginPath();
        c.arc(s[0].x, s[0].y, 1.4 * width, 0, Math.PI * 2);
        c.fill();
        return;
      }
      // Midpoint quadratic curves: smooth without lagging the pen.
      c.beginPath();
      c.moveTo(s[0].x, s[0].y);
      for (var i = 1; i < s.length - 1; i++) {
        var mx = (s[i].x + s[i + 1].x) / 2, my = (s[i].y + s[i + 1].y) / 2;
        c.quadraticCurveTo(s[i].x, s[i].y, mx, my);
      }
      var last = s[s.length - 1];
      c.lineTo(last.x, last.y);
      c.stroke();
    });
  }

  function init() { document.querySelectorAll("[data-sigpad]").forEach(setup); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
