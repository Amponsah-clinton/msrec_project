document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("applyForm");
  if (!form) return;

  /* ============================================================
     Yes/No toggles
  ============================================================ */
  function initYesNoToggles(root) {
    root.querySelectorAll(".yn-toggle").forEach((toggle) => {
      const hidden = document.getElementById(toggle.dataset.hiddenId);
      toggle.querySelectorAll(".yn-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          toggle.querySelectorAll(".yn-btn").forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          const value = btn.dataset.value;
          if (hidden) hidden.value = value;
          toggle.dispatchEvent(new CustomEvent("ynchange", { detail: { value }, bubbles: true }));
          updateProgress();
        });
      });
    });
  }
  initYesNoToggles(form);

  function gateYesNo(toggleId, detailEl, showValues) {
    const toggle = document.getElementById(toggleId);
    if (!toggle || !detailEl) return;
    toggle.addEventListener("ynchange", (e) => {
      detailEl.hidden = !showValues.includes(e.detail.value);
    });
  }

  /* Section 8 -> gates its own detail block AND the whole of section 9 */
  gateYesNo("participantsGate", document.getElementById("participantsDetails"), ["yes"]);
  gateYesNo("participantsGate", document.getElementById("sec-9"), ["yes"]);

  /* Section 9 compensation detail */
  (function () {
    const toggle = document.querySelector('.yn-toggle[data-hidden-id="compensationYn"]');
    const detail = document.getElementById("compensationDetails");
    if (toggle && detail) {
      toggle.addEventListener("ynchange", (e) => { detail.hidden = e.detail.value !== "yes"; });
    }
  })();

  /* Section 12 sensitive info */
  gateYesNo("sensitiveInfoGate", document.getElementById("sensitiveInfoDetails"), ["yes"]);

  /* Section 14 AI/ML */
  gateYesNo("aiGate", document.getElementById("aiDetails"), ["yes"]);

  /* Section 15 system/device */
  gateYesNo("systemGate", document.getElementById("systemDetails"), ["yes"]);

  /* Section 16 reviews */
  gateYesNo("reviewGate", document.getElementById("reviewDetails"), ["yes"]);

  /* Section 17 secondary data */
  gateYesNo("secondaryDataGate", document.getElementById("secondaryDataDetails"), ["yes"]);

  /* Section 19 funding / international collaboration */
  gateYesNo("fundedGate", document.getElementById("fundedDetails"), ["yes"]);
  gateYesNo("internationalGate", document.getElementById("internationalDetails"), ["yes"]);

  /* Section 5 academic programme */
  (function () {
    const toggle = form.querySelector('.yn-toggle[data-hidden-id="academicProgrammeYn"]');
    const detail = document.getElementById("academicProgrammeDetails");
    if (toggle && detail) {
      toggle.addEventListener("ynchange", (e) => { detail.hidden = e.detail.value !== "yes"; });
    }
  })();

  /* ============================================================
     Radio-based conditional reveals (non yes/no chip grids)
  ============================================================ */
  function gateOnRadio(groupName, showValues, detailEl) {
    const radios = Array.from(form.querySelectorAll(`input[name="${groupName}"]`));
    if (!radios.length || !detailEl) return;
    radios.forEach((r) => {
      r.addEventListener("change", () => {
        const selected = radios.find((x) => x.checked);
        detailEl.hidden = !(selected && showValues.includes(selected.value));
      });
    });
  }
  gateOnRadio("consentObtained", ["no", "waiver"], document.getElementById("consentExplainWrap"));
  gateOnRadio("coi", ["yes"], document.getElementById("coiDetails"));

  /* ============================================================
     "Other" reveal — any chip-checkbox-grid with a .chip-other-trigger
  ============================================================ */
  document.querySelectorAll(".chip-checkbox-grid, .apply-team-table").forEach((grid) => {
    grid.addEventListener("change", () => {
      grid.querySelectorAll(".chip-other-trigger").forEach((trigger) => {
        const wrap = document.querySelector(`[data-other-for="${trigger.dataset.otherTarget}"]`);
        if (wrap) wrap.hidden = !trigger.checked;
      });
    });
  });

  /* ============================================================
     Research team — add / remove rows
  ============================================================ */
  const teamTable = document.getElementById("applyTeamTable");
  const addTeamRowBtn = document.getElementById("addTeamRow");

  function bindRemove(row) {
    const btn = row.querySelector(".apply-team-remove");
    if (btn) btn.addEventListener("click", () => { row.remove(); });
  }
  teamTable.querySelectorAll(".apply-team-row:not(.apply-team-head)").forEach(bindRemove);

  addTeamRowBtn.addEventListener("click", () => {
    const row = document.createElement("div");
    row.className = "apply-team-row";
    row.innerHTML = `
      <input type="text" name="teamName[]" placeholder="Full name">
      <input type="text" name="teamRole[]" placeholder="e.g. Co-Investigator">
      <input type="text" name="teamInstitution[]" placeholder="Institution / organization">
      <button type="button" class="apply-team-remove" aria-label="Remove row"><i class="bi bi-x-lg"></i></button>
    `;
    teamTable.appendChild(row);
    bindRemove(row);
  });

  /* ============================================================
     Document uploader (client-side only — demo)
  ============================================================ */
  const fileInput = document.getElementById("applyFileInput");
  const fileDrop = document.querySelector(".apply-file-drop");
  const fileList = document.getElementById("applyFileList");
  let uploadedFiles = [];

  function formatSize(bytes) {
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  function renderFileList() {
    fileList.innerHTML = "";
    uploadedFiles.forEach((file, i) => {
      const item = document.createElement("div");
      item.className = "apply-file-item";
      item.innerHTML = `
        <i class="bi bi-file-earmark-text"></i>
        <span>${file.name}</span>
        <span class="apply-file-size">${formatSize(file.size)}</span>
        <button type="button" class="apply-file-remove" aria-label="Remove ${file.name}"><i class="bi bi-x-lg"></i></button>
      `;
      item.querySelector(".apply-file-remove").addEventListener("click", () => {
        uploadedFiles.splice(i, 1);
        renderFileList();
      });
      fileList.appendChild(item);
    });
  }

  function addFiles(fileArray) {
    Array.from(fileArray).forEach((f) => uploadedFiles.push(f));
    renderFileList();
    updateProgress();
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => { if (fileInput.files) addFiles(fileInput.files); });
  }
  if (fileDrop) {
    ["dragenter", "dragover"].forEach((evt) => {
      fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.add("is-dragover"); });
    });
    ["dragleave", "drop"].forEach((evt) => {
      fileDrop.addEventListener(evt, (e) => { e.preventDefault(); fileDrop.classList.remove("is-dragover"); });
    });
    fileDrop.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files) addFiles(e.dataTransfer.files);
    });
  }

  /* ============================================================
     Date defaults
  ============================================================ */
  const today = new Date().toISOString().slice(0, 10);
  const declarationDate = document.getElementById("declarationDate");
  if (declarationDate) declarationDate.value = today;

  /* ============================================================
     TOC: active-section highlighting + smooth scroll
  ============================================================ */
  const tocLinks = Array.from(document.querySelectorAll(".apply-toc a"));
  const sections = tocLinks
    .map((link) => document.getElementById(link.dataset.toc))
    .filter(Boolean);

  const SCROLLSPY_TRIGGER_OFFSET = 150; // matches .apply-section scroll-margin-top

  tocLinks.forEach((link) => {
    link.addEventListener("click", (e) => {
      const target = document.getElementById(link.dataset.toc);
      if (!target) return;
      e.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#" + target.id);
    });
  });

  function refreshActiveToc() {
    let activeId = sections[0] && sections[0].id;
    for (const s of sections) {
      if (s.getBoundingClientRect().top <= SCROLLSPY_TRIGGER_OFFSET) activeId = s.id;
      else break;
    }
    tocLinks.forEach((l) => l.classList.toggle("is-active", l.dataset.toc === activeId));
  }

  let scrollspyTicking = false;
  window.addEventListener("scroll", () => {
    if (scrollspyTicking) return;
    scrollspyTicking = true;
    requestAnimationFrame(() => { refreshActiveToc(); scrollspyTicking = false; });
  }, { passive: true });
  refreshActiveToc();

  /* ============================================================
     Progress meter — heuristic: answered fields / total visible fields
  ============================================================ */
  const progressFill = document.getElementById("applyProgressFill");
  const progressPct = document.getElementById("applyProgressPct");

  function isVisible(el) {
    return !!(el.offsetParent !== null || el.closest("[hidden]") === null);
  }

  function updateProgress() {
    const trackedSections = form.querySelectorAll(".apply-section");
    let total = 0;
    let answered = 0;

    trackedSections.forEach((section) => {
      if (section.closest("[hidden]")) return;

      // Text-like inputs / selects / textareas (excluding hidden helper inputs and "other" fields not shown)
      section.querySelectorAll('input[type="text"], input[type="email"], input[type="tel"], input[type="number"], input[type="date"], input[type="url"], select, textarea').forEach((field) => {
        if (field.closest("[hidden]")) return;
        if (field.disabled) return;
        total++;
        if (field.value && field.value.trim()) answered++;
      });

      // Checkbox / radio groups — count each distinct group once
      const groups = {};
      section.querySelectorAll('input[type="checkbox"], input[type="radio"]').forEach((box) => {
        if (box.closest("[hidden]")) return;
        if (box.disabled) return;
        if (!box.name) return;
        groups[box.name] = groups[box.name] || [];
        groups[box.name].push(box);
      });
      Object.values(groups).forEach((boxes) => {
        total++;
        if (boxes.some((b) => b.checked)) answered++;
      });

      // Yes/No toggles
      section.querySelectorAll(".yn-toggle").forEach((toggle) => {
        if (toggle.closest("[hidden]")) return;
        total++;
        if (toggle.querySelector(".yn-btn.active")) answered++;
      });
    });

    const pct = total ? Math.round((answered / total) * 100) : 0;
    if (progressFill) progressFill.style.width = pct + "%";
    if (progressPct) progressPct.textContent = pct + "%";
  }

  form.addEventListener("input", updateProgress);
  form.addEventListener("change", updateProgress);
  updateProgress();

  /* ============================================================
     Submit
  ============================================================ */
  form.addEventListener("submit", (e) => {
    e.preventDefault();

    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const submitBtn = form.querySelector(".btn-create-account");
    const originalHtml = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = "Submitting application...";

    setTimeout(() => {
      const formView = document.getElementById("applyFormView");
      const confirmView = document.getElementById("applyConfirmView");
      formView.hidden = true;
      confirmView.hidden = false;
      confirmView.scrollIntoView({ behavior: "smooth", block: "start" });
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalHtml;
    }, 700);
  });

  /* ============================================================
     Application date submitted (display only — set at submission
     time in a live system; shown here as today's date for context)
  ============================================================ */
  const dateSubmittedEl = document.getElementById("applyDateSubmitted");
  if (dateSubmittedEl) {
    dateSubmittedEl.textContent = new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" });
  }
});
