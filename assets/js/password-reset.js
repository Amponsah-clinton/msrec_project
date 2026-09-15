document.addEventListener("DOMContentLoaded", () => {

  /* ============================================================
     Password visibility toggles -- generic, keyed off data-target
     (reset-password.html has two password fields, unlike login's one).
  ============================================================ */
  document.querySelectorAll(".toggle-password[data-target]").forEach((btn) => {
    const input = document.getElementById(btn.dataset.target);
    const icon = btn.querySelector("i");
    if (!input || !icon) return;
    btn.addEventListener("click", () => {
      const isHidden = input.type === "password";
      input.type = isHidden ? "text" : "password";
      icon.classList.toggle("bi-eye", !isHidden);
      icon.classList.toggle("bi-eye-slash", isHidden);
      btn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
    });
  });

  /* ============================================================
     Password strength meter -- same rules/markup as signup.js's,
     targeting the New Password field here instead.
  ============================================================ */
  (function () {
    const passwordEl = document.getElementById("new_password");
    const meter = document.getElementById("passwordStrength");
    const fill = document.getElementById("passwordStrengthFill");
    const label = document.getElementById("passwordStrengthLabel");
    const requirementItems = document.querySelectorAll("#passwordRequirements li[data-rule]");
    if (!passwordEl || !meter || !fill || !label || !requirementItems.length) return;

    const RULES = {
      length: (v) => v.length >= 8,
      upper: (v) => /[A-Z]/.test(v),
      lower: (v) => /[a-z]/.test(v),
      number: (v) => /[0-9]/.test(v),
      symbol: (v) => /[^A-Za-z0-9]/.test(v),
    };
    const STRENGTH_STYLES = [
      { color: "#c0392b", label: "Weak" },
      { color: "#c0392b", label: "Weak" },
      { color: "#d68910", label: "Fair" },
      { color: "#d68910", label: "Fair" },
      { color: "#2a4747", label: "Strong" },
      { color: "#1e7e4e", label: "Very strong" },
    ];

    passwordEl.addEventListener("input", () => {
      const value = passwordEl.value;
      meter.hidden = value.length === 0;

      let met = 0;
      requirementItems.forEach((item) => {
        const passes = RULES[item.dataset.rule](value);
        item.classList.toggle("met", passes);
        if (passes) met += 1;
      });

      const style = STRENGTH_STYLES[met];
      fill.style.width = `${(met / 5) * 100}%`;
      fill.style.backgroundColor = style.color;
      label.textContent = value ? style.label : "";
      label.style.color = style.color;
    });
  })();

  /* ============================================================
     One-time-code field -- progressively enhances the plain #code
     text input into 6 boxed digits. #code itself is kept in the DOM
     (just hidden) and stays the thing that actually posts to the
     server, so the form works exactly the same with JS disabled --
     just as one visible field instead of six.
  ============================================================ */
  (function () {
    const codeInput = document.getElementById("code");
    if (!codeInput) return;

    const boxesWrap = document.createElement("div");
    boxesWrap.className = "otp-boxes";
    const boxes = [];
    for (let i = 0; i < 6; i += 1) {
      const box = document.createElement("input");
      box.type = "text";
      box.inputMode = "numeric";
      box.maxLength = 1;
      box.className = "otp-box";
      box.autocomplete = i === 0 ? "one-time-code" : "off";
      if (codeInput.disabled) box.disabled = true;
      boxesWrap.appendChild(box);
      boxes.push(box);
    }
    codeInput.insertAdjacentElement("afterend", boxesWrap);
    codeInput.style.display = "none";
    // A display:none required field can't be constraint-validated by the
    // browser (and throws when .reportValidity() is called on the form) --
    // the submit handler below enforces "all 6 digits" itself instead.
    codeInput.required = false;

    function syncHidden() {
      codeInput.value = boxes.map((box) => box.value).join("");
    }

    boxes.forEach((box, i) => {
      box.addEventListener("input", () => {
        box.value = box.value.replace(/[^0-9]/g, "").slice(-1);
        box.classList.toggle("filled", !!box.value);
        syncHidden();
        if (box.value && boxes[i + 1]) boxes[i + 1].focus();
      });
      box.addEventListener("keydown", (e) => {
        if (e.key === "Backspace" && !box.value && boxes[i - 1]) {
          boxes[i - 1].focus();
        }
      });
      box.addEventListener("paste", (e) => {
        const text = (e.clipboardData || window.clipboardData).getData("text").replace(/[^0-9]/g, "");
        if (!text) return;
        e.preventDefault();
        text.slice(0, 6).split("").forEach((ch, idx) => { if (boxes[idx]) boxes[idx].value = ch; });
        boxes.forEach((box) => box.classList.toggle("filled", !!box.value));
        syncHidden();
        const next = boxes[Math.min(text.length, 5)];
        if (next) next.focus();
      });
    });

    if (!codeInput.disabled) boxes[0].focus();
  })();

  /* ============================================================
     Resend-code cooldown -- mirrors the server's 60s
     PasswordResetCode.RESEND_COOLDOWN. Every action on this page is a
     POST followed by a redirect back to a fresh GET (see
     accounts.views.reset_password), so a plain page-load timer stays
     accurate without needing a timestamp passed down from the server.
  ============================================================ */
  (function () {
    const btn = document.getElementById("resendBtn");
    const form = document.getElementById("resendForm");
    if (!btn || !form) return;

    const COOLDOWN_SECONDS = 60;
    const originalText = btn.textContent;
    let remaining = COOLDOWN_SECONDS;

    function tick() {
      if (remaining <= 0) {
        btn.disabled = false;
        btn.textContent = originalText;
        return;
      }
      btn.disabled = true;
      btn.textContent = `Resend code (${remaining}s)`;
      remaining -= 1;
      setTimeout(tick, 1000);
    }
    tick();

    form.addEventListener("submit", () => {
      btn.disabled = true;
      btn.textContent = "Sending...";
    });
  })();

  /* ============================================================
     Submit busy-states + the OTP completeness check the hidden
     #code input can no longer enforce natively.
  ============================================================ */
  const forgotForm = document.getElementById("forgotForm");
  if (forgotForm) {
    forgotForm.addEventListener("submit", (e) => {
      if (!forgotForm.checkValidity()) {
        e.preventDefault();
        forgotForm.reportValidity();
        return;
      }
      const btn = forgotForm.querySelector(".btn-signin");
      if (btn) { btn.disabled = true; btn.textContent = "Sending..."; }
    });
  }

  const resetForm = document.getElementById("resetForm");
  if (resetForm) {
    resetForm.addEventListener("submit", (e) => {
      const codeInput = document.getElementById("code");
      const otpError = document.getElementById("otpError");
      if (codeInput && codeInput.value.length !== 6) {
        e.preventDefault();
        if (otpError) otpError.classList.add("show");
        const firstBox = document.querySelector(".otp-box");
        if (firstBox) firstBox.focus();
        return;
      }
      if (otpError) otpError.classList.remove("show");

      if (!resetForm.checkValidity()) {
        e.preventDefault();
        resetForm.reportValidity();
        return;
      }
      const btn = resetForm.querySelector(".btn-signin");
      if (btn) { btn.disabled = true; btn.textContent = "Resetting..."; }
    });
  }
});
