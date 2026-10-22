/* Workshop countdown -- keeps every [data-wcd] (templates/workshop/_countdown.html)
   ticking. The server renders the starting numbers; this only moves them on.

   Times arrive as Unix seconds. data-now is the server's clock at render
   time, so a visitor whose device clock is wrong still sees the right
   countdown: we measure the difference once and apply it to every tick. */
(function () {
  "use strict";

  var timers = Array.prototype.slice.call(document.querySelectorAll("[data-wcd]"));
  if (!timers.length) return;

  var CAPS = {
    days: ["Day", "Days"], hours: ["Hour", "Hours"],
    minutes: ["Minute", "Minutes"], seconds: ["Second", "Seconds"]
  };
  // The compact card tiles have room for short labels only.
  var SHORT_CAPS = {
    days: ["Day", "Days"], hours: ["Hr", "Hrs"],
    minutes: ["Min", "Min"], seconds: ["Sec", "Sec"]
  };

  function pad(n) { return n < 10 ? "0" + n : String(n); }
  function plural(n, one, many) { return n + " " + (n === 1 ? one : many); }

  // "3 days, 4 hours" / "5 hours, 12 minutes" / "40 minutes" -- like Django's timeuntil.
  function roughly(ms) {
    var s = Math.max(0, Math.floor(ms / 1000));
    var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
    if (d) return plural(d, "day", "days") + (h ? ", " + plural(h, "hour", "hours") : "");
    if (h) return plural(h, "hour", "hours") + (m ? ", " + plural(m, "minute", "minutes") : "");
    return plural(Math.max(m, 1), "minute", "minutes");
  }

  function setup(el) {
    var t = {
      el: el,
      start: +el.dataset.start * 1000,
      end: el.dataset.end ? +el.dataset.end * 1000 : 0,
      deadline: el.dataset.deadline ? +el.dataset.deadline * 1000 : 0,
      skew: el.dataset.now ? +el.dataset.now * 1000 - Date.now() : 0,
      small: el.classList.contains("wcd--sm"),
      line: el.classList.contains("wcd--line"),
      nums: {}, caps: {}, last: {},
      counting: el.querySelectorAll("[data-wcd-counting]"),
      live: el.querySelector("[data-wcd-live]"),
      note: el.querySelector("[data-wcd-deadline]"),
      noteLeft: el.querySelector("[data-wcd-deadline-left]"),
      sr: el.querySelector("[data-wcd-sr]"),
      srMinute: -1,
      done: false
    };
    ["days", "hours", "minutes", "seconds"].forEach(function (u) {
      t.nums[u] = el.querySelector('[data-u="' + u + '"]');
      t.caps[u] = el.querySelector('[data-c="' + u + '"]');
    });
    return t;
  }

  function show(nodes, on) {
    Array.prototype.forEach.call(nodes, function (n) { n.hidden = !on; });
  }

  function update(t) {
    var now = Date.now() + t.skew;

    if (now < t.start) {
      var left = Math.floor((t.start - now) / 1000);
      var parts = {
        days: Math.floor(left / 86400),
        hours: Math.floor(left % 86400 / 3600),
        minutes: Math.floor(left % 3600 / 60),
        seconds: left % 60
      };
      Object.keys(parts).forEach(function (u) {
        var node = t.nums[u];
        if (!node || t.last[u] === parts[u]) return;
        // The plain-text line reads "5 days", not "05 days".
        node.textContent = t.line ? String(parts[u]) : pad(parts[u]);
        if (t.last[u] !== undefined) {
          node.classList.remove("tick");
          void node.offsetWidth; // restart the animation
          node.classList.add("tick");
        }
        t.last[u] = parts[u];
        if (t.caps[u]) {
          var word = (t.small ? SHORT_CAPS : CAPS)[u][parts[u] === 1 ? 0 : 1];
          t.caps[u].textContent = t.line ? word.toLowerCase() : word;
        }
      });

      if (t.note) {
        if (t.deadline && now < t.deadline) {
          if (t.noteLeft) t.noteLeft.textContent = roughly(t.deadline - now);
        } else {
          t.note.textContent = "Registration has closed for this workshop.";
          t.note = null;
        }
      }
      // Screen readers get a fresh sentence once a minute, not every second.
      if (t.sr && parts.minutes !== t.srMinute) {
        t.srMinute = parts.minutes;
        t.sr.textContent = "Starts in " + roughly(t.start - now);
      }
      show(t.counting, true);
      if (t.live) t.live.hidden = true;
      return;
    }

    if (t.end && now < t.end) {
      show(t.counting, false);
      if (t.note) { t.note.hidden = true; }
      if (t.live) t.live.hidden = false;
      if (t.sr && t.srMinute !== "live") { t.srMinute = "live"; t.sr.textContent = "Happening now"; }
      return;
    }

    // Over: nothing left to count down to.
    t.el.hidden = true;
    t.done = true;
  }

  var state = timers.map(setup);
  function tickAll() {
    state.forEach(function (t) { if (!t.done) update(t); });
    if (state.every(function (t) { return t.done; })) return;
    // Land each tick just after the second boundary, so the seconds never skip or stall.
    setTimeout(tickAll, 1000 - (Date.now() % 1000) + 15);
  }
  tickAll();
  // A tab woken from the background catches up immediately.
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) state.forEach(function (t) { if (!t.done) update(t); });
  });
})();
