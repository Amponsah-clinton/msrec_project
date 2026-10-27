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
  var INK = "#1b2a5c";          // blue-black, the way a pen dries

  // A nib lays down a wider line the slower it moves, and a stylus adds
  // real pressure on top of that. These turn the pointer's speed into a
  // width so a stroke tapers and swells instead of being a flat ribbon.
  var BASE_W = 2.7;             // width at an ordinary writing speed
  var FAST = 0.95;              // px per ms counted as a fast flick
  var THICKEST = 1.65, THINNEST = 0.45; // multiples of BASE_W

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
      paint(ctx, strokes);
      hint.hidden = strokes.length > 0;
    }

    function resize() {
      var box = canvas.getBoundingClientRect();
      if (!box.width) return;
      var dpr = window.devicePixelRatio || 1;
      // Keep the drawing when the box changes size (rotation, resize).
      if (size.w && (size.w !== box.width || size.h !== box.height)) {
        var sx = box.width / size.w, sy = box.height / size.h;
        strokes = strokes.map(function (s) {
          return s.map(function (pt) {
            return { x: pt.x * sx, y: pt.y * sy, t: pt.t, f: pt.f, pen: pt.pen };
          });
        });
      }
      size = { w: box.width, h: box.height };
      canvas.width = Math.round(box.width * dpr);
      canvas.height = Math.round(box.height * dpr);
      redraw();
    }

    function point(e) {
      var box = canvas.getBoundingClientRect();
      return {
        x: e.clientX - box.left,
        y: e.clientY - box.top,
        // For the width: when the point was made, and how hard. A mouse
        // or finger reports 0.5 (or 0), so pressure is only trusted from
        // a stylus and speed does the work for everyone else.
        t: e.timeStamp || (window.performance && performance.now()) || Date.now(),
        f: e.pressure === undefined ? 0 : e.pressure,
        pen: e.pointerType === "pen",
      };
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
      paint(octx, strokes);
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

  // One width per point of a stroke, from how fast the pen was moving
  // there (and its pressure, with a stylus).
  function widths(s) {
    var w = [], i, pass, out, dx, dy, dt, speed, factor;
    for (i = 0; i < s.length; i++) {
      if (i === 0) {
        speed = 0;
      } else {
        dx = s[i].x - s[i - 1].x;
        dy = s[i].y - s[i - 1].y;
        dt = Math.max(1, (s[i].t || 0) - (s[i - 1].t || 0));
        speed = Math.sqrt(dx * dx + dy * dy) / dt;
      }
      factor = THICKEST - (THICKEST - THINNEST) * Math.min(1, speed / FAST);
      if (s[i].pen && s[i].f > 0) factor *= 0.55 + 0.9 * s[i].f;
      w.push(BASE_W * factor);
    }
    // Pointer timings are jittery and a real nib changes width gradually,
    // so the widths are averaged with their neighbours twice.
    for (pass = 0; pass < 2; pass++) {
      out = w.slice();
      for (i = 1; i < w.length - 1; i++) out[i] = (w[i - 1] + w[i] + w[i + 1]) / 3;
      w = out;
    }
    // Both ends thin out, the way a stroke does as the pen touches down
    // and lifts off again.
    var taper = Math.min(5, Math.floor(w.length / 3));
    for (i = 0; i < taper; i++) {
      var k = 0.4 + 0.6 * ((i + 1) / (taper + 1));
      w[i] *= k;
      w[w.length - 1 - i] *= k;
    }
    return w;
  }

  function paint(c, strokes) {
    c.strokeStyle = INK;
    c.fillStyle = INK;
    c.lineCap = "round";
    c.lineJoin = "round";
    strokes.forEach(function (s) {
      if (s.length === 1) {
        // A full stop: the nib pressed and lifted without moving.
        c.beginPath();
        c.arc(s[0].x, s[0].y, BASE_W * 0.7, 0, Math.PI * 2);
        c.fill();
        return;
      }
      // Midpoint quadratics -- smooth, and no lag behind the pen -- but
      // one short path per point, each at its own width. Round caps make
      // the joins between them invisible.
      var w = widths(s);
      for (var i = 1; i < s.length; i++) {
        var from = i === 1
          ? s[0]
          : { x: (s[i - 1].x + s[i].x) / 2, y: (s[i - 1].y + s[i].y) / 2 };
        var to = i === s.length - 1
          ? s[i]
          : { x: (s[i].x + s[i + 1].x) / 2, y: (s[i].y + s[i + 1].y) / 2 };
        c.lineWidth = w[i];
        c.beginPath();
        c.moveTo(from.x, from.y);
        c.quadraticCurveTo(s[i].x, s[i].y, to.x, to.y);
        c.stroke();
      }
    });
  }

  function init() { document.querySelectorAll("[data-sigpad]").forEach(setup); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
