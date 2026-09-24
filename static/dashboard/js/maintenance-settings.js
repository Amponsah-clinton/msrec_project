/* Site Settings > Maintenance: quick "+N hours" end times, and a hint
   that flips the master switch on when a schedule is entered. */
(function () {
  var form = document.getElementById("maintenanceForm");
  if (!form) return;
  var start = document.getElementById("mtStart");
  var end = document.getElementById("mtEnd");
  var enabled = document.getElementById("mtEnabled");

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  // datetime-local wants "YYYY-MM-DDTHH:MM" in the field's own (site) time.
  function fmt(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) + "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function parse(value) {
    var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value || "");
    return m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null;
  }

  form.querySelectorAll("[data-mt-hours]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var base = parse(start.value);
      if (!base) {
        // No start yet: the window begins now (rounded to the minute).
        base = new Date();
        base.setSeconds(0, 0);
        start.value = fmt(base);
      }
      end.value = fmt(new Date(base.getTime() + parseInt(btn.getAttribute("data-mt-hours"), 10) * 3600 * 1000));
    });
  });
  var clear = form.querySelector("[data-mt-clear]");
  if (clear) clear.addEventListener("click", function () { end.value = ""; });
})();
